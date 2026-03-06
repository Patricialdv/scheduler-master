import copy
from typing import List, Dict, Optional
from .schedule import Schedule
from .schedule_creator import ScheduleCreator
from .dto.turn import Turn
from .dto.room import Room
from .interfaces.constraint_interface import ConstraintInterface


class PeriodScheduleResult:
    """
    Container returned after generating schedules for a full period.

    base_schedule:    The base Schedule (all groups, weekly pattern).
    group_matrices:   Dict[group_code → 5×6 matrix] split from base_schedule.
    weekly_overrides: Dict[week_number → Schedule] for weeks with restrictions.
    """

    def __init__(
        self,
        base_schedule: Schedule,
        group_matrices: Dict[str, list],
        weekly_overrides: Optional[Dict[int, Schedule]] = None,
    ):
        self.base_schedule = base_schedule
        self.group_matrices = group_matrices
        self.weekly_overrides = weekly_overrides or {}


class ScheduleManager:
    """
    Orchestrates schedule generation for a full academic period.

    Workflow:
    1. Generate the BASE schedule using all groups' load at once.
    2. For weeks that have specific constraints, derive a WEEKLY schedule
       from the base (the GA restarts from the base matrix as seed).
    3. Weeks without special constraints reuse the base.
    """

    def __init__(
        self,
        rooms: List[Room],
        all_turns: List[Turn],                          # All turns for ALL groups
        constraints: List[ConstraintInterface],          # Period-wide constraints
        fixed_turns: Optional[List[Turn]] = None,
    ) -> None:
        self.rooms = rooms
        self.all_turns = all_turns
        self.constraints = constraints
        self.fixed_turns = fixed_turns or []

    def generate(self) -> PeriodScheduleResult:
        """Generate the base schedule and return a PeriodScheduleResult."""

        # Step 1: Generate the base schedule (all groups together)
        creator = ScheduleCreator(
            unscheduled_load=self.all_turns,
            rooms=self.rooms,
            constraints=self.constraints,
            fixed_turns=self.fixed_turns,
        )
        base_schedule = creator.get_best_schedule()

        # Step 2: Split by group for storage
        group_matrices = base_schedule.split_by_group()

        return PeriodScheduleResult(
            base_schedule=base_schedule,
            group_matrices=group_matrices,
        )

    def generate_weekly_override(
        self,
        week_number: int,
        week_constraints: List[ConstraintInterface],
        base_schedule: Schedule,
    ) -> Schedule:
        """
        Generate a week-specific schedule derived from the base.

        The GA is seeded with the base matrix so it deviates as little
        as possible while satisfying the week's constraints.
        """
        # Combine period constraints with week-specific ones
        combined_constraints = self.constraints + week_constraints

        # Collect the turns that the base schedule has placed
        # (we re-run placement from the base matrix as starting point)
        from .schedule import DAYS, TIME_SLOTS_PER_DAY
        base_turns: List[Turn] = []
        for d in range(DAYS):
            for t in range(TIME_SLOTS_PER_DAY):
                turn = base_schedule.matrix[d][t]
                if not turn.is_empty_slot():
                    base_turns.append(copy.deepcopy(turn))

        creator = ScheduleCreator(
            unscheduled_load=base_turns,
            rooms=self.rooms,
            constraints=combined_constraints,
            fixed_turns=self.fixed_turns,
        )
        return creator.get_best_schedule()


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def generate_base_schedule(
    rooms: List[Room],
    all_turns: List[Turn],
    constraints: List[ConstraintInterface],
    fixed_turns: Optional[List[Turn]] = None,
) -> PeriodScheduleResult:
    """
    Public entry point: generate the base schedule for a period.

    Parameters
    ----------
    rooms       : all available rooms
    all_turns   : all TeachingActivityAssignment turns for ALL groups in the period
    constraints : active Constraint objects mapped to ConstraintInterface instances
    fixed_turns : turns that must stay in a fixed (day, slot) position

    Returns
    -------
    PeriodScheduleResult with base_schedule and group_matrices
    """
    manager = ScheduleManager(
        rooms=rooms,
        all_turns=all_turns,
        constraints=constraints,
        fixed_turns=fixed_turns or [],
    )
    return manager.generate()