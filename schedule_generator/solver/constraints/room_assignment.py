"""
Room assignment constraint:
"Activity X of subject Y must always be held in room Z."
This is a HARD constraint — penalty is PENALTY_HARD.
"""
from typing import Any, List
from ..interfaces.constraint_interface import ConstraintInterface
from ..dto.turn import Turn
from ..schedule import PENALTY_HARD


class RoomAssignmentConstraint(ConstraintInterface):
    """
    Penalizes any turn of (subject_alias, activity_type) that is NOT
    placed in the required room.
    """

    def __init__(self, orm_constraint: Any, orm_schedules: List[Any]):
        super().__init__(
            constraint_type='ROOM_ASSIGNMENT',
            rule_data={},
            priority=5,  # Always hard
        )
        self.subject_alias  = None
        self.activity_type  = None   # 'C' | 'CP' | 'L' | None (all types)
        self.required_room_id = None

        if orm_constraint.subject:
            self.subject_alias = orm_constraint.subject.alias or orm_constraint.subject.name
        if orm_constraint.room:
            self.required_room_id = orm_constraint.room.id

        # activity_type can be stored in notes as "C", "CP", or "L"
        # If notes is empty → applies to ALL activity types of that subject
        notes = (orm_constraint.notes or '').strip().upper()
        if notes in ('C', 'CP', 'L'):
            self.activity_type = notes

        # Store for _get_fixed_room() in schedule.py
        self.rule_data = {
            'subject_alias': self.subject_alias,
            'activity_type': self.activity_type,
            'room_id': str(self.required_room_id) if self.required_room_id else None,
        }

    def evaluate(self, turn: Turn, day: int, slot: int) -> int:
        if turn.is_empty_slot():
            return 0
        if not self.subject_alias or turn.subject_alias != self.subject_alias:
            return 0
        if self.activity_type and turn.activity_type != self.activity_type:
            return 0
        if not turn.room:
            return PENALTY_HARD
        if str(turn.room.id) != str(self.required_room_id):
            return PENALTY_HARD
        return 0