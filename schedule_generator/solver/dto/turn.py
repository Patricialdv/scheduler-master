import uuid
from typing import Literal, Optional, List
from .room import Room

ActivityCode = Literal['C', 'CP', 'L']


class Turn:
    """
    The atomic assignment unit (the 'gene' in the GA).

    For conferences (C), a single Turn can hold up to 2 groups taught by the same
    professor in the same room. For CP and L, it's always one group.
    """

    def __init__(
        self,
        subject_alias: str = None,
        group_codes: List[str] = None,       # List to support 2 groups in conferences
        activity_type: ActivityCode = None,
        professor_id: uuid.UUID = None,
        source_assignment_ids: List[uuid.UUID] = None,  # One per group
        room: Optional[Room] = None,
    ) -> None:
        if subject_alias is not None:
            self.subject_alias = subject_alias
            self.group_codes = group_codes or []
            self.activity_type = activity_type
            self.professor_id = professor_id
            self.source_assignment_ids = source_assignment_ids or []
            self.room = room
            self.is_empty = False
        else:
            self.subject_alias = None
            self.group_codes = []
            self.activity_type = None
            self.professor_id = None
            self.source_assignment_ids = []
            self.room = None
            self.is_empty = True

    def is_empty_slot(self) -> bool:
        return self.is_empty

    def can_merge_with(self, other: 'Turn') -> bool:
        """
        Permite fusionar conferencias de la misma materia aunque tengan
        distintos profesores (modelo cubano: todos los grupos asisten juntos).
        Límite: máximo 3 grupos por celda.
        """
        return (
            not self.is_empty
            and not other.is_empty
            and self.activity_type == 'C'
            and other.activity_type == 'C'
            and self.subject_alias == other.subject_alias
            and len(self.group_codes) < 3
        )

    def merge(self, other: 'Turn') -> None:
        """Merges another group's conference into this Turn."""
        self.group_codes.extend(other.group_codes)
        self.source_assignment_ids.extend(other.source_assignment_ids)

    def __str__(self):
        if self.is_empty_slot():
            return '___'
        groups = '+'.join(self.group_codes)
        return f'{self.subject_alias}_{self.activity_type}_{groups}'