import uuid
from django.db import models
from django.core.validators import MinValueValidator
from django.forms import ValidationError


# =============================================================================
# PERÍODO Y CALENDARIO ACADÉMICO
# =============================================================================

class Period(models.Model):
    """Represents the semester or planning period."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.IntegerField(validators=[MinValueValidator(1)])
    weeks_count = models.IntegerField(default=16, validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=False)
    start_date = models.DateField(null=True, blank=True)

    class Career(models.TextChoices):
        ICI_D = 'ICI_D', 'Ingeniería en Ciencias Informáticas Curso Diurno'
        ICI_CPE = 'ICI_CPE', 'Ingeniería en Ciencias Informáticas Curso por Encuentros'

    career = models.CharField(max_length=30, choices=Career.choices)

    CAREERS_PERIOD_COUNT = {
        Career.ICI_D: 8,
        Career.ICI_CPE: 10
    }

    def clean(self):
        super().clean()
        total_period_count = self.CAREERS_PERIOD_COUNT.get(self.career)
        if total_period_count is not None:
            if self.number > total_period_count:
                career_name = self.get_career_display()
                raise ValidationError(
                    {
                        'number': f'El número del período ({self.number}) excede el máximo permitido '
                                  f'de {total_period_count} para la carrera: {career_name}.'
                    }
                )

    def __str__(self):
        return self.get_career_display() + ' - Período ' + str(self.number)


class AcademicDay(models.Model):
    """
    Represents a real calendar day within a period.
    When a day is cancelled (is_active=False), the semester extends by one day at the end.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    period = models.ForeignKey(Period, on_delete=models.CASCADE, related_name='academic_days')
    date = models.DateField()
    is_active = models.BooleanField(default=True)
    academic_week_number = models.IntegerField(validators=[MinValueValidator(1)])
    cancellation_reason = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['date']
        unique_together = ('period', 'date')

    def __str__(self):
        status = '' if self.is_active else ' (cancelado)'
        return f'{self.date} - Semana {self.academic_week_number}{status}'


# =============================================================================
# ENTIDADES PRINCIPALES
# =============================================================================

class Professor(models.Model):
    class ScientificCategory(models.TextChoices):
        DOCTOR = 'Doctor', 'Dr.'
        MASTER = 'Master', 'Msc.'
        LICENSED = 'Licensed', 'Lic.'
        ENGINEER = 'Engineer', 'Ing.'
        NONE = 'None', 'None'

    class DocentCategory(models.TextChoices):
        TITULAR = 'Titular', 'TI'
        ASSISTANT = 'Assistant', 'PA'
        ASSOCIATE = 'Associate', 'AU'
        INSTRUCTOR = 'Instructor', 'PI'

    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    full_name = models.CharField(max_length=100)
    scientific_category = models.CharField(max_length=50, choices=ScientificCategory.choices)
    docent_category = models.CharField(max_length=50, choices=DocentCategory.choices)

    def __str__(self):
        return self.full_name


class Room(models.Model):
    class RoomType(models.TextChoices):
        CLASSROOM = 'Classroom', 'A'
        LABORATORY = 'Laboratory', 'L'
        CONFERENCE_ROOM = 'Conference Room', 'S'

    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    room_code = models.CharField(max_length=10, unique=True)
    room_type = models.CharField(max_length=50, choices=RoomType.choices)

    def __str__(self):
        return self.room_code


class Subject(models.Model):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    alias = models.CharField(max_length=50, blank=True, null=True)
    period = models.ForeignKey(Period, on_delete=models.CASCADE, related_name='subjects')

    def __str__(self):
        return self.alias or self.name


class Group(models.Model):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    group_code = models.CharField(max_length=10)
    period = models.ForeignKey(Period, on_delete=models.CASCADE, null=True, related_name='groups')

    def __str__(self):
        return self.group_code


class Activity(models.Model):
    """Defines the types of classes."""
    class ActivityType(models.TextChoices):
        CONFERENCE = 'Conference', 'C'
        PRACTICAL_CLASS = 'Practical Class', 'CP'
        LABORATORY = 'Laboratory', 'L'

    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    title = models.CharField(max_length=100, verbose_name='Título')
    activity_type = models.CharField(max_length=50, choices=ActivityType.choices, verbose_name='Tipo de Actividad')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='activities_program', default=None, null=True, verbose_name='Asignatura')

    def __str__(self):
        return f'{self.title} ({self.get_activity_type_display()})'


class TeachingActivityAssignment(models.Model):
    """Links Subject, Group, and a Professor for the term."""
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    professor = models.ForeignKey(Professor, on_delete=models.SET_NULL, null=True, blank=True)
    activity_type = models.CharField(max_length=50, choices=Activity.ActivityType.choices)

    class Meta:
        unique_together = ('subject', 'group', 'activity_type')


# =============================================================================
# RESTRICCIONES GESTIONABLES
# =============================================================================

class Constraint(models.Model):
    class ConstraintType(models.TextChoices):
        UNAVAILABILITY = 'UNAVAILABILITY', 'Indisponibilidad temporal'
        TIME_SLOT_PREFERENCE = 'TIME_SLOT_PREFERENCE', 'Preferencia de franja horaria'
        ROOM_ASSIGNMENT = 'ROOM_ASSIGNMENT', 'Asignación fija de local'

    class TargetType(models.TextChoices):
        PROFESSOR = 'PROFESSOR', 'Profesor'
        ROOM = 'ROOM', 'Local'
        GROUP = 'GROUP', 'Grupo'
        SUBJECT = 'SUBJECT', 'Asignatura'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    priority = models.IntegerField(
        validators=[MinValueValidator(1)],
        choices=[(i, str(i)) for i in range(1, 6)]
    )
    constraint_type = models.CharField(max_length=50, choices=ConstraintType.choices)
    target_type = models.CharField(max_length=50, choices=TargetType.choices)

    professor = models.ForeignKey(Professor, on_delete=models.CASCADE, null=True, blank=True, related_name='constraints')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, null=True, blank=True, related_name='constraints')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True, blank=True, related_name='constraints')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True, related_name='constraints')

    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)

    def clean(self):
        super().clean()
        filled = sum([
            1 if self.professor else 0,
            1 if self.room else 0,
            1 if self.group else 0,
            1 if self.subject else 0,
        ])
        if filled != 1:
            raise ValidationError('Una restricción debe tener exactamente un objetivo (profesor, local, grupo o asignatura).')

    def __str__(self):
        return f'[P{self.priority}] {self.name}'


class ConstraintSchedule(models.Model):
    class PatternType(models.TextChoices):
        ALWAYS = 'ALWAYS', 'Siempre'
        SPECIFIC_DATES = 'SPECIFIC_DATES', 'Fechas específicas'
        WEEK_RANGE = 'WEEK_RANGE', 'Rango de semanas'
        WEEK_LIST = 'WEEK_LIST', 'Lista de semanas'
        WEEK_PARITY = 'WEEK_PARITY', 'Semanas pares/impares'

    class WeekParity(models.TextChoices):
        EVEN = 'EVEN', 'Pares'
        ODD = 'ODD', 'Impares'

    class TimeOfDay(models.TextChoices):
        MORNING = 'MORNING', 'Mañana (turnos 1-3)'
        AFTERNOON = 'AFTERNOON', 'Tarde (turnos 4-6)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    constraint = models.ForeignKey(Constraint, on_delete=models.CASCADE, related_name='schedules')
    pattern_type = models.CharField(max_length=20, choices=PatternType.choices)
    days_of_week = models.JSONField(default=list, blank=True)
    slots = models.JSONField(default=list, blank=True)
    week_from = models.IntegerField(null=True, blank=True)
    week_to = models.IntegerField(null=True, blank=True)
    week_numbers = models.JSONField(default=list, blank=True)
    week_parity = models.CharField(max_length=10, choices=WeekParity.choices, null=True, blank=True)
    specific_dates = models.JSONField(default=list, blank=True)
    time_of_day = models.CharField(max_length=20, choices=TimeOfDay.choices, null=True, blank=True)

    def __str__(self):
        return f'{self.constraint.name} - {self.get_pattern_type_display()}'


# =============================================================================
# HORARIOS
# =============================================================================

class Schedule(models.Model):
    """
    A generated schedule.
    is_base=True  → the base schedule for the entire semester.
    is_base=False → a week-specific schedule derived from the base.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    period = models.ForeignKey(Period, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True, blank=True)
    is_base = models.BooleanField(default=False)
    academic_week = models.ForeignKey(
        AcademicDay,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='schedules',
    )
    score = models.IntegerField(default=0)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('period', 'group', 'academic_week')

    def __str__(self):
        if self.is_base:
            return f'Horario Base - {self.period} - {self.group}'
        return f'Horario Semana {self.academic_week} - {self.period} - {self.group}'


class TimeSlot(models.Model):
    SLOT_CHOICES = [
        (1, '8:00 - 9:20'),
        (2, '9:30 - 10:50'),
        (3, '11:00 - 12:20'),
        (4, '12:30 - 13:50'),
        (5, '14:00 - 15:20'),
        (6, '15:30 - 16:50'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name='time_slots')
    academic_day = models.ForeignKey(AcademicDay, on_delete=models.CASCADE, related_name='time_slots')
    slot_index = models.IntegerField(choices=SLOT_CHOICES)

    class Meta:
        unique_together = ('schedule', 'academic_day', 'slot_index')

    def __str__(self):
        return f'{self.academic_day.date} - Turno {self.slot_index}'


# =============================================================================
# EVENTOS
# =============================================================================

class NonDocentEvent(models.Model):
    """Unique, manually scheduled non-teaching activities (meetings, etc.)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    affected_groups = models.ManyToManyField(Group, related_name='non_docent_events', blank=True)
    title = models.CharField(max_length=100)
    professors = models.ManyToManyField(Professor, related_name='non_docent_events', blank=True)
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.title


class DocentEvent(models.Model):
    """A teaching activity instance placed in a schedule."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    professor = models.ForeignKey(Professor, on_delete=models.SET_NULL, null=True, blank=True)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f'{self.activity} - {self.professor}'


class AssignedEvent(models.Model):
    """Links a TimeSlot to either a DocentEvent or a NonDocentEvent."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE)
    docent_event = models.ForeignKey(DocentEvent, on_delete=models.CASCADE, null=True, blank=True)
    non_docent_event = models.ForeignKey(NonDocentEvent, on_delete=models.CASCADE, null=True, blank=True)

    def clean(self):
        super().clean()
        event_count = sum([
            1 if self.docent_event else 0,
            1 if self.non_docent_event else 0,
        ])
        if event_count > 1:
            raise ValidationError(
                'Un AssignedEvent debe tener solamente un tipo de evento asignado (DocentEvent o NonDocentEvent), nunca ambos.'
            )
        if event_count < 1:
            raise ValidationError(
                'Un AssignedEvent debe tener un evento asignado, ya sea DocentEvent o NonDocentEvent.'
            )

    def __str__(self):
        if self.docent_event:
            return f'Asignación en {self.time_slot} - Docente: {self.docent_event}'
        elif self.non_docent_event:
            return f'Asignación en {self.time_slot} - No Docente: {self.non_docent_event}'
        return f'Asignación en {self.time_slot} - Evento Faltante (Error de Validación)'