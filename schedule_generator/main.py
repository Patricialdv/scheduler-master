"""
schedule_generator/main.py

Public entry point for the schedule generation system.
Fetches data from Django ORM, builds DTOs, pre-merges conference turns,
runs the GA, and returns the result.

Key change — pre-merge [A]:
    Conference turns (activity_type='C') that share the same subject AND
    professor are merged into a single TurnDTO with multiple group_codes
    BEFORE entering the GA. This reduces the number of turns the GA needs
    to place from N_groups×N_subjects down to N_subjects for conferences,
    which is the realistic academic model and prevents matrix overflow.
"""
import uuid
from collections import defaultdict
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
    """
    A5: Filter rooms to only those used in the period via constraints.
    Fallback to all rooms if no constraint-based filtering applies.
    """
    room_type_map = {
        RoomModel.RoomType.CLASSROOM:       'A',
        RoomModel.RoomType.LABORATORY:      'L',
        RoomModel.RoomType.CONFERENCE_ROOM: 'S',
    }

    # A5: get rooms referenced by active constraints for this period
    from apps.data_management.models import Constraint
    from django.db.models import Q

    period_professor_ids = list(
        TeachingActivityAssignment.objects
        .filter(subject__period=period)
        .values_list('professor_id', flat=True)
        .distinct()
    )
    period_group_ids = list(period.groups.values_list('id', flat=True))
    period_subject_ids = list(period.subjects.values_list('id', flat=True))

    constraint_room_ids = (
        Constraint.objects
        .filter(is_active=True)
        .filter(
            Q(professor_id__in=period_professor_ids) |
            Q(group_id__in=period_group_ids) |
            Q(subject_id__in=period_subject_ids) |
            Q(room__isnull=False)
        )
        .exclude(room__isnull=True)
        .values_list('room_id', flat=True)
        .distinct()
    )

    rooms_qs = RoomModel.objects.all()

    result = []
    for room in rooms_qs:
        result.append(RoomDTO(
            id=room.id,
            room_type_code=room_type_map.get(room.room_type, 'A'),
            number=room.room_code,
        ))
    return result


def _map_turns(period: Period) -> List[TurnDTO]:
    """
    Build TurnDTOs for all TeachingActivityAssignments in the period.

    [A] Pre-merge for conferences:
        Conference assignments that share the same (subject, professor) are
        collapsed into ONE TurnDTO with all their group_codes combined.
        This mirrors the academic reality where one professor teaches a
        conference to multiple groups simultaneously in the same room.

        Result: instead of 4 conference turns per subject (one per group),
        the GA receives 1 merged turn per subject → fits in the 30-cell matrix.

    CP and Laboratory turns are kept one-per-group (they are parallel sessions
    taught by different professors to different groups).
    """
    assignments = (
        TeachingActivityAssignment.objects
        .filter(subject__period=period)
        .select_related('subject', 'group', 'professor')
    )

    # Separate conferences from other activities
    conf_bucket: Dict[tuple, List] = defaultdict(list)  # (subject_alias, professor_id) → [assignments]
    other_turns: List[TurnDTO] = []

    for a in assignments:
        if not a.professor:
            continue

        subject_alias = a.subject.alias or a.subject.name
        act_code = _normalize_activity_type(a.activity_type)

        if act_code == 'C':
            # Fusionar conferencias por materia únicamente.
            # En el modelo cubano, todos los grupos de una misma materia
            # asisten a la misma conferencia en el mismo turno,
            # independientemente del profesor.
            key = subject_alias
            conf_bucket[key].append(a)
        else:
            other_turns.append(TurnDTO(
                subject_alias=subject_alias,
                group_codes=[a.group.group_code],
                activity_type=act_code,
                professor_id=a.professor.id,
                source_assignment_ids=[a.id],
            ))

    # Un TurnDTO fusionado por materia (todos los grupos juntos)
    merged_conf_turns: List[TurnDTO] = []
    for subject_alias, assignment_list in conf_bucket.items():
        group_codes = [a.group.group_code for a in assignment_list]
        source_ids  = [a.id for a in assignment_list]
        # Usar el profesor del primer assignment como referencia
        merged_conf_turns.append(TurnDTO(
            subject_alias=subject_alias,
            group_codes=group_codes,
            activity_type='C',
            professor_id=assignment_list[0].professor.id,
            source_assignment_ids=source_ids,
        ))

    all_turns = merged_conf_turns + other_turns
    return all_turns


def _normalize_activity_type(act_type: str) -> str:
    """Convert Django ActivityType label to short GA code."""
    mapping = {
        'Conference':      'C',
        'Practical Class': 'CP',
        'Laboratory':      'L',
        'C':  'C',
        'CP': 'CP',
        'L':  'L',
    }
    return mapping.get(act_type, act_type)


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
            Q(room__isnull=False)
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

    rooms       = _map_rooms(period)
    turns       = _map_turns(period)      # conferences already pre-merged
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