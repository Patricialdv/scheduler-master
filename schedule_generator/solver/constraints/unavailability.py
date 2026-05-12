"""
Unavailability constraint: a professor, room, group or subject
cannot be used at certain times.
"""
from typing import List, Any
from ..interfaces.constraint_interface import ConstraintInterface
from ..dto.turn import Turn


class UnavailabilityConstraint(ConstraintInterface):

    def __init__(self, orm_constraint: Any, orm_schedules: List[Any]):
        super().__init__(
            constraint_type='UNAVAILABILITY',
            rule_data={},
            priority=orm_constraint.priority,
        )
        self.target_type   = orm_constraint.target_type
        self.target_id     = self._resolve_target_id(orm_constraint)
        self.subject_alias = self._resolve_subject_alias(orm_constraint)
        self.blocked_slots = self._compute_blocked_slots(orm_schedules)

    def _resolve_target_id(self, c: Any):
        if c.target_type == 'PROFESSOR' and c.professor:
            return c.professor.id
        if c.target_type == 'ROOM' and c.room:
            return c.room.id
        if c.target_type == 'GROUP' and c.group:
            # Store group_code (e.g. '4E1') so it matches turn.group_codes
            return c.group.group_code
        if c.target_type == 'SUBJECT' and c.subject:
            return c.subject.id
        return None

    def _resolve_subject_alias(self, c: Any):
        """For SUBJECT constraints, store the alias so we can match against Turn."""
        if c.target_type == 'SUBJECT' and c.subject:
            return c.subject.alias or c.subject.name
        return None

    def _compute_blocked_slots(self, schedules: List[Any]) -> set:
        blocked = set()
        for s in schedules:
            days  = [int(d) - 1 for d in s.days_of_week] if s.days_of_week else list(range(5))
            slots = [int(sl) - 1 for sl in s.slots]      if s.slots        else list(range(6))

            if s.pattern_type in ('ALWAYS', 'WEEK_LIST', 'WEEK_RANGE', 'WEEK_PARITY', 'SPECIFIC_DATES'):
                for d in days:
                    for sl in slots:
                        blocked.add((d, sl))
        return blocked

    def evaluate(self, turn: Turn, day: int, slot: int) -> int:
        if turn.is_empty_slot():
            return 0
        if (day, slot) not in self.blocked_slots:
            return 0

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
            # Match by alias (Turn carries subject_alias)
            if not self.subject_alias or turn.subject_alias != self.subject_alias:
                return 0

        return self.penalty_base