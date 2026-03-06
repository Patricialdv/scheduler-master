from typing import Literal

Tipo = Literal['A','S','L']

class Local:
	tipo: Tipo
	numero: int
	def __init__(self, tipo: Tipo, numero: int):
		self.tipo = tipo
		self.numero = numero

	def __str__(self):
		return f'{self.tipo} {self.numero}'

