from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import (
    Period, AcademicDay, Group, Room, Subject, Activity,
    Professor, TeachingActivityAssignment,
    DocentEvent, NonDocentEvent, Schedule, TimeSlot,
    AssignedEvent, Constraint, ConstraintSchedule,
)


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------

class GroupInline(admin.TabularInline):
    model = Group
    extra = 1
    fields = ('group_code',)


class SubjectInline(admin.TabularInline):
    model = Subject
    extra = 1
    fields = ('name', 'alias')


class ActivityInline(admin.TabularInline):
    model = Activity
    extra = 0
    fields = ('title', 'activity_type')


class ConstraintScheduleInline(admin.TabularInline):
    model = ConstraintSchedule
    extra = 1
    fields = ('pattern_type', 'days_of_week', 'slots', 'week_numbers',
              'week_from', 'week_to', 'week_parity', 'specific_dates', 'time_of_day')


class AcademicDayInline(admin.TabularInline):
    model = AcademicDay
    extra = 0
    fields = ('date', 'academic_week_number', 'is_active', 'cancellation_reason')
    ordering = ('date',)
    show_change_link = True


# ---------------------------------------------------------------------------
# Period
# ---------------------------------------------------------------------------

@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'career', 'number', 'start_date', 'weeks_count', 'is_active', 'ver_horario')
    list_filter = ('career', 'is_active')
    search_fields = ('career', 'number')
    list_editable = ('is_active',)
    inlines = [GroupInline, SubjectInline, AcademicDayInline]

    def ver_horario(self, obj):
        url = reverse('schedule_selector') + f'?period_id={obj.id}'
        return format_html('<a href="{}" target="_blank">📅 Ver horario</a>', url)
    ver_horario.short_description = 'Horario'


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('group_code', 'period')
    list_filter = ('period__career', 'period')
    search_fields = ('group_code',)


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('room_code', 'room_type_badge')
    list_filter = ('room_type',)
    search_fields = ('room_code',)

    def room_type_badge(self, obj):
        colors = {
            'Classroom': '#f59e0b',
            'Laboratory': '#3b82f6',
            'Conference Room': '#10b981',
        }
        color = colors.get(obj.room_type, '#6b7280')
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:4px;font-size:0.82em">{}</span>',
            color, obj.get_room_type_display()
        )
    room_type_badge.short_description = 'Tipo'


# ---------------------------------------------------------------------------
# Subject + Activity
# ---------------------------------------------------------------------------

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'alias', 'period')
    list_filter = ('period__career', 'period')
    search_fields = ('name', 'alias')
    inlines = [ActivityInline]


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ('title', 'activity_type', 'subject')
    list_filter = ('activity_type', 'subject__period')
    search_fields = ('title', 'subject__name', 'subject__alias')


# ---------------------------------------------------------------------------
# Professor
# ---------------------------------------------------------------------------

@admin.register(Professor)
class ProfessorAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'scientific_category', 'docent_category')
    list_filter = ('scientific_category', 'docent_category')
    search_fields = ('^full_name',)


# ---------------------------------------------------------------------------
# TeachingActivityAssignment
# ---------------------------------------------------------------------------

@admin.register(TeachingActivityAssignment)
class TeachingActivityAssignmentAdmin(admin.ModelAdmin):
    list_display = ('subject', 'activity_type', 'group', 'professor')
    list_filter = ('activity_type', 'subject__period', 'group__period')
    search_fields = ('subject__alias', 'subject__name', 'group__group_code', 'professor__full_name')
    autocomplete_fields = ('subject', 'group', 'professor')


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

@admin.register(Constraint)
class ConstraintAdmin(admin.ModelAdmin):
    list_display = ('name', 'priority_badge', 'constraint_type', 'target_type', 'target_name', 'is_active')
    list_filter = ('priority', 'constraint_type', 'target_type', 'is_active')
    search_fields = ('name',)
    list_editable = ('is_active',)
    inlines = [ConstraintScheduleInline]

    def priority_badge(self, obj):
        colors = {1: '#9ca3af', 2: '#60a5fa', 3: '#fbbf24', 4: '#f97316', 5: '#ef4444'}
        labels = {1: 'Deseable', 2: 'Preferencia', 3: 'Importante', 4: 'Casi oblig.', 5: 'Absoluta'}
        color = colors.get(obj.priority, '#6b7280')
        label = labels.get(obj.priority, str(obj.priority))
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:4px;font-size:0.82em">P{} — {}</span>',
            color, obj.priority, label
        )
    priority_badge.short_description = 'Prioridad'

    def target_name(self, obj):
        if obj.professor:   return str(obj.professor)
        if obj.room:        return str(obj.room)
        if obj.group:       return str(obj.group)
        if obj.subject:     return str(obj.subject)
        return '—'
    target_name.short_description = 'Objetivo'


@admin.register(ConstraintSchedule)
class ConstraintScheduleAdmin(admin.ModelAdmin):
    list_display = ('constraint', 'pattern_type', 'days_of_week', 'slots')
    list_filter = ('pattern_type',)
    search_fields = ('constraint__name',)


# ---------------------------------------------------------------------------
# Schedule (read-only overview)
# ---------------------------------------------------------------------------

@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'period', 'group', 'is_base', 'score', 'generated_at')
    list_filter = ('is_base', 'period', 'group')
    readonly_fields = ('generated_at', 'score')


# ---------------------------------------------------------------------------
# Events (mostly read-only, generated by the solver)
# ---------------------------------------------------------------------------

@admin.register(DocentEvent)
class DocentEventAdmin(admin.ModelAdmin):
    list_display = ('activity', 'professor', 'room')
    search_fields = ('activity__title', 'professor__full_name', 'room__room_code')


@admin.register(NonDocentEvent)
class NonDocentEventAdmin(admin.ModelAdmin):
    list_display = ('title', 'room')
    search_fields = ('title', 'room__room_code')


@admin.register(AcademicDay)
class AcademicDayAdmin(admin.ModelAdmin):
    list_display = ('date', 'period', 'academic_week_number', 'is_active', 'cancellation_reason')
    list_filter = ('period', 'is_active')
    search_fields = ('period__career',)
    list_editable = ('is_active', 'cancellation_reason')
    ordering = ('period', 'date')


# ---------------------------------------------------------------------------
# Spanish verbose names for admin site
# ---------------------------------------------------------------------------
from django.apps import apps

VERBOSE_NAMES_ES = {
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
    'TimeSlot':                   ('Bloque Horario',       'Bloques Horarios'),
    'AssignedEvent':              ('Evento Asignado',      'Eventos Asignados'),
}

app = apps.get_app_config('data_management')
for model_name, (singular, plural) in VERBOSE_NAMES_ES.items():
    try:
        model = app.get_model(model_name)
        model._meta.verbose_name = singular
        model._meta.verbose_name_plural = plural
    except LookupError:
        pass


# ---------------------------------------------------------------------------
# Translate Django auth models (Groups / Users)
# ---------------------------------------------------------------------------
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib import admin as django_admin

try:
    django_admin.site.unregister(User)
    django_admin.site.unregister(Group)
except Exception:
    pass

User._meta.verbose_name = 'Usuario'
User._meta.verbose_name_plural = 'Usuarios'
Group._meta.verbose_name = 'Grupo de Permisos'
Group._meta.verbose_name_plural = 'Grupos de Permisos'

django_admin.site.register(User, UserAdmin)
django_admin.site.register(Group, GroupAdmin)