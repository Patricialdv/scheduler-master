"""
test_schedules.py
=================
Verifica que los horarios generados cumplen con todas las restricciones del sistema.

Pruebas incluidas:
  1. Tipo de sala correcto (Conf→Salón, CP→Aula, Lab→Laboratorio)
  2. Sin solapamiento de profesor (mismo profesor, mismo día y turno, 2 eventos)
  3. Sin solapamiento de sala (misma sala, mismo día y turno, 2 eventos)
  4. Sin solapamiento de grupo (mismo grupo, mismo día y turno, 2 eventos)
  5. Restricciones UNAVAILABILITY activas (prof/sala/grupo no disponible en ese turno)
  6. Restricciones ROOM_ASSIGNMENT (asignatura/grupo/prof debe usar sala fija)
  7. Restricciones TIME_SLOT_PREFERENCE (preferencia de franja horaria)
  8. Integridad referencial (TimeSlots sin AssignedEvent, eventos sin actividad)

Uso:
    python manage.py shell < test_schedules.py
    O: exec(open('test_schedules.py').read())
"""

import os
import django
from collections import defaultdict
from datetime import date

if not os.environ.get('DJANGO_SETTINGS_MODULE'):
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.general.settings')
    django.setup()

from apps.data_management.models import (
    Period, Schedule, TimeSlot, AssignedEvent,
    DocentEvent, Activity, Room, Constraint, ConstraintSchedule,
    AcademicDay,
)


# ── Tipos de sala permitidos por actividad ────────────────────────────────────
ROOM_TYPE_MAP = {
    Activity.ActivityType.CONFERENCE:     Room.RoomType.CONFERENCE_ROOM,   # 'S'
    Activity.ActivityType.PRACTICAL_CLASS: Room.RoomType.CLASSROOM,         # 'A'
    Activity.ActivityType.LABORATORY:     Room.RoomType.LABORATORY,         # 'L'
}

SLOT_LABEL = {1: '8:00-9:20', 2: '9:30-10:50', 3: '11:00-12:20',
              4: '12:30-13:50', 5: '14:00-15:20', 6: '15:30-16:50'}

DAY_NAME = {0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves', 4: 'Viernes'}


# ── Clases de resultado ───────────────────────────────────────────────────────

class Violation:
    def __init__(self, test, period, schedule, description, severity='ERROR'):
        self.test        = test
        self.period      = str(period)
        self.schedule    = str(schedule)
        self.description = description
        self.severity    = severity  # ERROR | WARN

    def __str__(self):
        icon = '[ERROR]' if self.severity == 'ERROR' else '[AVISO] '
        return f"  {icon} [{self.test}] {self.schedule}\n     {self.description}"


class TestResult:
    def __init__(self, name):
        self.name       = name
        self.violations = []
        self.checked    = 0

    def add(self, v: Violation):
        self.violations.append(v)

    def passed(self):
        return len([v for v in self.violations if v.severity == 'ERROR']) == 0

    def summary(self):
        errors = sum(1 for v in self.violations if v.severity == 'ERROR')
        warns  = sum(1 for v in self.violations if v.severity == 'WARN')
        icon   = '[OK]' if self.passed() else '[ERROR]'
        parts  = [f"revisados={self.checked}"]
        if errors: parts.append(f"errores={errors}")
        if warns:  parts.append(f"avisos={warns}")
        return f"{icon} {self.name} ({', '.join(parts)})"


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_all_assigned_events():
    """Devuelve todos los AssignedEvents de horarios base con sus relaciones."""
    return (
        AssignedEvent.objects
        .filter(
            time_slot__schedule__is_base=True,
            docent_event__isnull=False,
        )
        .select_related(
            'time_slot__schedule__period',
            'time_slot__schedule__group',
            'time_slot__academic_day',
            'docent_event__professor',
            'docent_event__activity__subject',
            'docent_event__room',
        )
    )


def slot_key(ae):
    """(day_of_week, slot_index) para un AssignedEvent."""
    d = ae.time_slot.academic_day.date
    return (d.weekday(), ae.time_slot.slot_index)


def constraint_applies_to_slot(cs: ConstraintSchedule, day_of_week: int,
                                slot_index: int, academic_week: int = 0) -> bool:
    """
    Evalúa si un ConstraintSchedule aplica a un día/turno/semana dados.
    Para horarios base (academic_week=0) se evalúan restricciones ALWAYS
    y WEEK_RANGE/WEEK_LIST/WEEK_PARITY que cubran la semana 0.
    """
    pt = cs.pattern_type

    # Filtro de días de semana (BD guarda 1-indexed: Lunes=1...Viernes=5)
    db_days = [int(d) - 1 for d in cs.days_of_week] if cs.days_of_week else []
    if db_days and day_of_week not in db_days:
        return False

    # Filtro de turnos (BD guarda 1-indexed: T1=1...T6=6)
    db_slots = [int(s) - 1 for s in cs.slots] if cs.slots else []
    if db_slots and (slot_index - 1) not in db_slots:
        return False

    # Filtro de franja horaria
    if cs.time_of_day == ConstraintSchedule.TimeOfDay.MORNING and slot_index > 3:
        return False
    if cs.time_of_day == ConstraintSchedule.TimeOfDay.AFTERNOON and slot_index < 4:
        return False

    if pt == ConstraintSchedule.PatternType.ALWAYS:
        return True
    if pt == ConstraintSchedule.PatternType.WEEK_RANGE:
        wf = cs.week_from or 0
        wt = cs.week_to or 999
        return wf <= academic_week <= wt
    if pt == ConstraintSchedule.PatternType.WEEK_LIST:
        return academic_week in (cs.week_numbers or [])
    if pt == ConstraintSchedule.PatternType.WEEK_PARITY:
        if cs.week_parity == ConstraintSchedule.WeekParity.EVEN:
            return academic_week % 2 == 0
        if cs.week_parity == ConstraintSchedule.WeekParity.ODD:
            return academic_week % 2 != 0
    if pt == ConstraintSchedule.PatternType.SPECIFIC_DATES:
        return False  # No aplica a horarios base

    return False


def print_separator(char='─', width=65):
    print(char * width)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_room_types(events) -> TestResult:
    """T1: Conferencias en salón, CP en aulas, Laboratorios en lab."""
    result = TestResult("Tipo de sala por actividad")

    for ae in events:
        result.checked += 1
        de   = ae.docent_event
        act  = de.activity
        room = de.room

        if not act or not room:
            continue

        required_type = ROOM_TYPE_MAP.get(act.activity_type)
        if required_type is None:
            continue

        if room.room_type != required_type:
            day, slot = slot_key(ae)
            result.add(Violation(
                test="T1-TipoSala",
                period=ae.time_slot.schedule.period,
                schedule=ae.time_slot.schedule,
                description=(
                    f"{act.get_activity_type_display()} de '{act.subject}' "
                    f"en {DAY_NAME.get(day,'?')} T{slot} "
                    f"→ sala '{room.room_code}' ({room.get_room_type_display()}) "
                    f"pero debería ser {required_type}"
                )
            ))

    return result


def test_no_professor_overlap(events) -> TestResult:
    """T2: Un profesor no puede impartir dos clases DISTINTAS al mismo tiempo.
    Un mismo evento de conferencia se almacena una vez por grupo participante
    — si (subject, room, activity_type) son identicos, es el mismo evento.
    """
    result = TestResult("Sin solapamiento de profesor")

    index = defaultdict(list)
    for ae in events:
        de = ae.docent_event
        if not de or not de.professor:
            continue
        period_id = ae.time_slot.schedule.period_id
        key = (period_id, de.professor_id, *slot_key(ae))
        index[key].append(ae)
        result.checked += 1

    for key, aes in index.items():
        if len(aes) <= 1:
            continue

        # Coleccionar firmas unicas (subject, room, activity_type)
        signatures = set()
        for a in aes:
            if a.docent_event and a.docent_event.activity:
                subj = str(a.docent_event.activity.subject_id)
                room = str(a.docent_event.room_id) if a.docent_event.room else 'none'
                act  = a.docent_event.activity.activity_type
                signatures.add((subj, room, act))

        # Una sola firma = mismo evento repetido por grupo (valido)
        if len(signatures) <= 1:
            continue

        period_id, prof_id, day, slot = key
        prof_name = aes[0].docent_event.professor.full_name
        subj_list = sorted({
            a.docent_event.activity.subject.alias or a.docent_event.activity.subject.name
            for a in aes if a.docent_event and a.docent_event.activity
        })
        result.add(Violation(
            test="T2-SolapProfesor",
            period=aes[0].time_slot.schedule.period,
            schedule=aes[0].time_slot.schedule,
            description=(
                f"Prof. '{prof_name}' imparte clases DISTINTAS en "
                f"{DAY_NAME.get(day,'?')} T{slot}: {subj_list}"
            )
        ))

    return result


def test_no_room_overlap(events) -> TestResult:
    """T3: Una sala no puede usarse para dos clases DISTINTAS al mismo tiempo.
    Un mismo evento de conferencia se almacena una vez por grupo participante
    — si (subject, professor, activity_type) son identicos, es el mismo evento.
    Ademas verifica que conferencias compartidas no superen 2 grupos por salon.
    """
    result = TestResult("Sin solapamiento de sala")

    index = defaultdict(list)
    for ae in events:
        de = ae.docent_event
        if not de or not de.room:
            continue
        period_id = ae.time_slot.schedule.period_id
        key = (period_id, de.room_id, *slot_key(ae))
        index[key].append(ae)
        result.checked += 1

    for key, aes in index.items():
        if len(aes) <= 1:
            continue

        # Firmas unicas (subject, professor, activity_type)
        signatures = set()
        for a in aes:
            if a.docent_event and a.docent_event.activity:
                subj = str(a.docent_event.activity.subject_id)
                prof = str(a.docent_event.professor_id) if a.docent_event.professor else 'none'
                act  = a.docent_event.activity.activity_type
                signatures.add((subj, prof, act))

        if len(signatures) <= 1:
            # Mismo evento — verificar limite de 2 grupos por salon
            groups = [str(a.time_slot.schedule.group) for a in aes]
            if len(groups) > 2:
                period_id, room_id, day, slot = key
                room_code = aes[0].docent_event.room.room_code
                subj_name = (aes[0].docent_event.activity.subject.alias or
                             aes[0].docent_event.activity.subject.name
                             if aes[0].docent_event and aes[0].docent_event.activity else '?')
                result.add(Violation(
                    test="T3-SolapSala",
                    period=aes[0].time_slot.schedule.period,
                    schedule=aes[0].time_slot.schedule,
                    description=(
                        f"Sala '{room_code}' tiene {len(groups)} grupos en conferencia de "
                        f"{subj_name} en {DAY_NAME.get(day,'?')} T{slot} "
                        f"(maximo permitido: 2): {groups}"
                    )
                ))
            continue

        period_id, room_id, day, slot = key
        room_code = aes[0].docent_event.room.room_code
        groups    = [str(a.time_slot.schedule.group) for a in aes]
        subj_list = sorted({
            a.docent_event.activity.subject.alias or a.docent_event.activity.subject.name
            for a in aes if a.docent_event and a.docent_event.activity
        })
        result.add(Violation(
            test="T3-SolapSala",
            period=aes[0].time_slot.schedule.period,
            schedule=aes[0].time_slot.schedule,
            description=(
                f"Sala '{room_code}' tiene clases DISTINTAS en "
                f"{DAY_NAME.get(day,'?')} T{slot}: grupos={groups} materias={subj_list}"
            )
        ))

    return result


def test_no_group_overlap(events) -> TestResult:
    """T4: Un grupo no puede tener dos clases al mismo tiempo."""
    result = TestResult("Sin solapamiento de grupo")

    index = defaultdict(list)
    for ae in events:
        group = ae.time_slot.schedule.group
        if not group:
            continue
        period_id = ae.time_slot.schedule.period_id
        key = (period_id, str(group.id), *slot_key(ae))
        index[key].append(ae)
        result.checked += 1

    for key, aes in index.items():
        if len(aes) > 1:
            period_id, group_id, day, slot = key
            group_code = str(aes[0].time_slot.schedule.group)
            subjects   = [a.docent_event.activity.subject.alias or
                          a.docent_event.activity.subject.name
                          for a in aes if a.docent_event and a.docent_event.activity]
            result.add(Violation(
                test="T4-SolapGrupo",
                period=aes[0].time_slot.schedule.period,
                schedule=aes[0].time_slot.schedule,
                description=(
                    f"Grupo '{group_code}' tiene {len(aes)} clases en "
                    f"{DAY_NAME.get(day,'?')} T{slot}: {subjects}"
                )
            ))

    return result


def test_unavailability_constraints(events) -> TestResult:
    """T5: Restricciones de indisponibilidad (UNAVAILABILITY)."""
    result = TestResult("Restricciones UNAVAILABILITY")

    constraints = (
        Constraint.objects
        .filter(constraint_type=Constraint.ConstraintType.UNAVAILABILITY, is_active=True)
        .prefetch_related('schedules')
    )

    for ae in events:
        result.checked += 1
        de    = ae.docent_event
        day   = ae.time_slot.academic_day.date.weekday()
        slot  = ae.time_slot.slot_index
        week  = ae.time_slot.academic_day.academic_week_number or 0

        for c in constraints:
            # Determinar si el evento es objetivo de la restricción
            is_target = False
            target_label = ''

            if c.professor and de and de.professor and de.professor == c.professor:
                is_target = True
                target_label = f"Prof. '{c.professor.full_name}'"
            elif c.room and de and de.room and de.room == c.room:
                is_target = True
                target_label = f"Sala '{c.room.room_code}'"
            elif c.group and ae.time_slot.schedule.group == c.group:
                is_target = True
                target_label = f"Grupo '{c.group.group_code}'"
            elif c.subject and de and de.activity and de.activity.subject == c.subject:
                is_target = True
                target_label = f"Asignatura '{c.subject}'"

            if not is_target:
                continue

            # Evaluar si algún ConstraintSchedule aplica a este slot
            for cs in c.schedules.all():
                if constraint_applies_to_slot(cs, day, slot, week):
                    result.add(Violation(
                        test="T5-Indisponibilidad",
                        period=ae.time_slot.schedule.period,
                        schedule=ae.time_slot.schedule,
                        description=(
                            f"{target_label} tiene clase en {DAY_NAME.get(day,'?')} T{slot} "
                            f"pero la restricción '{c.name}' lo marca como no disponible"
                        ),
                        severity='ERROR'
                    ))
                    break

    return result


def test_room_assignment_constraints(events) -> TestResult:
    """T6: Restricciones de asignacion fija de local (ROOM_ASSIGNMENT).
    Si la sala requerida es incompatible con el tipo de actividad
    (ej. sala tipo S para una CP que debe ir en Aula), se reporta como AVISO
    de restriccion inviable en lugar de ERROR al horario.
    """
    result = TestResult("Restricciones ROOM_ASSIGNMENT")

    # Mapa directo: activity_type (valor BD) -> room_type (valor BD)
    ACTIVITY_ROOM_TYPE = {
        Activity.ActivityType.CONFERENCE:      Room.RoomType.CONFERENCE_ROOM,
        Activity.ActivityType.PRACTICAL_CLASS: Room.RoomType.CLASSROOM,
        Activity.ActivityType.LABORATORY:      Room.RoomType.LABORATORY,
    }

    constraints = (
        Constraint.objects
        .filter(constraint_type=Constraint.ConstraintType.ROOM_ASSIGNMENT, is_active=True)
        .select_related('subject', 'professor', 'room')
        .prefetch_related('schedules')
    )

    for ae in events:
        result.checked += 1
        de   = ae.docent_event
        if not de:
            continue
        day  = ae.time_slot.academic_day.date.weekday()
        slot = ae.time_slot.slot_index
        week = ae.time_slot.academic_day.academic_week_number or 0

        for c in constraints:
            is_target = False
            target_label = ''
            required_room = None

            if c.subject and de.activity and de.activity.subject == c.subject:
                is_target = True
                target_label = f"Asignatura '{c.subject}'"
                required_room = c.room
            elif c.professor and de.professor and de.professor == c.professor:
                is_target = True
                target_label = f"Prof. '{c.professor.full_name}'"
                required_room = c.room

            if not is_target or not required_room:
                continue

            for cs in c.schedules.all():
                if constraint_applies_to_slot(cs, day, slot, week):
                    if de.room != required_room:
                        # Verificar si la sala requerida es compatible
                        # con el tipo de actividad
                        act_type_val = de.activity.activity_type if de.activity else ''
                        required_room_type = ACTIVITY_ROOM_TYPE.get(act_type_val, '')
                        is_incompatible = (
                            bool(required_room_type)
                            and required_room.room_type != required_room_type
                        )
                        if is_incompatible:
                            result.add(Violation(
                                test="T6-SalaFija",
                                period=ae.time_slot.schedule.period,
                                schedule=ae.time_slot.schedule,
                                description=(
                                    f"RESTRICCION INVIABLE: {target_label} tiene actividad "
                                    f"'{act_type_val}' que requiere sala tipo "
                                    f"'{required_room_type}', pero la restriccion exige "
                                    f"'{required_room.room_code}' "
                                    f"(tipo: {required_room.get_room_type_display()}). "
                                    f"El GA la ignora correctamente."
                                ),
                                severity='WARN'
                            ))
                        else:
                            result.add(Violation(
                                test="T6-SalaFija",
                                period=ae.time_slot.schedule.period,
                                schedule=ae.time_slot.schedule,
                                description=(
                                    f"{target_label} en {DAY_NAME.get(day,'?')} T{slot}: "
                                    f"sala asignada='{de.room.room_code if de.room else 'ninguna'}' "
                                    f"pero la restriccion exige '{required_room.room_code}'"
                                ),
                                severity='ERROR'
                            ))
                    break

    return result


def test_time_slot_preference(events) -> TestResult:
    """T7: Restricciones de preferencia de franja horaria (aviso, no error)."""
    result = TestResult("Preferencias de franja horaria")

    constraints = (
        Constraint.objects
        .filter(constraint_type=Constraint.ConstraintType.TIME_SLOT_PREFERENCE, is_active=True)
        .prefetch_related('schedules')
    )

    for ae in events:
        result.checked += 1
        de   = ae.docent_event
        day  = ae.time_slot.academic_day.date.weekday()
        slot = ae.time_slot.slot_index
        week = ae.time_slot.academic_day.academic_week_number or 0

        for c in constraints:
            is_target = False
            target_label = ''

            if c.professor and de and de.professor and de.professor == c.professor:
                is_target = True
                target_label = f"Prof. '{c.professor.full_name}'"
            elif c.group and ae.time_slot.schedule.group == c.group:
                is_target = True
                target_label = f"Grupo '{c.group.group_code}'"
            elif c.subject and de and de.activity and de.activity.subject == c.subject:
                is_target = True
                target_label = f"Asignatura '{c.subject}'"

            if not is_target:
                continue

            # La preferencia define un patrón donde SÍ debería estar;
            # si no está en ese patrón, es un aviso (no error).
            for cs in c.schedules.all():
                preferred_slots = cs.slots or []
                preferred_days  = cs.days_of_week or []

                if preferred_slots and slot not in preferred_slots:
                    result.add(Violation(
                        test="T7-PreferenciaFranja",
                        period=ae.time_slot.schedule.period,
                        schedule=ae.time_slot.schedule,
                        description=(
                            f"{target_label} tiene clase en T{slot} ({SLOT_LABEL[slot]}) "
                            f"pero prefiere turnos {preferred_slots} "
                            f"según '{c.name}'"
                        ),
                        severity='WARN'
                    ))
                    break

    return result


def test_referential_integrity(events) -> TestResult:
    """T8: Integridad referencial básica."""
    result = TestResult("Integridad referencial")

    for ae in events:
        result.checked += 1
        de = ae.docent_event

        if not de:
            result.add(Violation(
                test="T8-Integridad",
                period=ae.time_slot.schedule.period,
                schedule=ae.time_slot.schedule,
                description=f"AssignedEvent {ae.id} no tiene DocentEvent ni NonDocentEvent",
                severity='ERROR'
            ))
            continue

        if not de.activity:
            result.add(Violation(
                test="T8-Integridad",
                period=ae.time_slot.schedule.period,
                schedule=ae.time_slot.schedule,
                description=f"DocentEvent {de.id} no tiene Activity asignada",
                severity='ERROR'
            ))

        if not de.professor:
            result.add(Violation(
                test="T8-Integridad",
                period=ae.time_slot.schedule.period,
                schedule=ae.time_slot.schedule,
                description=f"DocentEvent {de.id} (act={de.activity}) no tiene profesor",
                severity='WARN'
            ))

        if not de.room:
            result.add(Violation(
                test="T8-Integridad",
                period=ae.time_slot.schedule.period,
                schedule=ae.time_slot.schedule,
                description=f"DocentEvent {de.id} (act={de.activity}) no tiene sala asignada",
                severity='WARN'
            ))

    return result


# ── Ejecución principal ───────────────────────────────────────────────────────

print()
print_separator('═')
print("  TEST DE RESTRICCIONES — HORARIOS BASE")
print_separator('═')

events = list(get_all_assigned_events())
schedules_count = Schedule.objects.filter(is_base=True).count()
periods_count   = Period.objects.filter(is_active=True).count()

print(f"\n  Períodos activos    : {periods_count}")
print(f"  Horarios base en BD : {schedules_count}")
print(f"  Eventos cargados    : {len(events)}")

if not events:
    print("\n  [AVISO]  No hay eventos en la BD. Genera los horarios primero.")
    print("     Ejecuta: exec(open('generate_all_schedules.py').read())")
    print_separator('═')
else:
    print()
    tests = [
        test_referential_integrity(events),
        test_room_types(events),
        test_no_professor_overlap(events),
        test_no_room_overlap(events),
        test_no_group_overlap(events),
        test_unavailability_constraints(events),
        test_room_assignment_constraints(events),
        test_time_slot_preference(events),
    ]

    # ── Sumario ───────────────────────────────────────────────────────────────
    print_separator()
    print("  RESULTADOS")
    print_separator()
    for t in tests:
        print(f"  {t.summary()}")

    total_errors = sum(
        len([v for v in t.violations if v.severity == 'ERROR']) for t in tests
    )
    total_warns  = sum(
        len([v for v in t.violations if v.severity == 'WARN'])  for t in tests
    )

    print_separator()
    print(f"  Total errores : {total_errors}")
    print(f"  Total avisos  : {total_warns}")

    # ── Detalle de violaciones ────────────────────────────────────────────────
    has_violations = any(t.violations for t in tests)
    if has_violations:
        print()
        print_separator()
        print("  DETALLE DE VIOLACIONES")
        print_separator()

        for t in tests:
            if not t.violations:
                continue
            errors = [v for v in t.violations if v.severity == 'ERROR']
            warns  = [v for v in t.violations if v.severity == 'WARN']
            print(f"\n  {t.name}:")
            for v in errors + warns:
                print(str(v))

    print_separator('═')

    if total_errors == 0:
        print("  [PERFECTO] TODOS LOS TESTS PASARON — Los horarios cumplen las restricciones.")
    else:
        print(f"  [AVISO]  HAY {total_errors} VIOLACIONES que deben corregirse.")
    print_separator('═')
    print()