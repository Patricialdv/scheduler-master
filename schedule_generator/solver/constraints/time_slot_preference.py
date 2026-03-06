"""
Time-of-day preference constraint:
e.g. "subject X should always be in the afternoon"
"""
from typing import List, Any
from ..interfaces.constraint_interface import ConstraintInterface
from ..dto.turn import Turn

MORNING_SLOTS = {0, 1, 2}    # slots 1-3
AFTERNOON_SLOTS = {3, 4, 5}  # slots 4-6


class TimeSlotPreferenceConstraint(ConstraintInterface):
    """
    Penalizes turns placed in the wrong time-of-day.

    Supports target_type: PROFESSOR, GROUP, SUBJECT.
    rule_data:
        time_of_day: 'MORNING' | 'AFTERNOON'
    """

    def __init__(self, orm_constraint: Any, orm_schedules: List[Any]):
        super().__init__(
            constraint_type='TIME_SLOT_PREFERENCE',
            rule_data={},
            priority=orm_constraint.priority,
        )
        self.target_type = orm_constraint.target_type
        self.target_id = self._resolve_target_id(orm_constraint)

        # Determine preferred and forbidden slot sets from schedules
        self.forbidden_slots = self._compute_forbidden_slots(orm_schedules)

    def _resolve_target_id(self, c: Any):
        if c.target_type == 'PROFESSOR' and c.professor:
            return c.professor.id
        if c.target_type == 'GROUP' and c.group:
            return c.group.id
        if c.target_type == 'SUBJECT' and c.subject:
            return c.subject.id
        return None

    def _compute_forbidden_slots(self, schedules: List[Any]) -> set:
        forbidden = set()
        for s in schedules:
            if not s.time_of_day:
                continue
            if s.time_of_day == 'MORNING':
                # Preference is MORNING → afternoon slots are forbidden
                forbidden.update(AFTERNOON_SLOTS)
            elif s.time_of_day == 'AFTERNOON':
                # Preference is AFTERNOON → morning slots are forbidden
                forbidden.update(MORNING_SLOTS)
        return forbidden

    def evaluate(self, turn: Turn, day: int, slot: int) -> int:
        if turn.is_empty_slot():
            return 0
        if slot not in self.forbidden_slots:
            return 0

        if self.target_type == 'PROFESSOR':
            if turn.professor_id != self.target_id:
                return 0
        elif self.target_type == 'GROUP':
            if str(self.target_id) not in [str(gc) for gc in turn.group_codes]:
                return 0
        elif self.target_type == 'SUBJECT':
            return 0  # Needs alias→id resolution (future improvement)

        return self.penalty_base