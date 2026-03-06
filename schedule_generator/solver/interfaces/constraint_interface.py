from typing import Dict, Any, Literal
from ..dto.turn import Turn

ConstraintType = Literal[
    'UNAVAILABILITY',
    'TIME_SLOT_PREFERENCE',
]


class ConstraintInterface:
    """
    Base class for all soft constraints evaluated by the GA.

    Each subclass implements evaluate() and returns a penalty integer.
    A return of 0 means no violation.

    The penalty magnitude should reflect the priority:
        Priority 5 (Absolute)       → use PENALTY_HARD from schedule.py (never soft)
        Priority 4 (Near-mandatory) → 50_000
        Priority 3 (Important)      → 5_000
        Priority 2 (Preference)     → 500
        Priority 1 (Desirable)      → 50
    """

    PRIORITY_PENALTIES = {
        5: 1_000_000,
        4: 50_000,
        3: 5_000,
        2: 500,
        1: 50,
    }

    def __init__(
        self,
        constraint_type: ConstraintType,
        rule_data: Dict[str, Any],
        priority: int,
    ):
        self.constraint_type = constraint_type
        self.rule_data = rule_data
        self.priority = priority
        self.penalty_base = self.PRIORITY_PENALTIES.get(priority, 500)

    def evaluate(self, turn: Turn, day: int, slot: int) -> int:
        """
        Evaluate the turn placed at (day, slot).
        Returns the penalty (0 = no violation).
        Override in subclasses.
        """
        return 0