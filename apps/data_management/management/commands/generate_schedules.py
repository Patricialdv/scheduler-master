"""
Management command to generate schedules for all active periods with pending schedules.

Usage:
    .venv\\Scripts\\python manage.py generate_schedules
    .venv\\Scripts\\python manage.py generate_schedules --period=2
"""

import logging
from django.core.management.base import BaseCommand, CommandError

from apps.data_management.models import Period, Schedule, Group, DocentEvent, AssignedEvent
from schedule_generator.main import generate_schedule_for_period
from schedule_generator.solver.schedule_creator import ScheduleCreator

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Generate schedules for active periods with pending schedules (score=0)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--period',
            type=int,
            help='Process only a specific period number (e.g., --period=2)',
        )
        parser.add_argument(
            '--career',
            type=str,
            choices=['ICI_D', 'ICI_CPE'],
            help='Filter by career (ICI_D or ICI_CPE)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be generated without actually generating',
        )

    def handle(self, *args, **options):
        period_num = options.get('period')
        career_filter = options.get('career')
        dry_run = options.get('dry_run', False)

        # Build query for periods with pending schedules
        periods_query = Period.objects.filter(
            is_active=True,
            number__in=[2, 4, 6, 8, 10]  # Even periods only
        ).prefetch_related('groups')

        if period_num:
            periods_query = periods_query.filter(number=period_num)

        if career_filter:
            periods_query = periods_query.filter(career=career_filter)

        periods = list(periods_query)
        
        if not periods:
            raise CommandError('No active periods found matching the criteria.')

        # Get periods with pending schedules (score=0)
        pending_periods = []
        for period in periods:
            pending_count = Schedule.objects.filter(
                period=period,
                is_base=True,
                score=0
            ).count()
            if pending_count > 0:
                pending_periods.append((period, pending_count))

        if not pending_periods:
            self.stdout.write(self.style.WARNING(
                'No periods with pending schedules (score=0) found.'
            ))
            return

        self.stdout.write(self.style.WARNING('=' * 60))
        self.stdout.write(self.style.WARNING('GENERANDO HORARIOS PARA PERÍODOS PENDIENTES'))
        self.stdout.write(self.style.WARNING('=' * 60))
        self.stdout.write(self.style.SUCCESS(
            f'Períodos a procesar: {len(pending_periods)}'
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING('\n[DRY RUN] Períodos que serían procesados:'))
            for period, count in pending_periods:
                self.stdout.write(f'  - {period} ({count} grupos)')
            return

        # Process each period
        success_count = 0
        failure_count = 0
        failures = []

        for period, pending_groups in pending_periods:
            self.stdout.write(self.style.WARNING(f'\n[{'='*50}]'))
            self.stdout.write(self.style.WARNING(f'Procesando: {period}'))
            self.stdout.write(self.style.WARNING(f'Grupos pendientes: {pending_groups}'))
            
            try:
                # Generate the schedule
                result = generate_schedule_for_period(period_id=period.id)
                final_score = result.base_schedule.get_score()
                
                # Update existing Schedule objects (score=0) with new data
                updated_count = 0
                for group_code, matrix in result.group_matrices.items():
                    group = Group.objects.filter(
                        group_code=group_code,
                        period=period
                    ).first()
                    if not group:
                        continue

                    # Get or create the schedule (update existing with score=0)
                    schedule, created = Schedule.objects.update_or_create(
                        period=period,
                        group=group,
                        is_base=True,
                        defaults={'score': final_score}
                    )

                    # Clear old TimeSlots and recreate
                    from apps.data_management.models import TimeSlot, Activity, AssignedEvent
                    from schedule_generator.solver.schedule import DAYS, TIME_SLOTS_PER_DAY
                    
                    # Delete old events
                    AssignedEvent.objects.filter(time_slot__schedule=schedule).delete()
                    TimeSlot.objects.filter(schedule=schedule).delete()

                    # Get base academic days
                    from apps.scheduler_management.schedule_service import _get_or_create_base_academic_days
                    base_days = _get_or_create_base_academic_days(period)

                    # Create new TimeSlots, DocentEvents and AssignedEvents
                    for d in range(DAYS):
                        for t in range(TIME_SLOTS_PER_DAY):
                            turn = matrix[d][t] if matrix[d] else None
                            if turn is None or turn.is_empty_slot():
                                continue

                            # Get the teaching assignment first
                            assignment = None
                            if hasattr(turn, 'source_assignment_ids') and turn.source_assignment_ids:
                                from apps.data_management.models import TeachingActivityAssignment
                                assignment = TeachingActivityAssignment.objects.filter(
                                    id__in=turn.source_assignment_ids
                                ).select_related('professor', 'subject').first()

                            if not assignment:
                                continue

                            # Only create TimeSlot when we have a valid assignment
                            time_slot = TimeSlot.objects.create(
                                schedule=schedule,
                                academic_day=base_days[d],
                                slot_index=t + 1,
                            )

                            # Get or create activity
                            activity, _ = Activity.objects.get_or_create(
                                subject=assignment.subject,
                                activity_type=turn.activity_type,
                                defaults={
                                    'title': f'{assignment.subject.alias or assignment.subject.name} — {turn.activity_type}'
                                }
                            )

                            # Get room
                            room_obj = None
                            if turn.room:
                                from apps.data_management.models import Room as RoomModel
                                room_obj = RoomModel.objects.filter(
                                    room_code=turn.room.number
                                ).first()

                            # Create DocentEvent first, then link with AssignedEvent
                            docent_event = DocentEvent.objects.create(
                                professor=assignment.professor,
                                activity=activity,
                                room=room_obj,
                            )

                            # Create AssignedEvent linking TimeSlot to DocentEvent
                            AssignedEvent.objects.create(
                                time_slot=time_slot,
                                docent_event=docent_event,
                            )
                    
                    updated_count += 1

                # Verify the score was saved
                verify_score = Schedule.objects.filter(
                    period=period,
                    is_base=True
                ).first().score if updated_count > 0 else 0

                # Determine success/failure based on score
                threshold = ScheduleCreator.SCORE_THRESHOLD
                # Aceptar scores hasta 200,000 como "generados" (aunque subóptimos)
                max_acceptable_score = 200_000
                
                if final_score <= threshold:
                    status = self.style.SUCCESS
                    success_count += 1
                    status_msg = f'✓ ÉXITO (score óptimo)'
                elif final_score <= max_acceptable_score:
                    status = self.style.WARNING
                    success_count += 1  # Contar como éxito si es aceptable
                    status_msg = f'⚠️ GENERADO (score alto)'
                else:
                    status = self.style.ERROR
                    failure_count += 1
                    status_msg = f'✗ SCORE MUY ALTO'

                self.stdout.write(status(
                    f'  → Score final: {final_score:,} (threshold: {threshold:,})'
                ))
                self.stdout.write(status(f'  → {status_msg}'))
                self.stdout.write(status(f'  → Grupos actualizados: {updated_count}'))

            except Exception as e:
                failure_count += 1
                failures.append((str(period), str(e)))
                self.stdout.write(self.style.ERROR(f'  → ✗ ERROR: {str(e)}'))
                log.exception(f'Error generating schedule for {period}')

        # Final summary
        self.stdout.write(self.style.WARNING('\n' + '=' * 60))
        self.stdout.write(self.style.WARNING('RESUMEN DE GENERACIÓN'))
        self.stdout.write(self.style.WARNING('=' * 60))
        
        self.stdout.write(self.style.SUCCESS(
            f'  ✓ Exitosos: {success_count}'
        ))
        
        if failure_count > 0:
            self.stdout.write(self.style.ERROR(
                f'  ✗ Fallidos: {failure_count}'
            ))
            self.stdout.write(self.style.WARNING('  Errores:'))
            for period_name, error in failures:
                self.stdout.write(self.style.ERROR(f'    - {period_name}: {error}'))
        else:
            self.stdout.write(self.style.ERROR(f'  ✗ Fallidos: 0'))

        # Verify final state
        self.stdout.write(self.style.WARNING('\n[VERIFICACIÓN FINAL]'))
        total_schedules = Schedule.objects.filter(is_base=True).count()
        with_score = Schedule.objects.filter(is_base=True, score__gt=0).count()
        pending = Schedule.objects.filter(is_base=True, score=0).count()
        
        self.stdout.write(self.style.SUCCESS(
            f'  Total schedules: {total_schedules}'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'  Con score > 0: {with_score}'
        ))
        self.stdout.write(self.style.WARNING(
            f'  Pendientes (score=0): {pending}'
        ))

        if pending > 0:
            self.stdout.write(self.style.ERROR(
                f'\n  ⚠️ ADVERTENCIA: {pending} horarios siguen pendientes!'
            ))