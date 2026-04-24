"""
Django Management Command: populate_realistic_data

Este script limpia la base de datos y la rellena con datos académicos
realistas para Ingeniería en Ciencias Informáticas (UCI).

Características:
- Limpia todos los modelos relacionados con horarios (excepto User)
- Asegura capacidad de carga matemática (máx 75% de ocupación)
- Usa nombres de asignaturas reales de ICI
- Genera períodos válidos para ICI_D (8 semestres) e ICI_CPE (10 semestres)
"""
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.data_management.models import (
    Period,
    AcademicDay,
    Professor,
    Room,
    Subject,
    Group,
    Activity,
    TeachingActivityAssignment,
    Constraint,
    ConstraintSchedule,
    Schedule,
    TimeSlot,
    NonDocentEvent,
    DocentEvent,
    AssignedEvent,
)


# =============================================================================
# CONSTANTES Y CONFIGURACIÓN
# =============================================================================

# Días y turnos disponibles por semana
DAYS_PER_WEEK = 5
SLOTS_PER_DAY = 6
TOTAL_SLOTS_PER_WEEK = DAYS_PER_WEEK * SLOTS_PER_DAY  # 30 slots

# Margen de holgura para que el GA pueda encontrar soluciones
OCCUPANCY_MARGIN = 0.75  # máximo 75% de ocupación

# Asignaturas reales de ICI (plan de estudio)
ICI_SUBJECTS = [
    {"name": "Programación I", "alias": "PROG1", "hours": 4},
    {"name": "Programación II", "alias": "PROG2", "hours": 4},
    {"name": "Matemática Discreta", "alias": "MATD", "hours": 3},
    {"name": "Álgebra Lineal", "alias": "ALG", "hours": 3},
    {"name": "Arquitectura de Computadoras", "alias": "ARQC", "hours": 3},
    {"name": "Bases de Datos I", "alias": "BD1", "hours": 3},
    {"name": "Bases de Datos II", "alias": "BD2", "hours": 3},
    {"name": "Sistemas Operativos", "alias": "SOP", "hours": 3},
    {"name": "Redes de Computadoras", "alias": "RED", "hours": 3},
    {"name": "Ingeniería de Software I", "alias": "ISW1", "hours": 3},
    {"name": "Ingeniería de Software II", "alias": "ISW2", "hours": 3},
    {"name": "Inteligencia Artificial", "alias": "IA", "hours": 3},
    {"name": "Compiladores", "alias": "COMP", "hours": 3},
    {"name": "Metodología de la Investigación", "alias": "MET", "hours": 2},
    {"name": "Proyecto de Grado", "alias": "PROY", "hours": 4},
    {"name": " Inglés", "alias": "INGL", "hours": 2},
    {"name": "Educación Física I", "alias": "EFI1", "hours": 2},
    {"name": "Educación Física II", "alias": "EFI2", "hours": 2},
]

# Nombres de profesores realistas
PROFESSOR_NAMES = [
    "Dr. Carlos Martínez Pérez", "Msc. Ana López García", "Ing. Roberto Sánchez Ruiz",
    "Msc. María Cristina Díaz", "Dr. José Antonio Fernández", "Lic. Laura Hernández Gómez",
    "Ing. Pedro Rodríguez Morales", "Msc. Carmen Lucía Torres", "Dr. Alejandro Vega Jiménez",
    "Ing. Beatriz Ruiz Castillo", "Msc. Daniel Mendoza Silva", "Dr. Isabel Vargas Reyes",
    "Ing. Fernando López Acosta", "Msc. Gloria María Peña", "Dr. Ricardo Jiménez Martínez",
    "Ing. Silvia Carolina Ramos", "Msc. Ernesto Guzmán López", "Dr. Patricia Vázquez Sánchez",
    "Ing. Jorge Alberto Reyes", "Msc. Adriana María Ortega",
]

# Distribución de actividades por asignatura (horas semanales)
# C = Conferencia, CP = Clase Práctica, L = Laboratorio
ACTIVITY_DISTRIBUTION = {
    "PROG1": {"C": 2, "CP": 2, "L": 2},  # 6 horas
    "PROG2": {"C": 2, "CP": 2, "L": 2},
    "MATD": {"C": 2, "CP": 1, "L": 0},
    "ALG": {"C": 2, "CP": 1, "L": 0},
    "ARQC": {"C": 2, "CP": 1, "L": 1},
    "BD1": {"C": 2, "CP": 1, "L": 1},
    "BD2": {"C": 2, "CP": 1, "L": 1},
    "SOP": {"C": 2, "CP": 1, "L": 1},
    "RED": {"C": 2, "CP": 1, "L": 1},
    "ISW1": {"C": 2, "CP": 1, "L": 0},
    "ISW2": {"C": 2, "CP": 1, "L": 0},
    "IA": {"C": 2, "CP": 1, "L": 1},
    "COMP": {"C": 2, "CP": 1, "L": 0},
    "MET": {"C": 2, "CP": 0, "L": 0},
    "PROY": {"C": 0, "CP": 4, "L": 0},
    "INGL": {"C": 2, "CP": 0, "L": 0},
    "EFI1": {"C": 0, "CP": 2, "L": 0},
    "EFI2": {"C": 0, "CP": 2, "L": 0},
}


class Command(BaseCommand):
    help = "Limpia la BD y genera datos realistas para ICI (UCI)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-wipe",
            action="store_true",
            help="No limpiar la base de datos, solo agregar datos",
        )
        parser.add_argument(
            "--groups-per-period",
            type=int,
            default=3,
            help="Número de grupos por período (default: 3)",
        )

    def handle(self, *args, **options):
        no_wipe = options["no_wipe"]
        groups_per_period = options["groups_per_period"]

        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write(self.style.WARNING("POBLANDO DATOS REALISTAS PARA ICI (UCI)"))
        self.stdout.write(self.style.WARNING("=" * 60))

        if not no_wipe:
            self._wipe_database()
        else:
            self.stdout.write(self.style.WARNING("Skipping wipe (--no-wipe)"))

        # Crear datos
        rooms = self._create_rooms()
        professors = self._create_professors()

        # Crear períodos para ambas carreras
        for career in [Period.Career.ICI_D, Period.Career.ICI_CPE]:
            max_periods = Period.CAREERS_PERIOD_COUNT[career]
            for period_num in range(1, max_periods + 1):
                period = self._create_period(career, period_num)
                self._create_academic_days(period)
                subjects = self._create_subjects(period)
                groups = self._create_groups(period, groups_per_period)
                self._create_activities(subjects)
                self._create_teaching_assignments(subjects, groups, professors, period)
                self.stdout.write(self.style.SUCCESS(
                    f"  ✓ Período {period_num} de {career} creado"
                ))

        # Verificar capacidad de carga
        self._verify_capacity(groups_per_period)

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
        self.stdout.write(self.style.SUCCESS("DATOS GENERADOS CORRECTAMENTE"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

    def _wipe_database(self):
        """Limpia todos los modelos relacionados con horarios."""
        self.stdout.write(self.style.WARNING("\n[1/6] Limpiando base de datos..."))

        with transaction.atomic():
            # Eliminar en orden inverso a las dependencias
            AssignedEvent.objects.all().delete()
            TimeSlot.objects.all().delete()
            Schedule.objects.all().delete()
            ConstraintSchedule.objects.all().delete()
            Constraint.objects.all().delete()
            DocentEvent.objects.all().delete()
            NonDocentEvent.objects.all().delete()
            TeachingActivityAssignment.objects.all().delete()
            Activity.objects.all().delete()
            Group.objects.all().delete()
            Subject.objects.all().delete()
            AcademicDay.objects.all().delete()
            Period.objects.all().delete()
            # No eliminamos Professor ni Room (recursos reutilizables)
            # No eliminamos User (requerido para acceso)

        self.stdout.write(self.style.SUCCESS("  ✓ Base de datos limpiada (User preservado)"))

    def _create_rooms(self):
        """Crea las aulas con tipos correctos."""
        self.stdout.write(self.style.WARNING("\n[2/6] Creando aulas..."))

        rooms_data = [
            # Salones de conferencia (S)
            {"code": "S1", "type": Room.RoomType.CONFERENCE_ROOM},
            {"code": "S2", "type": Room.RoomType.CONFERENCE_ROOM},
            {"code": "S3", "type": Room.RoomType.CONFERENCE_ROOM},
            {"code": "S4", "type": Room.RoomType.CONFERENCE_ROOM},
            # Aulas teóricas (A)
            {"code": "A1", "type": Room.RoomType.CLASSROOM},
            {"code": "A2", "type": Room.RoomType.CLASSROOM},
            {"code": "A3", "type": Room.RoomType.CLASSROOM},
            {"code": "A4", "type": Room.RoomType.CLASSROOM},
            {"code": "A5", "type": Room.RoomType.CLASSROOM},
            {"code": "A6", "type": Room.RoomType.CLASSROOM},
            # Laboratorios (L)
            {"code": "L1", "type": Room.RoomType.LABORATORY},
            {"code": "L2", "type": Room.RoomType.LABORATORY},
            {"code": "L3", "type": Room.RoomType.LABORATORY},
            {"code": "L4", "type": Room.RoomType.LABORATORY},
            {"code": "L5", "type": Room.RoomType.LABORATORY},
        ]

        rooms = []
        for data in rooms_data:
            room, created = Room.objects.get_or_create(
                room_code=data["code"],
                defaults={"room_type": data["type"]}
            )
            rooms.append(room)
            if created:
                self.stdout.write(f"    ✓ Aula {data['code']} ({data['type']})")

        self.stdout.write(self.style.SUCCESS(f"  ✓ Total: {len(rooms)} aulas"))
        return rooms

    def _create_professors(self):
        """Crea profesores con categorías reales."""
        self.stdout.write(self.style.WARNING("\n[3/6] Creando profesores..."))

        professors = []
        categories = [
            (Professor.ScientificCategory.DOCTOR, Professor.DocentCategory.TITULAR, 2),
            (Professor.ScientificCategory.MASTER, Professor.DocentCategory.TITULAR, 4),
            (Professor.ScientificCategory.MASTER, Professor.DocentCategory.ASSISTANT, 6),
            (Professor.ScientificCategory.LICENSED, Professor.DocentCategory.ASSOCIATE, 5),
            (Professor.ScientificCategory.ENGINEER, Professor.DocentCategory.INSTRUCTOR, 3),
        ]

        idx = 0
        for sci_cat, doc_cat, count in categories:
            for _ in range(count):
                if idx >= len(PROFESSOR_NAMES):
                    break
                prof, created = Professor.objects.get_or_create(
                    full_name=PROFESSOR_NAMES[idx],
                    defaults={
                        "scientific_category": sci_cat,
                        "docent_category": doc_cat,
                    }
                )
                professors.append(prof)
                if created:
                    self.stdout.write(f"    ✓ {prof.full_name} ({sci_cat.label}, {doc_cat.label})")
                idx += 1

        self.stdout.write(self.style.SUCCESS(f"  ✓ Total: {len(professors)} profesores"))
        return professors

    def _create_period(self, career: str, number: int) -> Period:
        """Crea un período académico."""
        start_date = date(2025, 9, 1) + timedelta(weeks=(number - 1) * 16)

        period, created = Period.objects.get_or_create(
            career=career,
            number=number,
            defaults={
                "weeks_count": 16,
                "is_active": (number == 1),  # Solo el primer período activo
                "start_date": start_date,
            }
        )
        return period

    def _create_academic_days(self, period: Period):
        """Crea los días académicos del período (16 semanas × 5 días)."""
        if AcademicDay.objects.filter(period=period).exists():
            return

        current_date = period.start_date
        for week in range(1, period.weeks_count + 1):
            for day_offset in range(5):  # Lunes a viernes
                AcademicDay.objects.get_or_create(
                    period=period,
                    date=current_date,
                    defaults={
                        "academic_week_number": week,
                        "is_active": True,
                    }
                )
                current_date += timedelta(days=1)
            # Saltar fin de semana
            current_date += timedelta(days=2)

    def _create_subjects(self, period: Period) -> list:
        """Crea las asignaturas del período."""
        # Seleccionar asignaturas según el semestre
        # (simulación: asignaturas rotan por semestres)
        period_subjects = []
        start_idx = (period.number - 1) % 5
        selected_subjects = ICI_SUBJECTS[start_idx:] + ICI_SUBJECTS[:start_idx]
        selected_subjects = selected_subjects[:10]  # 10 asignaturas por período

        for subj_data in selected_subjects:
            subject, created = Subject.objects.get_or_create(
                period=period,
                alias=subj_data["alias"],
                defaults={
                    "name": subj_data["name"],
                }
            )
            period_subjects.append(subject)
            if created:
                self.stdout.write(f"    ✓ {subj_data['alias']}: {subj_data['name']}")

        return period_subjects

    def _create_activities(self, subjects: list):
        """Crea las actividades (tipos de clase) para cada asignatura."""
        for subject in subjects:
            dist = ACTIVITY_DISTRIBUTION.get(subject.alias, {"C": 2, "CP": 1, "L": 1})

            for act_type, hours in dist.items():
                if hours > 0:
                    activity_type_map = {
                        "C": Activity.ActivityType.CONFERENCE,
                        "CP": Activity.ActivityType.PRACTICAL_CLASS,
                        "L": Activity.ActivityType.LABORATORY,
                    }
                    Activity.objects.get_or_create(
                        subject=subject,
                        activity_type=activity_type_map[act_type],
                        defaults={
                            "title": f"{subject.alias} - {act_type}",
                        }
                    )

    def _create_groups(self, period: Period, count: int) -> list:
        """Crea los grupos del período."""
        groups = []
        suffix = "D" if period.career == Period.Career.ICI_D else "E"

        for i in range(1, count + 1):
            group_code = f"{period.number}{suffix}{i}"
            group, created = Group.objects.get_or_create(
                period=period,
                group_code=group_code,
                defaults={}
            )
            groups.append(group)
            if created:
                self.stdout.write(f"    ✓ Grupo {group_code}")

        return groups

    def _create_teaching_assignments(
        self,
        subjects: list,
        groups: list,
        professors: list,
        period: Period
    ):
        """
        Crea las asignaciones de actividades docente.
        Asegura capacidad de carga matemática (máx 75% de ocupación).
        """
        # Mezclar profesores para distribuir carga
        available_profs = professors.copy()
        random.shuffle(available_profs)
        prof_idx = 0

        total_hours_per_group = {g.group_code: 0 for g in groups}
        max_hours = int(TOTAL_SLOTS_PER_WEEK * OCCUPANCY_MARGIN)  # 22.5 → 22 horas

        for subject in subjects:
            dist = ACTIVITY_DISTRIBUTION.get(subject.alias, {"C": 2, "CP": 1, "L": 1})

            for group in groups:
                # Verificar capacidad de carga antes de agregar
                current_hours = total_hours_per_group[group.group_code]
                subject_total_hours = sum(dist.values())

                if current_hours + subject_total_hours > max_hours:
                    self.stdout.write(self.style.WARNING(
                        f"    ⚠ {group.group_code}: skipping {subject.alias} "
                        f"(capacity: {current_hours}/{max_hours})"
                    ))
                    continue

                for act_type, hours in dist.items():
                    if hours == 0:
                        continue

                    activity_type_map = {
                        "C": Activity.ActivityType.CONFERENCE,
                        "CP": Activity.ActivityType.PRACTICAL_CLASS,
                        "L": Activity.ActivityType.LABORATORY,
                    }

                    # Asignar profesor (rotar)
                    prof = available_profs[prof_idx % len(available_profs)]
                    prof_idx += 1

                    TeachingActivityAssignment.objects.get_or_create(
                        subject=subject,
                        group=group,
                        activity_type=activity_type_map[act_type],
                        defaults={"professor": prof}
                    )

                    total_hours_per_group[group.group_code] += hours

        # Reporte de capacidad
        self.stdout.write(self.style.SUCCESS("  ✓ Capacidad de carga por grupo:"))
        for group_code, hours in total_hours_per_group.items():
            percentage = (hours / TOTAL_SLOTS_PER_WEEK) * 100
            status = self.style.SUCCESS if percentage <= 75 else self.style.ERROR
            self.stdout.write(f"    {status}{group_code}: {hours}h ({percentage:.1f}%)")

    def _verify_capacity(self, groups_per_period: int):
        """Verifica que la capacidad de carga sea matemáticamente soluble."""
        self.stdout.write(self.style.WARNING("\n[6/6] Verificando capacidad de carga..."))

        max_hours = int(TOTAL_SLOTS_PER_WEEK * OCCUPANCY_MARGIN)

        all_ok = True
        for period in Period.objects.all():
            for group in period.groups.all():
                assignments = TeachingActivityAssignment.objects.filter(group=group)
                total_hours = sum(
                    2 if a.activity_type == Activity.ActivityType.CONFERENCE else
                    1 if a.activity_type == Activity.ActivityType.PRACTICAL_CLASS else 1
                    for a in assignments
                )

                if total_hours > max_hours:
                    self.stdout.write(self.style.ERROR(
                        f"  ✗ {group.group_code}: {total_hours}h exceeds {max_hours}h limit"
                    ))
                    all_ok = False

        if all_ok:
            self.stdout.write(self.style.SUCCESS(
                f"  ✓ Todos los grupos dentro del límite ({max_hours}h = 75% de {TOTAL_SLOTS_PER_WEEK})"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "  ⚠ Algunos grupos exceden el límite - el GA puede tener dificultades"
            ))