import random
import copy
from typing import List, Optional
from .schedule import Schedule
from .dto.turn import Turn
from .dto.room import Room
from .interfaces.constraint_interface import ConstraintInterface


class ScheduleCreator:
    """
    Runs the Genetic Algorithm to produce the BASE schedule for a full period.

    Input:  all TeachingActivityAssignment turns for ALL groups in the period.
    Output: one Schedule object (the best found) representing the weekly pattern.

    The caller is responsible for splitting the result by group via
    schedule.split_by_group().
    """

    POPULATION_SIZE = 100
    MAX_EPOCHS = 300
    ELITE_SIZE = 10
    MUTATION_RATE = 0.10

    def __init__(
        self,
        unscheduled_load: List[Turn],
        rooms: List[Room],
        constraints: List[ConstraintInterface],
        fixed_turns: Optional[List[Turn]] = None,
    ) -> None:
        self.unscheduled_load = unscheduled_load
        self.rooms = rooms
        self.constraints = constraints
        self.fixed_turns = fixed_turns or []

        # Build the base matrix pre-loaded with fixed (non-movable) turns
        self.base_matrix = self._build_base_matrix()

        # Run the GA immediately
        self.best_schedule = self._run_ga()

    def _build_base_matrix(self) -> List[List[Turn]]:
        """Places fixed turns into an otherwise empty matrix."""
        from .schedule import DAYS, TIME_SLOTS_PER_DAY
        matrix = [[Turn() for _ in range(TIME_SLOTS_PER_DAY)] for _ in range(DAYS)]
        for turn in self.fixed_turns:
            # Fixed turns must carry a (day, slot) hint; skip if missing
            d = getattr(turn, 'fixed_day', None)
            t = getattr(turn, 'fixed_slot', None)
            if d is not None and t is not None:
                matrix[d][t] = copy.deepcopy(turn)
        return matrix

    def _run_ga(self) -> Schedule:
        # --- Initial population ---
        population: List[Schedule] = []
        for _ in range(self.POPULATION_SIZE):
            individual = Schedule(
                rooms=self.rooms,
                constraints=self.constraints,
                unscheduled_load=self.unscheduled_load,
                base_matrix=self.base_matrix,
            )
            individual.initialize_randomly()
            individual.calculate_score()
            population.append(individual)

        best_score = float('inf')

        for epoch in range(self.MAX_EPOCHS):
            population = self._epoch(population)

            # Check best every 10 epochs
            if epoch % 10 == 0:
                population.sort(key=lambda s: s.get_score())
                current_best = population[0].get_score()

                if current_best == 0:
                    break  # Perfect schedule found

                if current_best < best_score:
                    best_score = current_best

        population.sort(key=lambda s: s.get_score())
        return population[0]

    def _epoch(self, population: List[Schedule]) -> List[Schedule]:
        population.sort(key=lambda s: s.get_score())
        elite = population[:self.ELITE_SIZE]
        new_population: List[Schedule] = copy.deepcopy(elite)

        while len(new_population) < self.POPULATION_SIZE:
            parent1 = random.choice(elite)
            parent2 = random.choice(elite)

            if parent1 is parent2:
                continue

            child = copy.deepcopy(parent1)
            child.fusion(parent2.matrix)

            if random.random() < self.MUTATION_RATE:
                child.mutate()

            child.calculate_score()
            new_population.append(child)

        return new_population

    def get_best_schedule(self) -> Schedule:
        return copy.deepcopy(self.best_schedule)