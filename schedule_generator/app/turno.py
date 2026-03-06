from .local import Local
from typing import Literal

Tipo = Literal['C', 'CP', 'L']
# C CP L
class Turno:
	asignatura: str
	local: Local
	tipo_clase: Tipo
	es_vacio = True
	def __init__(self, asignatura: str = None, local: Local = None, tipo_clase: Tipo = None) -> None:
		if asignatura is not None and local is not None and tipo_clase is not None:
			self.asignatura = asignatura
			self.local = local
			self.tipo_clase = tipo_clase
			self.es_vacio = False

	def esta_vasio(self) -> bool:
		return self.es_vacio
	

	def __str__(self):
		if self.esta_vasio():
			return '___'
		else:
			#return f'{self.asignatura} {self.tipo_clase} {self.local.__str__()}'
			return f'{self.asignatura}_{self.tipo_clase}_{self.local.__str__()}'

