"""
Unavailability constraint: a professor, room, group or subject
cannot be used at certain times.
"""
from typing import List, Any
from ..interfaces.constraint_interface import ConstraintInterface
from ..dto.turn import Turn


class UnavailabilityConstraint(ConstraintInterface):
    """
    Penalizes turns that land on a blocked time slot.

    rule_data keys (set from ORM Constraint + ConstraintSchedule):
        target_type : 'PROFESSOR' | 'ROOM' | 'GROUP' | 'SUBJECT'
        target_id   : UUID of the target entity
        blocked_slots: List of (day, slot) tuples that are unavailable
                       (pre-computed from ConstraintSchedule patterns)
    """

    def __init__(self, orm_constraint: Any, orm_schedules: List[Any]):
        super().__init__(
            constraint_type='UNAVAILABILITY',
            rule_data={},
            priority=orm_constraint.priority,
        )
        self.target_type = orm_constraint.target_type
        self.target_id = self._resolve_target_id(orm_constraint)
        self.blocked_slots = self._compute_blocked_slots(orm_schedules)

    def _resolve_target_id(self, c: Any):
        if c.target_type == 'PROFESSOR' and c.professor:
            return c.professor.id
        if c.target_type == 'ROOM' and c.room:
            return c.room.id
        if c.target_type == 'GROUP' and c.group:
            return c.group.id
        if c.target_type == 'SUBJECT' and c.subject:
            return c.subject.id
        return None

    def _compute_blocked_slots(self, schedules: List[Any]) -> set:
        """
        Convert ConstraintSchedule ORM objects into a set of (day, slot) tuples.
        day:  0=Monday … 4=Friday
        slot: 0-5
        """
        blocked = set()
        for s in schedules:
            days = [int(d) - 1 for d in s.days_of_week] if s.days_of_week else list(range(5))
            slots = [int(sl) - 1 for sl in s.slots] if s.slots else list(range(6))

            if s.pattern_type == 'ALWAYS':
                for d in days:
                    for sl in slots:
                        blocked.add((d, sl))

            elif s.pattern_type in ('WEEK_LIST', 'WEEK_RANGE', 'WEEK_PARITY', 'SPECIFIC_DATES'):
                # For base schedule generation we treat these as ALWAYS
                # (week-specific resolution happens in weekly override generation)
                for d in days:
                    for sl in slots:
                        blocked.add((d, sl))

        return blocked

    def evaluate(self, turn: Turn, day: int, slot: int) -> int:
        if turn.is_empty_slot():
            return 0
        if (day, slot) not in self.blocked_slots:
            return 0

        # Check if this turn involves the constrained entity
        if self.target_type == 'PROFESSOR':
            if turn.professor_id != self.target_id:
                return 0
        elif self.target_type == 'ROOM':
            if not turn.room or turn.room.id != self.target_id:
                return 0
        elif self.target_type == 'GROUP':
            if str(self.target_id) not in [str(gc) for gc in turn.group_codes]:
                return 0
        elif self.target_type == 'SUBJECT':
            # target_id is subject UUID; we only have alias in Turn
            # For now skip subject-level unavailability (needs alias→id map)
            return 0

        return self.penalty_base