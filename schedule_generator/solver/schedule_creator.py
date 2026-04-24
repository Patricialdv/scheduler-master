import random
import copy
import logging
import time
from typing import List, Optional
from .schedule import Schedule
from .dto.turn import Turn
from .dto.room import Room
from .interfaces.constraint_interface import ConstraintInterface

log = logging.getLogger(__name__)


class ScheduleCreator:
    """
    Runs the Genetic Algorithm to produce the BASE schedule for a full period.

    Input:  all TeachingActivityAssignment turns for ALL groups in the period.
    Output: one Schedule object (the best found) representing the weekly pattern.

    The caller is responsible for splitting the result by group via
    schedule.split_by_group().

    GA configuration:
        POPULATION_SIZE : total individuals per generation
        MAX_EPOCHS      : initial epoch budget (extends if score > SCORE_THRESHOLD)
        ELITE_SIZE      : top individuals preserved each epoch
        MUTATION_COUNT  : worst elite individuals mutated (with verification) per epoch
        SCORE_THRESHOLD : acceptable score ceiling — GA keeps running until reached
        STAGNATION_LIMIT: epochs without improvement before partial population reset
        DIVERSITY_MIN_DIFF: minimum score difference required to accept a new individual
                            into the initial population (forces diversity)
    """

    # Hiperparámetros del GA
    POPULATION_SIZE    = 50    # menos individuos = época más rápida
    MAX_EPOCHS         = 300
    ELITE_SIZE         = 10    # top 20% de elite
    MUTATION_COUNT     = 3
    # Umbral de score aceptable:
    #   sin violaciones de sala (10K× cada una) → objetivo < 10K
    SCORE_THRESHOLD    = 10_000
    STAGNATION_LIMIT   = 10    # resetea más rápido ante estancamiento
    DIVERSITY_MIN_DIFF = 300
    TIME_LIMIT_SECONDS = 45    # máximo 45 segundos por período

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

    # ------------------------------------------------------------------
    # Base matrix
    # ------------------------------------------------------------------

    def _build_base_matrix(self) -> List[List[Turn]]:
        """Places fixed turns into an otherwise empty matrix."""
        from .schedule import DAYS, TIME_SLOTS_PER_DAY
        matrix = [[Turn() for _ in range(TIME_SLOTS_PER_DAY)] for _ in range(DAYS)]
        for turn in self.fixed_turns:
            d = getattr(turn, 'fixed_day', None)
            t = getattr(turn, 'fixed_slot', None)
            if d is not None and t is not None:
                matrix[d][t] = copy.deepcopy(turn)
        return matrix

    # ------------------------------------------------------------------
    # Initial population with forced diversity  [06]
    # ------------------------------------------------------------------

    def _make_individual(self) -> Schedule:
        """Create and evaluate a single random Schedule individual."""
        individual = Schedule(
            rooms=self.rooms,
            constraints=self.constraints,
            unscheduled_load=self.unscheduled_load,
            base_matrix=self.base_matrix,
        )
        individual.initialize_randomly()
        # C3: early stopping con umbral 10× mayor que SCORE_THRESHOLD
        individual.calculate_score(abort_threshold=self.SCORE_THRESHOLD * 20)
        return individual

    def _build_initial_population(self) -> List[Schedule]:
        """
        Build the initial population enforcing minimum score diversity.

        [05] The first individual is built with initialize_randomly().
            Every subsequent individual uses initialize_from_permutation()
            seeded from the first individual, varying only the free turns.
            Diversity is still enforced via DIVERSITY_MIN_DIFF.
        """
        population: List[Schedule] = []
        accepted_scores: List[int] = []
        reference: Optional[Schedule] = None

        attempts = 0
        max_attempts_per_slot = 10

        while len(population) < self.POPULATION_SIZE:
            candidate = Schedule(
                rooms=self.rooms,
                constraints=self.constraints,
                unscheduled_load=self.unscheduled_load,
                base_matrix=self.base_matrix,
            )

            if reference is None:
                # First individual: fully random with constraints-first [04]
                candidate.initialize_randomly()
            else:
                # Subsequent: permutation of free turns around the reference [05]
                candidate.initialize_from_permutation(reference)

            # C3: early stopping con umbral 10× mayor que SCORE_THRESHOLD
            candidate.calculate_score(abort_threshold=self.SCORE_THRESHOLD * 20)

            c_score = candidate.get_score()
            too_similar = any(
                abs(c_score - s) < self.DIVERSITY_MIN_DIFF
                for s in accepted_scores
            )

            if not too_similar or attempts >= max_attempts_per_slot:
                population.append(candidate)
                accepted_scores.append(c_score)
                if reference is None:
                    reference = candidate
                attempts = 0
            else:
                attempts += 1

        return population

    # ------------------------------------------------------------------
    # Main GA loop  [02] [03] [07] [11]
    # ------------------------------------------------------------------

    def _run_ga(self) -> Schedule:
        log.info('[GA] Starting — pop=%d, elite=%d, max_epochs=%d, threshold=%d, time_limit=%ds',
                self.POPULATION_SIZE, self.ELITE_SIZE,
                self.MAX_EPOCHS, self.SCORE_THRESHOLD, self.TIME_LIMIT_SECONDS)

        start_time = time.time()

        # [06] Diverse initial population
        population = self._build_initial_population()
        population.sort(key=lambda s: s.get_score())

        best_score = population[0].get_score()
        epochs_without_improvement = 0
        epoch = 0

        while True:
            # --- Hard time limit check ---
            elapsed = time.time() - start_time
            if elapsed >= self.TIME_LIMIT_SECONDS:
                log.warning(
                    '[GA] Time limit reached (%.1fs). '
                    'Best score so far: %d. Returning best found.',
                    elapsed, population[0].get_score(),
                )
                break

            population = self._epoch(population)
            epoch += 1

            current_best = population[0].get_score()

            # [11] Log every 10 epochs
            if epoch % 10 == 0:
                elapsed = time.time() - start_time
                unplaced = len(population[0].unscheduled_load)
                log.info(
                    '[GA] Epoch %d | best_score=%d | unplaced_turns=%d | elapsed=%.1fs',
                    epoch, current_best, unplaced, elapsed,
                )

            # [03] Stop condition 1: perfect schedule
            if current_best == 0:
                log.info('[GA] Perfect schedule (score=0) found at epoch %d.', epoch)
                break

            # Track stagnation [07]
            if current_best < best_score:
                best_score = current_best
                epochs_without_improvement = 0
            else:
                epochs_without_improvement += 1

            # [07] Partial reset on stagnation
            if epochs_without_improvement >= self.STAGNATION_LIMIT:
                log.info(
                    '[GA] Stagnation at epoch %d. Injecting 10 fresh individuals.',
                    epoch,
                )
                fresh = [self._make_individual() for _ in range(10)]
                population[-10:] = fresh
                population.sort(key=lambda s: s.get_score())
                epochs_without_improvement = 0

            # [03] After MAX_EPOCHS: check threshold
            if epoch >= self.MAX_EPOCHS:
                if current_best <= self.SCORE_THRESHOLD:
                    log.info(
                        '[GA] Epoch %d. Score %d ≤ threshold %d. Stopping.',
                        epoch, current_best, self.SCORE_THRESHOLD,
                    )
                    break
                else:
                    if epoch >= self.MAX_EPOCHS * 2:
                        log.warning(
                            '[GA] Safety cap at epoch %d. Score %d > threshold %d. '
                            'Returning best found.',
                            epoch, current_best, self.SCORE_THRESHOLD,
                        )
                        break

        elapsed = time.time() - start_time
        log.info('[GA] Finished — epoch=%d | final_score=%d | elapsed=%.1fs',
                epoch, population[0].get_score(), elapsed)
        return population[0]

    # ------------------------------------------------------------------
    # Epoch  [01] [02]
    # ------------------------------------------------------------------

    def _epoch(self, population: List[Schedule]) -> List[Schedule]:
        population.sort(key=lambda s: s.get_score())
        elite = population[:self.ELITE_SIZE]  # [02] top 20
        new_population: List[Schedule] = copy.deepcopy(elite)

        # --- Crossover: generate 80 children from elite parents ---
        while len(new_population) < self.POPULATION_SIZE:
            parent1 = random.choice(elite)
            parent2 = random.choice(elite)

            if parent1 is parent2:
                continue

            # A1: copia shallow de matrix en lugar de deepcopy del individuo completo
            new_matrix = [row[:] for row in parent1.matrix]
            child = Schedule(
                rooms=parent1.rooms,
                constraints=parent1.constraints,
                unscheduled_load=parent1.unscheduled_load,
                matrix=new_matrix,
            )
            # M2: limpiar caché del hijo antes de evaluar
            child._reset_cache()
            child.fusion(parent2.matrix)
            # C3: early stopping con umbral 10× mayor que SCORE_THRESHOLD
            child.calculate_score(abort_threshold=self.SCORE_THRESHOLD * 20)
            new_population.append(child)

        # --- Select best 20 from the full pool of 100 ---  [02]
        new_population.sort(key=lambda s: s.get_score())

        # --- [01] Mutation with verification on the 5 worst of the top 20 ---
        worst_indices = list(range(self.ELITE_SIZE - self.MUTATION_COUNT, self.ELITE_SIZE))

        for idx in worst_indices:
            candidate = copy.deepcopy(new_population[idx])
            original_score = candidate.get_score()

            # Perform swap mutation and use fast score update [10]
            occupied = [
                (d, t)
                for d in range(5)
                for t in range(6)
                if not candidate.matrix[d][t].is_empty_slot()
            ]
            if len(occupied) >= 2:
                (d1, t1), (d2, t2) = random.sample(occupied, 2)
                candidate.matrix[d1][t1], candidate.matrix[d2][t2] = (
                    candidate.matrix[d2][t2], candidate.matrix[d1][t1]
                )
                candidate.calculate_score_after_swap(d1, t1, d2, t2)

            # Keep only if improved
            if candidate.get_score() < original_score:
                new_population[idx] = candidate

        # Final sort after mutations
        new_population.sort(key=lambda s: s.get_score())

        return new_population

    # ------------------------------------------------------------------
    # Public accessor
    # ------------------------------------------------------------------

    def get_best_schedule(self) -> Schedule:
        return copy.deepcopy(self.best_schedule)