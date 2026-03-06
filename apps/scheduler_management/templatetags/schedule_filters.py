from django import template
from typing import Sequence

# Registra los filtros personalizados con Django
register = template.Library()

@register.filter
def split(value: str, arg: str) -> list[str]:
    """
    Divide una cadena (string) por el argumento (separador) dado y devuelve una lista.
    Uso: 'cadena,con,comas'|split:',' 
    """
    if not isinstance(value, str):
        # Manejar caso de valor no válido
        return []
    return value.split(arg)

@register.filter
def index(sequence: Sequence, position: str) -> any:
    """
    Devuelve el elemento en la posición dada de una secuencia (lista o string).
    Acepta el índice como una cadena y lo convierte a entero.
    Uso: lista|index:"0"
    """
    try:
        # Aseguramos que la posición sea un entero antes de indexar
        idx = int(position)
        return sequence[idx]
    except (IndexError, TypeError, ValueError):
        # Si la secuencia o el índice son inválidos, devolvemos None
        return None