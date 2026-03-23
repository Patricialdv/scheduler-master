import uuid
from datetime import timedelta
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from apps.data_management.models import (
    Period, Group, AcademicDay,
    Schedule, TimeSlot, DocentEvent, AssignedEvent,
    TeachingActivityAssignment, Activity, Professor, Room as RoomModel,
)
from schedule_generator.main import generate_schedule_for_period
from schedule_generator.solver.schedule import DAYS, TIME_SLOTS_PER_DAY
from schedule_generator.solver.schedule_manager import generate_base_schedule

ACTIVITY_TYPE_CODE = {
    'Conference': 'C', 'Practical Class': 'CP', 'Laboratory': 'L',
    'C': 'C', 'CP': 'CP', 'L': 'L',
}

def _normalize_activity_type(v):
    return ACTIVITY_TYPE_CODE.get(v, v)

SLOT_LABELS = {
    0: '8:00 - 9:20',   1: '9:30 - 10:50',  2: '11:00 - 12:20',
    3: '12:30 - 13:50', 4: '14:00 - 15:20', 5: '15:30 - 16:50',
}
DAY_LABELS = {0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves', 4: 'Viernes'}


# ---------------------------------------------------------------------------
# Helpers — Academic calendar
# ---------------------------------------------------------------------------

def _get_week_choices(period):
    choices = [{'number': 0, 'label': 'Horario Base (patrón general)', 'monday': None}]

    if not period.start_date:
        return choices

    monday = period.start_date - timedelta(days=period.start_date.weekday())

    for week_num in range(1, period.weeks_count + 1):
        week_monday = monday + timedelta(weeks=week_num - 1)
        week_friday = week_monday + timedelta(days=4)
        label = (
            f'Semana {week_num}: '
            f'{week_monday.strftime("%#d %b")} - {week_friday.strftime("%#d %b")}'
        )
        choices.append({'number': week_num, 'label': label, 'monday': week_monday})

    return choices


def _get_or_create_base_academic_days(period):
    """5 virtual AcademicDays (week_number=0) for the base schedule."""
    base_days = {}
    if period.start_date:
        monday = period.start_date - timedelta(days=period.start_date.weekday())
    else:
        from datetime import date
        monday = date(2000, 1, 3)

    for d in range(DAYS):
        day_date = monday + timedelta(days=d)
        academic_day, _ = AcademicDay.objects.get_or_create(
            period=period, date=day_date,
            defaults={'is_active': True, 'academic_week_number': 0}
        )
        base_days[d] = academic_day
    return base_days


def _get_or_create_week_academic_days(period, week_monday):
    """5 AcademicDays for a specific week."""
    week_days = {}
    for d in range(DAYS):
        day_date = week_monday + timedelta(days=d)
        delta = (week_monday - period.start_date).days // 7 + 1
        academic_day, _ = AcademicDay.objects.get_or_create(
            period=period, date=day_date,
            defaults={'is_active': True, 'academic_week_number': delta}
        )
        week_days[d] = academic_day
    return week_days


# ---------------------------------------------------------------------------
# Helpers — Persist
# ---------------------------------------------------------------------------

def _persist_schedule(period, result, is_base, academic_week_day=None):
    """Persist a schedule (base or weekly) to the DB."""
    base_days = (
        _get_or_create_base_academic_days(period) if is_base
        else _get_or_create_week_academic_days(period, academic_week_day)
    )

    for group_code, matrix in result.group_matrices.items():
        group = Group.objects.filter(group_code=group_code, period=period).first()
        if not group:
            continue

        Schedule.objects.filter(
            period=period, group=group,
            is_base=is_base,
            academic_week=base_days[0] if not is_base else None,
        ).delete()

        schedule = Schedule.objects.create(
            period=period,
            group=group,
            is_base=is_base,
            academic_week=None if is_base else base_days[0],
            score=result.base_schedule.get_score(),
        )

        for d in range(DAYS):
            for t in range(TIME_SLOTS_PER_DAY):
                turn = matrix[d][t] if matrix[d] else None
                if turn is None or turn.is_empty_slot():
                    continue

                time_slot = TimeSlot.objects.create(
                    schedule=schedule,
                    academic_day=base_days[d],
                    slot_index=t + 1,
                )

                assignment = TeachingActivityAssignment.objects.filter(
                    id__in=turn.source_assignment_ids
                ).select_related('professor').first()
                if not assignment:
                    continue

                activity, _ = Activity.objects.get_or_create(
                    subject=assignment.subject,
                    activity_type=turn.activity_type,
                    defaults={'title': f'{assignment.subject.alias or assignment.subject.name} — {turn.activity_type}'}
                )
                if activity is None:
                    continue

                room_obj = None
                if turn.room:
                    room_obj = RoomModel.objects.filter(room_code=turn.room.number).first()

                docent_event = DocentEvent.objects.create(
                    professor=assignment.professor,
                    activity=activity,
                    room=room_obj,
                )
                AssignedEvent.objects.create(
                    time_slot=time_slot,
                    docent_event=docent_event,
                )


# ---------------------------------------------------------------------------
# Helpers — Display
# ---------------------------------------------------------------------------

def _result_to_display_groups(result):
    prof_map = {str(p.id): p.full_name for p in Professor.objects.all()}
    display_groups = []

    for group_code, matrix in result.group_matrices.items():
        rows = []
        for t in range(TIME_SLOTS_PER_DAY):
            row = {'slot_label': SLOT_LABELS[t], 'slot_index': t + 1, 'cells': []}
            for d in range(DAYS):
                turn = matrix[d][t] if matrix[d] else None
                if turn is not None:
                    row['cells'].append({
                        'empty': False,
                        'subject': turn.subject_alias,
                        'activity_type': _normalize_activity_type(turn.activity_type),
                        'groups': ', '.join(turn.group_codes),
                        'professor_name': prof_map.get(str(turn.professor_id), 'Desconocido'),
                        'room': turn.room.number if turn.room else 'N/A',
                    })
                else:
                    row['cells'].append({'empty': True})
        rows.append(row)
        display_groups.append({'group_code': group_code, 'rows': rows})

    return display_groups


def _db_schedule_to_display_groups(period, week_monday):
    """Load an already-persisted weekly schedule from the DB and build display context."""
    from datetime import date
    prof_map = {str(p.id): p.full_name for p in Professor.objects.all()}
    display_groups = []

    groups = Group.objects.filter(period=period)
    for group in groups:
        monday_day = AcademicDay.objects.filter(period=period, date=week_monday).first()
        if not monday_day:
            continue

        schedule = Schedule.objects.filter(
            period=period, group=group,
            is_base=False,
            academic_week=monday_day,
        ).first()
        if not schedule:
            continue

        time_slots = TimeSlot.objects.filter(schedule=schedule).select_related(
            'academic_day'
        ).prefetch_related(
            'assignedevent_set__docent_event__professor',
            'assignedevent_set__docent_event__activity__subject',
            'assignedevent_set__docent_event__room',
        )

        day_to_col = {}
        for d in range(DAYS):
            day_to_col[(week_monday + timedelta(days=d))] = d

        rows = []
        for t in range(TIME_SLOTS_PER_DAY):
            row = {'slot_label': SLOT_LABELS[t], 'slot_index': t + 1, 'cells': []}
            for d in range(DAYS):
                day_date = week_monday + timedelta(days=d)
                ts = time_slots.filter(academic_day__date=day_date, slot_index=t + 1).first()
                if ts:
                    ae = ts.assignedevent_set.filter(docent_event__isnull=False).first()
                    if ae and ae.docent_event:
                        de = ae.docent_event
                        row['cells'].append({
                            'empty': False,
                            'subject': de.activity.subject.alias or de.activity.subject.name if de.activity else 'N/A',
                            'activity_type': _normalize_activity_type(de.activity.activity_type) if de.activity else '',
                            'groups': group.group_code,
                            'professor_name': de.professor.full_name if de.professor else 'N/A',
                            'room': de.room.room_code if de.room else 'N/A',
                        })
                    else:
                        row['cells'].append({'empty': True})
                else:
                    row['cells'].append({'empty': True})
            rows.append(row)

        display_groups.append({'group_code': group.group_code, 'rows': rows})

    return display_groups


def _db_base_schedule_to_display_groups(period):
    """Load the base schedule from DB and build display context."""
    prof_map = {str(p.id): p.full_name for p in Professor.objects.all()}
    display_groups = []

    groups = Group.objects.filter(period=period)
    for group in groups:
        schedule = Schedule.objects.filter(
            period=period, group=group, is_base=True
        ).first()
        if not schedule:
            continue

        time_slots = TimeSlot.objects.filter(schedule=schedule).prefetch_related(
            'assignedevent_set__docent_event__professor',
            'assignedevent_set__docent_event__activity__subject',
            'assignedevent_set__docent_event__room',
        )

        rows = []
        for t in range(TIME_SLOTS_PER_DAY):
            row = {'slot_label': SLOT_LABELS[t], 'slot_index': t + 1, 'cells': []}
            for d in range(DAYS):
                ts = time_slots.filter(slot_index=t + 1).filter(
                    academic_day__academic_week_number=0
                ).filter(academic_day__date__week_day=d + 2).first()
                if ts:
                    ae = ts.assignedevent_set.filter(docent_event__isnull=False).first()
                    if ae and ae.docent_event:
                        de = ae.docent_event
                        row['cells'].append({
                            'empty': False,
                            'subject': de.activity.subject.alias or de.activity.subject.name if de.activity else 'N/A',
                            'activity_type': _normalize_activity_type(de.activity.activity_type) if de.activity else '',
                            'groups': group.group_code,
                            'professor_name': de.professor.full_name if de.professor else 'N/A',
                            'room': de.room.room_code if de.room else 'N/A',
                        })
                    else:
                        row['cells'].append({'empty': True})
                else:
                    row['cells'].append({'empty': True})
            rows.append(row)

        display_groups.append({'group_code': group.group_code, 'rows': rows})

    return display_groups


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@login_required
def schedule_selector(request):
    """Step 1: Ensure all active periods have schedules, then show selector."""
    from .schedule_service import ensure_all_active_periods
    generation_errors = ensure_all_active_periods()

    periods = Period.objects.filter(is_active=True).order_by('career', 'number')

    selected_period_id = request.GET.get('period_id')
    selected_period = None
    week_choices = []

    if selected_period_id:
        selected_period = Period.objects.filter(id=selected_period_id).first()
    elif periods.exists():
        selected_period = periods.first()

    if selected_period:
        week_choices = _get_week_choices(selected_period)

    return render(request, 'schedule/selector.html', {
        'periods': periods,
        'selected_period': selected_period,
        'week_choices': week_choices,
        'generation_errors': generation_errors,
    })


@login_required
def view_schedule(request):
    """Step 2: Display the selected schedule (always read from DB)."""
    period_id = request.GET.get('period_id')
    week_number = request.GET.get('week_number', '0')

    try:
        week_number = int(week_number)
    except ValueError:
        week_number = 0

    try:
        period = Period.objects.get(id=period_id)
    except (Period.DoesNotExist, TypeError):
        return render(request, 'schedule/error.html', {
            'error_message': 'Período no encontrado.'
        })

    try:
        week_choices = _get_week_choices(period)

        if week_number == 0:
            display_groups = _db_base_schedule_to_display_groups(period)
            week_label = 'Horario Base'
            base_sched = Schedule.objects.filter(period=period, is_base=True).first()
            score = base_sched.score if base_sched else 0
            is_perfect = score == 0

        else:
            if not period.start_date:
                return render(request, 'schedule/error.html', {
                    'error_message': 'El período no tiene fecha de inicio definida.'
                })
            monday = period.start_date - timedelta(days=period.start_date.weekday())
            week_monday = monday + timedelta(weeks=week_number - 1)
            week_friday = week_monday + timedelta(days=4)
            week_label = (
                f'Semana {week_number}: '
                f'{week_monday.strftime("%#d %b")} - {week_friday.strftime("%#d %b")}'
            )
            display_groups = _db_schedule_to_display_groups(period, week_monday)
            monday_day = AcademicDay.objects.filter(period=period, date=week_monday).first()
            sched = Schedule.objects.filter(
                period=period, is_base=False, academic_week=monday_day
            ).first() if monday_day else None
            score = sched.score if sched else 0
            is_perfect = score == 0

        return render(request, 'schedule/schedule_display.html', {
            'period': period,
            'display_groups': display_groups,
            'day_labels': [DAY_LABELS[d] for d in range(DAYS)],
            'score': score,
            'is_perfect': is_perfect,
            'week_label': week_label,
            'week_number': week_number,
            'week_choices': week_choices,
            'periods': Period.objects.filter(is_active=True).order_by('career', 'number'),
        })

    except ValueError as e:
        return render(request, 'schedule/error.html', {'error_message': str(e)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return render(request, 'schedule/error.html', {'error_message': str(e)})


# Keep old URL working as redirect to selector
@login_required
def generate_schedule(request):
    from django.shortcuts import redirect
    return redirect('schedule_selector')


def landing_page(request):
    return render(request, 'landing/index.html')