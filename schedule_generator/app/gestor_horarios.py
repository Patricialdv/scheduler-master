from typing import Dict, List
import copy
from .local import Local
from .turno import Turno
from .creacion_horario import CreacionHorario
from .horario import Horario


class GestorHorarios:
    lista_carga_docente_por_semana_grupo: list = []
    lista_turnos_faltantes_carga_docente: list = []

    lista_horarios_grupos: list = []

    def __init__(self, salones: List[Local], P1: dict[str, list[dict[str, str]]]) -> None:
        self.salones = salones
        self.P1 = P1
    
    
    #queda or arreglar el comportamiento de cantidad por semanas para convertirlas en una lista 
    def _separar_carga_docente(self, num_semanas: int) -> None:
        cantidad_por_semana = copy.deepcopy(self.P1)
        restantes_por_asignatura = copy.deepcopy(self.P1)
        for key in self.P1:
            num = int(len(self.P1[key])/num_semanas)
            cantidad_por_semana[key] = num if num >= 1 else 1 if num <= 5 else 5 
            restantes_por_asignatura[key] = int(len(self.P1[key])%num_semanas)

            # cantidad_por_semana[key] = []
            # for i in range(num_semanas):
            #     cantidad_por_semana[key].append()
            """
            Tengo que redondear el decimal a por encima de 0.3 se suma uno si no se queda en el mismo numero
            y luego hallar los restantes. que se hace el final rellenando el resto 
            """

        pos_por_semana = {}
        aux = []
        for key in self.P1:
            pos_por_semana[key] = 0
        for pos in range(num_semanas):
            _p1 = copy.deepcopy(self.P1)
            for  key in _p1:
                try:
                    _p1[key] = _p1[key][pos_por_semana[key]:pos_por_semana[key] + cantidad_por_semana[key]]
                except Exception as e:
                    _p1[key] = 0
                pos_por_semana[key] += cantidad_por_semana[key]
            aux.append(_p1)
        self.lista_carga_docente_por_semana_grupo.append(aux)

        self.lista_turnos_faltantes_carga_docente = copy.deepcopy(restantes_por_asignatura)
        
        
    #Crea una semana para agregar restricciones aplicables a todas las semanas del curso.
    def crear_horario_base(self, num_semanas: int) -> Horario:
        self.num_semanas = num_semanas
        self._separar_carga_docente(num_semanas)
        horario_base = [[Turno() for i in range(6)] for j in range(5)]
        return horario_base, self.lista_carga_docente_por_semana_grupo[0][0]
        
    #Crea la lista de semanas del curso para hacer ajustes finales a nivel de semana espesífica
    def crear_semanas_tipo(self, restricciones_totales):
        semanas = []
        horario_base = CreacionHorario(carga_docente=self.lista_carga_docente_por_semana_grupo[0][0], salones=self.salones, restricciones = restricciones_totales).get_horario()
        semanas.append(horario_base)
        for pos in range(1,self.num_semanas):
            p1 = self.lista_carga_docente_por_semana_grupo[0][pos]
            horario_base_por_semana = CreacionHorario(carga_docente=p1, salones=self.salones, restricciones = restricciones_totales, horario = horario_base.get_horario()).get_horario()
            semanas.append(horario_base_por_semana)
        return semanas

    def ajustar_balance_por_semana(self, num_semana, cant_turnos, pos_turno: list[Dict[int, int]]):

        pass

    def crear_horarios_grupos(self):
        pass
