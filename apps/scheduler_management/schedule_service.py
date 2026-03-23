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

                time_slot = TimeSlot.objects.create(
                    schedule=schedule,
                    academic_day=base_days[d],
                    slot_index=t + 1,
                )

                assignment = TeachingActivityAssignment.objects.filter(
                    id__in=turn.source_assignment_ids
                ).select_related('professor').first()
                if not assignment:
                    continue

                activity, _ = Activity.objects.get_or_create(
                    subject=assignment.subject,
                    activity_type=turn.activity_type,
                    defaults={
                        'title': f'{assignment.subject.alias or assignment.subject.name} — {turn.activity_type}'
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
    """Get or create 5 virtual AcademicDays (week 0) for the base schedule."""
    from datetime import date
    base_days = {}
    if period.start_date:
        monday = period.start_date - timedelta(days=period.start_date.weekday())
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