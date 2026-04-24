"""
schedule_service.py

Central service for automatic schedule generation and selective regeneration.

Public API:
    ensure_all_active_periods()          — generate missing schedules on startup
    regenerate_from_week(period, week)   — regenerate week N onwards for a period
    regenerate_period(period)            — regenerate all schedules for a period
    regenerate_all_active_periods()      — regenerate all active periods completely
"""

import logging
from datetime import timedelta
from typing import Optional

from apps.data_management.models import (
    Period, Group, AcademicDay, Schedule, TimeSlot,
    DocentEvent, AssignedEvent, TeachingActivityAssignment,
    Activity, Room as RoomModel,
)
from schedule_generator.main import (
    generate_schedule_for_period, _map_rooms, _map_turns, _map_constraints,
)
from schedule_generator.solver import schedule
from schedule_generator.solver.schedule_manager import ScheduleManager
from schedule_generator.solver.schedule import DAYS, TIME_SLOTS_PER_DAY

log = logging.getLogger(__name__)

SLOT_LABELS = {
    0: '8:00 - 9:20',   1: '9:30 - 10:50',  2: '11:00 - 12:20',
    3: '12:30 - 13:50', 4: '14:00 - 15:20', 5: '15:30 - 16:50',
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _base_schedule_has_timeslots(period: Period) -> bool:
    """
    Devuelve True solo si el período tiene horario base con timeslots
    Y esos timeslots tienen AssignedEvents (es decir, fue persistido correctamente).
    """
    base = Schedule.objects.filter(period=period, is_base=True).first()
    if not base:
        return False
    ts = TimeSlot.objects.filter(schedule=base).first()
    if not ts:
        return False
    return AssignedEvent.objects.filter(time_slot__schedule=base).exists()


def _weekly_schedule_exists(period: Period, week_monday) -> bool:
    """Devuelve True si ya existe el horario de la semana que empieza en week_monday."""
    monday_day = AcademicDay.objects.filter(period=period, date=week_monday).first()
    if not monday_day:
        return False
    sched = Schedule.objects.filter(
        period=period, is_base=False, academic_week=monday_day
    ).first()
    if not sched:
        return False
    return TimeSlot.objects.filter(schedule=sched).exists()


def _persist_weekly_from_base(period: Period, week_monday, week_number: int):
    """
    Genera el horario de una semana específica a partir del horario base.

    Si existen restricciones activas para esa semana (UNAVAILABILITY, etc.),
    re-ejecuta el GA seeded desde el base con esas restricciones aplicadas.
    Si no hay restricciones específicas, copia el patrón del base directamente.
    """
    from datetime import date as date_type

    base_schedules = list(Schedule.objects.filter(period=period, is_base=True))
    if not base_schedules:
        raise ValueError(f"No hay horario base para {period}.")

    # Crear / recuperar los AcademicDays de esta semana
    week_days = {}
    for d in range(DAYS):
        day_date = week_monday + timedelta(days=d)
        academic_day, _ = AcademicDay.objects.get_or_create(
            period=period,
            date=day_date,
            defaults={'is_active': True, 'academic_week_number': week_number},
        )
        week_days[d] = academic_day

    monday_academic_day = week_days[0]

    # Verificar si hay restricciones específicas para esta semana
    week_constraints = _get_week_specific_constraints(period, week_number)
    has_week_constraints = len(week_constraints) > 0

    if has_week_constraints:
        log.info(
            '[weekly] Semana %d de %s tiene %d restricciones específicas — re-ejecutando GA.',
            week_number, period, len(week_constraints),
        )
        _persist_weekly_via_ga(period, week_monday, week_number, week_days, week_constraints)
    else:
        log.info(
            '[weekly] Semana %d de %s sin restricciones específicas — copiando base.',
            week_number, period,
        )
        _persist_weekly_copy_base(period, base_schedules, week_days, monday_academic_day)


def _persist_weekly_copy_base(period, base_schedules, week_days, monday_academic_day):
    """Copia el patrón base a los AcademicDays de la semana específica."""
    for base_sched in base_schedules:
        group = base_sched.group

        # Borrar horario semanal previo si existía
        Schedule.objects.filter(
            period=period, group=group,
            is_base=False, academic_week=monday_academic_day,
        ).delete()

        weekly_sched = Schedule.objects.create(
            period=period,
            group=group,
            is_base=False,
            academic_week=monday_academic_day,
            score=base_sched.score,
        )

        base_timeslots = TimeSlot.objects.filter(schedule=base_sched).select_related(
            'academic_day'
        ).prefetch_related(
            'assignedevent_set__docent_event__professor',
            'assignedevent_set__docent_event__activity',
            'assignedevent_set__docent_event__room',
        )

        for ts in base_timeslots:
            weekday = ts.academic_day.date.weekday()  # 0=Lunes … 4=Viernes
            if weekday >= DAYS:
                continue

            new_ts = TimeSlot.objects.create(
                schedule=weekly_sched,
                academic_day=week_days[weekday],
                slot_index=ts.slot_index,
            )

            for ae in ts.assignedevent_set.filter(docent_event__isnull=False):
                de = ae.docent_event
                new_de = DocentEvent.objects.create(
                    professor=de.professor,
                    activity=de.activity,
                    room=de.room,
                )
                AssignedEvent.objects.create(time_slot=new_ts, docent_event=new_de)


def _persist_weekly_via_ga(period, week_monday, week_number, week_days, week_constraints):
    """Re-ejecuta el GA para la semana, seeded desde el base, con restricciones de esa semana."""
    rooms       = _map_rooms(period)
    all_turns   = _map_turns(period)
    base_constraints  = _map_constraints(period)
    combined    = base_constraints + week_constraints

    manager = ScheduleManager(rooms=rooms, all_turns=all_turns, constraints=combined)

    # Reconstruir el base Schedule como punto de partida del GA semanal
    from schedule_generator.solver.schedule import Schedule as ScheduleGA
    base_sched_obj = ScheduleGA(rooms=rooms, constraints=combined, unscheduled_load=all_turns)
    weekly_result = manager.generate_weekly_override(
        week_number=week_number,
        week_constraints=week_constraints,
        base_schedule=base_sched_obj,
    )

    monday_academic_day = week_days[0]
    group_matrices = weekly_result.split_by_group()
    score = weekly_result.get_score()

    for group_code, matrix in group_matrices.items():
        group = Group.objects.filter(group_code=group_code, period=period).first()
        if not group:
            continue

        Schedule.objects.filter(
            period=period, group=group,
            is_base=False, academic_week=monday_academic_day,
        ).delete()

        weekly_sched = Schedule.objects.create(
            period=period, group=group,
            is_base=False, academic_week=monday_academic_day,
            score=score,
        )

        for d in range(DAYS):
            for t in range(TIME_SLOTS_PER_DAY):
                turn = matrix[d][t] if matrix[d] else None
                if turn is None or turn.is_empty_slot():
                    continue

                assignment = TeachingActivityAssignment.objects.filter(
                    id__in=turn.source_assignment_ids
                ).select_related('professor').first()
                if not assignment:
                    continue

                time_slot = TimeSlot.objects.create(
                    schedule=weekly_sched,
                    academic_day=week_days[d],
                    slot_index=t + 1,
                )
                activity, _ = Activity.objects.get_or_create(
                    subject=assignment.subject,
                    activity_type=turn.activity_type,
                    defaults={'title': f'{assignment.subject.alias or assignment.subject.name} — {turn.activity_type}'},
                )
                room_obj = None
                if turn.room:
                    room_obj = RoomModel.objects.filter(room_code=turn.room.number).first()

                de = DocentEvent.objects.create(
                    professor=assignment.professor, activity=activity, room=room_obj,
                )
                AssignedEvent.objects.create(time_slot=time_slot, docent_event=de)


def _get_week_specific_constraints(period: Period, week_number: int) -> list:
    """
    Devuelve las restricciones activas que aplican específicamente a esta semana
    (WEEK_RANGE o WEEK_LIST) y no a todas las semanas (ALWAYS).
    """
    from schedule_generator.main import _map_constraints
    from apps.data_management.models import Constraint, ConstraintSchedule

    all_constraints = _map_constraints(period)
    week_specific = []

    # ConstraintSchedules con WEEK_RANGE o WEEK_LIST que incluyan esta semana
    week_sched_ids = set(
        ConstraintSchedule.objects.filter(
            pattern_type__in=['WEEK_RANGE', 'WEEK_LIST']
        ).filter(
            week_from__lte=week_number, week_to__gte=week_number
        ).values_list('constraint_id', flat=True)
    ) | set(
        cs.constraint_id
        for cs in ConstraintSchedule.objects.filter(pattern_type='WEEK_LIST')
        if week_number in (cs.week_numbers or [])
    )

    for c in all_constraints:
        raw = getattr(c, '_constraint', None)
        if raw and str(raw.id) in {str(i) for i in week_sched_ids}:
            week_specific.append(c)

    return week_specific


def ensure_all_active_periods():
    """
    Called on system startup (landing page / selector first load).
    Generates the base schedule for every active period that has none yet.
    Already-generated periods are left untouched.
    """
    errors = []
    for period in Period.objects.filter(is_active=True):
        has_base = Schedule.objects.filter(period=period, is_base=True).exists()
        if not has_base:
            try:
                _generate_base_for_period(period)
                log.info(f'[ensure] Base schedule generated for {period}')
            except Exception as e:
                msg = f'Error generating base schedule for {period}: {e}'
                log.error(msg)
                errors.append(msg)
    return errors


def regenerate_period(period: Period):
    """
    Fully regenerate all schedules (base + all weeks) for a period.
    Called when something structural changes: rooms, assignments, groups.
    """
    errors = []
    try:
        _delete_all_schedules_for_period(period)
        _generate_base_for_period(period)
        log.info(f'[regen] Full regeneration done for {period}')
    except Exception as e:
        msg = f'Error regenerating {period}: {e}'
        log.error(msg)
        errors.append(msg)
    return errors


def regenerate_from_week(period: Period, from_week: int):
    """
    Regenerate schedules from week `from_week` onwards for a period.
    Called when a constraint changes that affects specific weeks.
    The base schedule is always regenerated too since it's the seed.
    """
    errors = []
    try:
        _delete_weekly_schedules_from(period, from_week)
        _delete_base_schedules_for_period(period)
        _generate_base_for_period(period)
        log.info(f'[regen] Regenerated from week {from_week} for {period}')
    except Exception as e:
        msg = f'Error regenerating from week {from_week} for {period}: {e}'
        log.error(msg)
        errors.append(msg)
    return errors


def regenerate_all_active_periods():
    """Regenerate all active periods completely."""
    errors = []
    for period in Period.objects.filter(is_active=True):
        errors.extend(regenerate_period(period))
    return errors


# ---------------------------------------------------------------------------
# Internal helpers — generation
# ---------------------------------------------------------------------------

def _generate_base_for_period(period: Period):
    """Generate and persist the base schedule for a period."""
    result = generate_schedule_for_period(period_id=period.id)
    _persist_base_schedule(period, result)


def _persist_base_schedule(period: Period, result):
    """Persist base schedule result to DB."""
    base_days = _get_or_create_base_academic_days(period)

    for group_code, matrix in result.group_matrices.items():
        group = Group.objects.filter(group_code=group_code, period=period).first()
        if not group:
            continue

        Schedule.objects.filter(period=period, group=group, is_base=True).delete()

        schedule = Schedule.objects.create(
            period=period,
            group=group,
            is_base=True,
            score=result.base_schedule.get_score(),
        )

        for d in range(DAYS):
            for t in range(TIME_SLOTS_PER_DAY):
                turn = matrix[d][t] if matrix[d] else None
                if turn is None or turn.is_empty_slot():
                    continue

                assignment = TeachingActivityAssignment.objects.filter(
                    id__in=turn.source_assignment_ids
                ).select_related('professor').first()
                if not assignment:
                    continue

                time_slot = TimeSlot.objects.create(
                    schedule=schedule,
                    academic_day=base_days[d],
                    slot_index=t + 1,
                )

                activity, _ = Activity.objects.get_or_create(
                    subject=assignment.subject,
                    activity_type=assignment.activity_type,
                    defaults={
                        'title': f'{assignment.subject.alias or assignment.subject.name} — {assignment.get_activity_type_display()}'
                    }
                )

                room_obj = None
                if turn.room:
                    room_obj = RoomModel.objects.filter(room_code=turn.room.number).first()

                docent_event = DocentEvent.objects.create(
                    professor=assignment.professor,
                    activity=activity,
                    room=room_obj,
                )
                AssignedEvent.objects.create(
                    time_slot=time_slot,
                    docent_event=docent_event,
                )


def _get_or_create_base_academic_days(period: Period) -> dict:
    """Get or create 5 virtual AcademicDays (week=0) for the base schedule."""
    from datetime import date
    base_days = {}
    if period.start_date:
        first_week_monday = period.start_date - timedelta(days=period.start_date.weekday())
        monday = first_week_monday - timedelta(days=7)
    else:
        monday = date(2000, 1, 3)

    for d in range(DAYS):
        day_date = monday + timedelta(days=d)
        academic_day, _ = AcademicDay.objects.get_or_create(
            period=period, date=day_date,
            defaults={'is_active': True, 'academic_week_number': 0}
        )
        base_days[d] = academic_day
    return base_days


# ---------------------------------------------------------------------------
# Internal helpers — deletion
# ---------------------------------------------------------------------------

def _delete_all_schedules_for_period(period: Period):
    """Delete all schedules (base + weekly) for a period."""
    for s in Schedule.objects.filter(period=period):
        _delete_schedule_cascade(s)


def _delete_base_schedules_for_period(period: Period):
    """Delete only base schedules for a period."""
    for s in Schedule.objects.filter(period=period, is_base=True):
        _delete_schedule_cascade(s)


def _delete_weekly_schedules_from(period: Period, from_week: int):
    """Delete weekly schedules starting from `from_week`."""
    schedules = Schedule.objects.filter(
        period=period,
        is_base=False,
        academic_week__academic_week_number__gte=from_week,
    )
    for s in schedules:
        _delete_schedule_cascade(s)


def _delete_schedule_cascade(schedule: Schedule):
    """Delete a schedule and all its related time slots and events."""
    for ts in TimeSlot.objects.filter(schedule=schedule):
        for ae in AssignedEvent.objects.filter(time_slot=ts):
            if ae.docent_event:
                ae.docent_event.delete()
            ae.delete()
        ts.delete()
    schedule.delete()


# ---------------------------------------------------------------------------
# Utility — determine affected periods from a changed object
# ---------------------------------------------------------------------------

def get_affected_periods_from_constraint(constraint) -> list:
    """Return active periods affected by a constraint."""
    from apps.data_management.models import Period
    if constraint.professor:
        period_ids = TeachingActivityAssignment.objects.filter(
            professor=constraint.professor
        ).values_list('subject__period_id', flat=True).distinct()
        return list(Period.objects.filter(id__in=period_ids, is_active=True))
    if constraint.subject:
        return list(Period.objects.filter(
            id=constraint.subject.period_id, is_active=True
        ))
    if constraint.group:
        return list(Period.objects.filter(
            id=constraint.group.period_id, is_active=True
        ))
    if constraint.room:
        return list(Period.objects.filter(is_active=True))
    return []


def get_earliest_week_from_constraint(constraint) -> int:
    """Return the earliest week number affected by a constraint."""
    schedules = list(constraint.schedules.all())
    if not schedules:
        return 1
    min_week = None
    for s in schedules:
        if s.pattern_type == 'ALWAYS':
            return 1
        if s.pattern_type == 'WEEK_RANGE' and s.week_from:
            w = s.week_from
        elif s.pattern_type == 'WEEK_LIST' and s.week_numbers:
            w = min(int(x) for x in s.week_numbers)
        else:
            return 1
        if min_week is None or w < min_week:
            min_week = w
    return min_week or 1