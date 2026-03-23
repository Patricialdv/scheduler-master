from django.contrib import admin as django_admin
from django.utils.html import format_html
from django.urls import reverse
from django import forms
from django.utils.safestring import mark_safe

from .models import (
    Period, AcademicDay, Group, Room, Subject, Activity,
    Professor, TeachingActivityAssignment,
    Constraint, ConstraintSchedule,
    Schedule, DocentEvent, NonDocentEvent, AssignedEvent, TimeSlot,
)

admin = django_admin


# ---------------------------------------------------------------------------
# Inlines helpers
# ---------------------------------------------------------------------------

class GroupInline(admin.TabularInline):
    model = Group
    extra = 0
    fields = ('group_code',)
    show_change_link = True

class SubjectInline(admin.TabularInline):
    model = Subject
    extra = 0
    fields = ('name', 'alias')
    show_change_link = True

class ActivityInline(admin.TabularInline):
    model = Activity
    extra = 0
    fields = ('title', 'activity_type')

class AcademicDayInline(admin.TabularInline):
    model = AcademicDay
    extra = 0
    fields = ('date', 'academic_week_number', 'is_active', 'cancellation_reason')
    ordering = ('date',)
    show_change_link = True


# ---------------------------------------------------------------------------
# ConstraintSchedule — custom form
# ---------------------------------------------------------------------------

DAYS_CHOICES = [
    ('1', 'Lunes'), ('2', 'Martes'), ('3', 'Miércoles'),
    ('4', 'Jueves'), ('5', 'Viernes'),
]

SLOTS_CHOICES = [
    ('1', 'T1 — 8:00-9:20'),  ('2', 'T2 — 9:30-10:50'),
    ('3', 'T3 — 11:00-12:20'), ('4', 'T4 — 12:30-13:50'),
    ('5', 'T5 — 14:00-15:20'), ('6', 'T6 — 15:30-16:50'),
]

WEEKS_CHOICES = [(str(i), f'Semana {i}') for i in range(1, 17)]


class CheckboxGroupWidget(forms.CheckboxSelectMultiple):
    """Checkbox group que añade clase CSS para styling."""
    option_template_name = 'django/forms/widgets/checkbox_option.html'

    def __init__(self, css_class='checkbox-select', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.css_class = css_class

    def build_attrs(self, base_attrs, extra_attrs=None):
        attrs = super().build_attrs(base_attrs, extra_attrs)
        return attrs

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx['widget']['attrs']['class'] = self.css_class
        return ctx


class WeekNumberWidget(CheckboxGroupWidget):
    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx['widget']['attrs']['class'] = 'semanas-grid'
        return ctx


class ConstraintScheduleForm(forms.ModelForm):
    days_of_week = forms.MultipleChoiceField(
        choices=DAYS_CHOICES,
        widget=CheckboxGroupWidget(),
        required=False,
        label='Días de la semana',
        help_text='Deja vacío para aplicar a todos los días.',
    )
    slots = forms.MultipleChoiceField(
        choices=SLOTS_CHOICES,
        widget=CheckboxGroupWidget(),
        required=False,
        label='Turnos',
        help_text='Deja vacío para aplicar a todos los turnos.',
    )
    week_numbers = forms.MultipleChoiceField(
        choices=WEEKS_CHOICES,
        widget=WeekNumberWidget(),
        required=False,
        label='Semanas',
        help_text='Solo para patrón "Lista de semanas". Selecciona las semanas en que aplica la restricción.',
    )

    class Meta:
        model = ConstraintSchedule
        fields = '__all__'
        widgets = {
            'specific_dates': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': '["2024-03-15", "2024-03-22"]',
                'style': 'font-family:monospace;font-size:0.82rem;',
            }),
        }
        labels = {
            'pattern_type':    'Patrón de aplicación',
            'week_from':       'Desde semana №',
            'week_to':         'Hasta semana №',
            'week_parity':     'Paridad (par/impar)',
            'specific_dates':  'Fechas específicas (JSON)',
            'time_of_day':     'Franja del día',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get('instance')
        if instance:
            if instance.days_of_week:
                self.initial['days_of_week'] = [str(d) for d in instance.days_of_week]
            if instance.slots:
                self.initial['slots'] = [str(s) for s in instance.slots]
            if instance.week_numbers:
                self.initial['week_numbers'] = [str(w) for w in instance.week_numbers]
        # Estilizar week_from y week_to como número pequeño
        for field in ('week_from', 'week_to'):
            if field in self.fields:
                self.fields[field].widget.attrs.update({
                    'style': 'width:80px;',
                    'min': 1, 'max': 20,
                })

    def clean_days_of_week(self):
        return [int(d) for d in self.cleaned_data.get('days_of_week', [])]

    def clean_slots(self):
        return [int(s) for s in self.cleaned_data.get('slots', [])]

    def clean_week_numbers(self):
        return [int(w) for w in self.cleaned_data.get('week_numbers', [])]


class ConstraintScheduleInline(admin.StackedInline):
    model = ConstraintSchedule
    form = ConstraintScheduleForm
    extra = 1
    can_delete = True
    verbose_name = 'Patrón temporal'
    verbose_name_plural = 'Patrones temporales'

    fieldsets = (
        ('Tipo de patrón', {
            'fields': ('pattern_type',),
        }),
        ('¿Qué días y turnos?', {
            'fields': ('days_of_week', 'slots'),
            'description': 'Selecciona los días y turnos afectados. Vacío = todos.',
        }),
        ('¿En qué semanas?', {
            'fields': ('week_numbers', 'week_from', 'week_to', 'week_parity', 'specific_dates'),
            'classes': ('collapse',),
            'description': 'Solo necesario si el patrón no es "Siempre".',
        }),
        ('Franja horaria', {
            'fields': ('time_of_day',),
            'classes': ('collapse',),
            'description': 'Solo para restricciones de tipo "Preferencia de franja horaria".',
        }),
    )

    class Media:
        css = {'all': []}
        js = []


# ---------------------------------------------------------------------------
# Constraint admin — with JS to show/hide fields by constraint_type
# ---------------------------------------------------------------------------

class ConstraintAdminForm(forms.ModelForm):
    class Meta:
        model = Constraint
        fields = '__all__'
        labels = {
            'name':            'Nombre descriptivo',
            'priority':        'Prioridad',
            'constraint_type': 'Tipo de restricción',
            'target_type':     'Objetivo',
            'professor':       'Profesor',
            'room':            'Local',
            'group':           'Grupo',
            'subject':         'Asignatura',
            'is_active':       'Activa',
            'notes':           'Notas / Tipo de actividad',
        }
        help_texts = {
            'priority': (
                '1 = Deseable | 2 = Preferencia | 3 = Importante | '
                '4 = Casi obligatoria | 5 = Absoluta (nunca se viola)'
            ),
            'notes': (
                'Para "Asignación fija de local": escribe C, CP o L '
                'para limitar a un tipo de actividad. Vacío = todos los tipos.'
            ),
        }


@admin.register(Constraint)
class ConstraintAdmin(admin.ModelAdmin):
    form = ConstraintAdminForm
    list_per_page = 20
    list_display  = ('name', 'priority_badge', 'constraint_type_badge', 'target_badge', 'is_active')
    list_filter   = ('priority', 'constraint_type', 'target_type', 'is_active')
    search_fields = ('name',)
    list_editable = ('is_active',)
    inlines       = [ConstraintScheduleInline]

    fieldsets = (
        ('Identificación', {
            'fields': ('name', 'priority', 'constraint_type', 'is_active'),
        }),
        ('Objetivo', {
            'fields': ('target_type', 'professor', 'room', 'group', 'subject'),
            'description': (
                'Selecciona el tipo de objetivo y luego elige <strong>solo uno</strong> '
                'de los campos de abajo (profesor, local, grupo o asignatura).'
            ),
        }),
        ('Opciones adicionales', {
            'fields': ('notes',),
            'classes': ('collapse',),
        }),
    )

    class Media:
        js = ('admin/js/constraint_form.js',)

    def priority_badge(self, obj):
        colors = {1: '#9ca3af', 2: '#60a5fa', 3: '#fbbf24', 4: '#f97316', 5: '#ef4444'}
        labels = {1: 'Deseable', 2: 'Preferencia', 3: 'Importante', 4: 'Casi oblig.', 5: 'Absoluta'}
        color  = colors.get(obj.priority, '#6b7280')
        label  = labels.get(obj.priority, str(obj.priority))
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:4px;font-size:0.82em">P{} — {}</span>',
            color, obj.priority, label
        )
    priority_badge.short_description = 'Prioridad'

    def constraint_type_badge(self, obj):
        labels = {
            'UNAVAILABILITY':      ('Indisponibilidad', '#6366f1'),
            'TIME_SLOT_PREFERENCE':('Franja horaria',   '#0ea5e9'),
            'ROOM_ASSIGNMENT':     ('Local fijo',       '#10b981'),
        }
        label, color = labels.get(obj.constraint_type, (obj.constraint_type, '#6b7280'))
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:4px;font-size:0.82em">{}</span>',
            color, label
        )
    constraint_type_badge.short_description = 'Tipo'

    def target_badge(self, obj):
        target = None
        if obj.professor:  target = f'👤 {obj.professor}'
        elif obj.room:     target = f'🏫 {obj.room}'
        elif obj.group:    target = f'👥 {obj.group}'
        elif obj.subject:  target = f'📚 {obj.subject}'
        return target or '—'
    target_badge.short_description = 'Objetivo'

    def target_name(self, obj):
        return self.target_badge(obj)
    target_name.short_description = 'Objetivo'


# ---------------------------------------------------------------------------
# Period
# ---------------------------------------------------------------------------

@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_per_page  = 20
    list_display   = ('__str__', 'career', 'number', 'start_date', 'weeks_count', 'is_active', 'ver_horario')
    list_filter    = ('career', 'is_active')
    search_fields  = ('career', 'number')
    list_editable  = ('is_active',)
    inlines        = [GroupInline, SubjectInline, AcademicDayInline]

    def ver_horario(self, obj):
        url = reverse('schedule_selector') + f'?period_id={obj.id}'
        return format_html('<a href="{}" target="_blank">📅 Ver horario</a>', url)
    ver_horario.short_description = 'Horario'


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_display  = ('group_code', 'period')
    list_filter   = ('period__career', 'period')
    search_fields = ('group_code',)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_display  = ('room_code', 'room_type_badge')
    list_filter   = ('room_type',)
    search_fields = ('room_code',)

    def room_type_badge(self, obj):
        colors = {
            'Classroom':      '#f59e0b',
            'Laboratory':     '#3b82f6',
            'Conference Room':'#10b981',
        }
        color = colors.get(obj.room_type, '#6b7280')
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:4px;font-size:0.82em">{}</span>',
            color, obj.get_room_type_display()
        )
    room_type_badge.short_description = 'Tipo'


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_display  = ('name', 'alias', 'period')
    list_filter   = ('period__career', 'period')
    search_fields = ('name', 'alias')
    inlines       = [ActivityInline]


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_display  = ('title', 'activity_type', 'subject')
    list_filter   = ('activity_type', 'subject__period')
    search_fields = ('title', 'subject__name', 'subject__alias')


@admin.register(Professor)
class ProfessorAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_display  = ('full_name', 'scientific_category', 'docent_category')
    list_filter   = ('scientific_category', 'docent_category')
    search_fields = ('^full_name',)


@admin.register(TeachingActivityAssignment)
class TeachingActivityAssignmentAdmin(admin.ModelAdmin):
    list_per_page    = 20
    list_display     = ('subject', 'activity_type', 'group', 'professor')
    list_filter      = ('activity_type', 'subject__period', 'group__period')
    search_fields    = ('subject__alias', 'subject__name', 'group__group_code', 'professor__full_name')
    autocomplete_fields = ('subject', 'group', 'professor')


@admin.register(ConstraintSchedule)
class ConstraintScheduleAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_display  = ('constraint', 'pattern_type')


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_per_page  = 20
    list_display   = ('period', 'group', 'is_base', 'score', 'generated_at')
    list_filter    = ('is_base', 'period')
    readonly_fields = ('generated_at', 'score')


@admin.register(DocentEvent)
class DocentEventAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_display  = ('activity', 'professor', 'room')
    search_fields = ('activity__title', 'professor__full_name', 'room__room_code')


@admin.register(NonDocentEvent)
class NonDocentEventAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_display  = ('title', 'room')
    search_fields = ('title', 'room__room_code')


@admin.register(AcademicDay)
class AcademicDayAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_display  = ('date', 'period', 'academic_week_number', 'is_active', 'cancellation_reason')
    list_filter   = ('period', 'is_active')
    search_fields = ('date',)


# ---------------------------------------------------------------------------
# Translate Django auth models
# ---------------------------------------------------------------------------

from django.contrib.auth.models import User, Group as AuthGroup
from django.contrib.auth.admin import UserAdmin, GroupAdmin as AuthGroupAdmin

django_admin.site.unregister(User)
try:
    django_admin.site.unregister(AuthGroup)
except Exception:
    pass

User._meta.verbose_name        = 'Usuario'
User._meta.verbose_name_plural = 'Usuarios'
AuthGroup._meta.verbose_name        = 'Grupo de Permisos'
AuthGroup._meta.verbose_name_plural = 'Grupos de Permisos'

# Verbose names for Constraint model
VERBOSE_MAP = {
    'Period':                     ('Período',              'Períodos'),
    'AcademicDay':                ('Día Académico',        'Días Académicos'),
    'Group':                      ('Grupo',                'Grupos'),
    'Room':                       ('Local',                'Locales'),
    'Subject':                    ('Asignatura',           'Asignaturas'),
    'Activity':                   ('Actividad',            'Actividades'),
    'Professor':                  ('Profesor',             'Profesores'),
    'TeachingActivityAssignment': ('Asignación Docente',   'Asignaciones Docentes'),
    'Constraint':                 ('Restricción',          'Restricciones'),
    'ConstraintSchedule':         ('Patrón Temporal',      'Patrones Temporales'),
    'Schedule':                   ('Horario',              'Horarios'),
    'DocentEvent':                ('Evento Docente',       'Eventos Docentes'),
    'NonDocentEvent':             ('Evento No Docente',    'Eventos No Docentes'),
    'AssignedEvent':              ('Evento Asignado',      'Eventos Asignados'),
    'TimeSlot':                   ('Turno',                'Turnos'),
}

from django.apps import apps as django_apps
for model_name, (singular, plural) in VERBOSE_MAP.items():
    try:
        m = django_apps.get_model('data_management', model_name)
        m._meta.verbose_name        = singular
        m._meta.verbose_name_plural = plural
    except Exception:
        pass

class CustomUserAdmin(UserAdmin):
    list_per_page = 20
    actions = ['delete_selected']

class CustomGroupAdmin(AuthGroupAdmin):
    list_per_page = 20
    actions = ['delete_selected']

django_admin.site.register(User, CustomUserAdmin)
django_admin.site.register(AuthGroup, CustomGroupAdmin)


# ---------------------------------------------------------------------------
# Signals — automatic schedule regeneration on admin changes
# ---------------------------------------------------------------------------

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


def _run_regen(func, *args, **kwargs):
    """Run a regeneration function and log errors without crashing."""
    import logging
    log = logging.getLogger(__name__)
    try:
        errors = func(*args, **kwargs)
        for e in errors:
            log.error(f'[signal regen] {e}')
    except Exception as e:
        log.error(f'[signal regen] Unexpected error: {e}')


@receiver([post_save, post_delete], sender=Room)
def on_room_change(sender, instance, **kwargs):
    """Room change affects all active periods."""
    from apps.scheduler_management.schedule_service import regenerate_all_active_periods
    _run_regen(regenerate_all_active_periods)


@receiver([post_save, post_delete], sender=TeachingActivityAssignment)
def on_assignment_change(sender, instance, **kwargs):
    """Assignment change affects its period."""
    from apps.scheduler_management.schedule_service import regenerate_period
    try:
        period = instance.subject.period
        if period.is_active:
            _run_regen(regenerate_period, period)
    except Exception:
        pass


@receiver([post_save, post_delete], sender=Group)
def on_group_change(sender, instance, **kwargs):
    """Group change affects its period."""
    from apps.scheduler_management.schedule_service import regenerate_period
    try:
        period = instance.period
        if period and period.is_active:
            _run_regen(regenerate_period, period)
    except Exception:
        pass


@receiver([post_save, post_delete], sender=Subject)
def on_subject_change(sender, instance, **kwargs):
    """Subject change affects its period."""
    from apps.scheduler_management.schedule_service import regenerate_period
    try:
        period = instance.period
        if period and period.is_active:
            _run_regen(regenerate_period, period)
    except Exception:
        pass


@receiver([post_save, post_delete], sender=Constraint)
def on_constraint_change(sender, instance, **kwargs):
    """Constraint change: regenerate affected periods from earliest affected week."""
    from apps.scheduler_management.schedule_service import (
        get_affected_periods_from_constraint,
        get_earliest_week_from_constraint,
        regenerate_from_week,
    )
    try:
        periods = get_affected_periods_from_constraint(instance)
        from_week = get_earliest_week_from_constraint(instance)
        for period in periods:
            _run_regen(regenerate_from_week, period, from_week)
    except Exception:
        pass


@receiver([post_save, post_delete], sender=ConstraintSchedule)
def on_constraint_schedule_change(sender, instance, **kwargs):
    """ConstraintSchedule change: same logic as its parent Constraint."""
    from apps.scheduler_management.schedule_service import (
        get_affected_periods_from_constraint,
        get_earliest_week_from_constraint,
        regenerate_from_week,
    )
    try:
        constraint = instance.constraint
        periods = get_affected_periods_from_constraint(constraint)
        from_week = get_earliest_week_from_constraint(constraint)
        for period in periods:
            _run_regen(regenerate_from_week, period, from_week)
    except Exception:
        pass


@receiver(post_save, sender=Period)
def on_period_change(sender, instance, **kwargs):
    """If a period becomes active, ensure it has a schedule."""
    if instance.is_active:
        from apps.scheduler_management.schedule_service import ensure_all_active_periods
        _run_regen(ensure_all_active_periods)