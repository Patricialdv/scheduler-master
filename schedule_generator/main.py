"""
schedule_generator/main.py

Public entry point for the schedule generation system.
Fetches data from Django ORM, builds DTOs, runs the GA, and returns the result.
"""
import uuid
from typing import List, Dict, Optional

from apps.data_management.models import (
    Room as RoomModel,
    TeachingActivityAssignment,
    Period,
    Constraint,
    ConstraintSchedule,
)
from .solver.dto.room import Room as RoomDTO
from .solver.dto.turn import Turn as TurnDTO
from .solver.interfaces.constraint_interface import ConstraintInterface
from .solver.schedule_manager import generate_base_schedule, PeriodScheduleResult


# ---------------------------------------------------------------------------
# ORM → DTO mappers
# ---------------------------------------------------------------------------

def _map_rooms(period: Period) -> List[RoomDTO]:
    """All rooms available (global, not period-specific)."""
    room_type_map = {
        RoomModel.RoomType.CLASSROOM: 'A',
        RoomModel.RoomType.LABORATORY: 'L',
        RoomModel.RoomType.CONFERENCE_ROOM: 'S',
    }
    result = []
    for room in RoomModel.objects.all():
        result.append(RoomDTO(
            id=room.id,
            room_type_code=room_type_map.get(room.room_type, 'A'),
            number=room.room_code,
        ))
    return result


def _map_turns(period: Period) -> List[TurnDTO]:
    """
    Build one TurnDTO per TeachingActivityAssignment in the period.
    Assignments without a professor are skipped (cannot be scheduled).
    """
    assignments = (
        TeachingActivityAssignment.objects
        .filter(subject__period=period)
        .select_related('subject', 'group', 'professor')
    )

    turns: List[TurnDTO] = []
    for a in assignments:
        if not a.professor:
            continue  # Cannot schedule without a professor
        turns.append(TurnDTO(
            subject_alias=a.subject.alias or a.subject.name,
            group_codes=[a.group.group_code],
            activity_type=a.activity_type,
            professor_id=a.professor.id,
            source_assignment_ids=[a.id],
        ))
    return turns


def _map_constraints(period: Period) -> List[ConstraintInterface]:
    """
    Load active Constraint objects relevant to this period and convert them to
    ConstraintInterface instances the GA can evaluate.

    Supports:
        UNAVAILABILITY       → UnavailabilityConstraint
        TIME_SLOT_PREFERENCE → TimeSlotPreferenceConstraint
        ROOM_ASSIGNMENT      → RoomAssignmentConstraint
    """
    from .solver.constraints.unavailability import UnavailabilityConstraint
    from .solver.constraints.time_slot_preference import TimeSlotPreferenceConstraint
    from .solver.constraints.room_assignment import RoomAssignmentConstraint

    # Only load constraints whose target belongs to this period
    period_professor_ids = list(
        TeachingActivityAssignment.objects
        .filter(subject__period=period)
        .values_list('professor_id', flat=True)
        .distinct()
    )
    period_group_ids = list(
        period.groups.values_list('id', flat=True)
    )
    period_subject_ids = list(
        period.subjects.values_list('id', flat=True)
    )

    from django.db.models import Q
    active_constraints = (
        Constraint.objects
        .filter(is_active=True)
        .filter(
            Q(professor_id__in=period_professor_ids) |
            Q(group_id__in=period_group_ids) |
            Q(subject_id__in=period_subject_ids) |
            Q(room__isnull=False)   # Room constraints apply globally
        )
        .prefetch_related('schedules', 'subject', 'professor', 'group', 'room')
    )

    result: List[ConstraintInterface] = []
    for c in active_constraints:
        schedules = list(c.schedules.all())
        if c.constraint_type == Constraint.ConstraintType.UNAVAILABILITY:
            result.append(UnavailabilityConstraint(c, schedules))
        elif c.constraint_type == Constraint.ConstraintType.TIME_SLOT_PREFERENCE:
            result.append(TimeSlotPreferenceConstraint(c, schedules))
        elif c.constraint_type == 'ROOM_ASSIGNMENT':
            result.append(RoomAssignmentConstraint(c, schedules))

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_schedule_for_period(period_id: Optional[uuid.UUID] = None) -> PeriodScheduleResult:
    """
    Generate the base schedule for the given period (or the active one).

    Returns a PeriodScheduleResult containing:
        - base_schedule:  the full Schedule object (all groups)
        - group_matrices: Dict[group_code → 5×6 matrix]
    """
    if period_id:
        period = Period.objects.get(id=period_id)
    else:
        period = Period.objects.filter(is_active=True).first()

    if not period:
        raise ValueError("No active period found. Please activate a period first.")

    rooms = _map_rooms(period)
    turns = _map_turns(period)
    constraints = _map_constraints(period)

    if not turns:
        raise ValueError(
            f"Period '{period}' has no scheduled teaching assignments. "
            "Please add TeachingActivityAssignments before generating a schedule."
        )

    if not rooms:
        raise ValueError("No rooms available. Please add rooms before generating a schedule.")

    return generate_base_schedule(
        rooms=rooms,
        all_turns=turns,
        constraints=constraints,
    )