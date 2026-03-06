from typing import Literal, Dict
from .restricciones_interface import RestriccionInterface
from .local import Local
from .turno import Turno
import random
import copy



TIPO_CLASE = ["C", "CP", "L"]
TIPO_LOCAL = ["S", "A", "L"]
TIPO_CLASE_LOCAL = {
    "C": "S",
    "CP": "A",
    "L": "L",
}
NUM_TURNOS = 6


class Horario:
    horario: list[list[Turno]]
    restricciones: list[list[RestriccionInterface]]
    asignauras: list[str]
    locales: list[Local]
    p1: Dict[str, list[str]]
    semanas: int
    puntuacion: int = 0

    def __init__(
        self,
        semanas: int,
        asignaturas: list[str],
        locales: list[Local],
        restricciones: list[list[RestriccionInterface]],
        p1: list[list],
        horario: list = None,
    ) -> None:
        self.asignaturas = asignaturas
        self.locales = locales
        self.restricciones = restricciones
        self.p1 = p1
        self.horario = horario if horario else []
        self.semanas = semanas

    def turno_aleatorio(self, lis_asignaturas=None, tipo_clase_ = None) -> Turno:
        asignaturas = lis_asignaturas if lis_asignaturas else self.asignaturas
        asig = random.randint(0, len(asignaturas) - 1)
        tipo_ = random.randint(0, 2)
        tipo_clase = TIPO_CLASE[tipo_] 
        if tipo_clase_:
            tipo_clase_ = tipo_clase_    
        tipo_local = TIPO_CLASE_LOCAL[tipo_clase]
        locales = [loc for loc in self.locales if loc.tipo == tipo_local]
        local = random.randint(0, len(locales) - 1)
        turno = Turno(
            asignatura=asignaturas[asig], tipo_clase=tipo_clase, local=locales[local]
        )
        return turno

    def get_puntuacion(self):
        return self.puntuacion

    def get_horario(self) -> list[list]:
        return copy.deepcopy(self.horario)

    def set_horario(self, horario: list[list]) -> None:
        self.horario = horario

    def ajuste_de_carga(self) -> None:
        for key in self.p1:
            pos = 0
            for dia in range(len(self.horario)):
                for turno in range(len(self.horario[0])):
                    turno_ = self.horario[dia][turno]
                    if not turno_.esta_vasio():
                        if ( turno_.asignatura == key):
                            if(len(self.p1[key]) == 0) | (pos >= len(self.p1[key])):
                                self.horario[dia][turno] = Turno()
                            elif turno_.tipo_clase is not self.p1[key][pos]:
                                turno_.tipo_clase = self.p1[key][pos]
                                locales = [
                                    loc
                                    for loc in self.locales
                                    if loc.tipo == TIPO_CLASE_LOCAL[self.p1[key][pos]['type']]
                                ]
                                turno_.local = locales[0]
                                self.horario[dia][turno] = turno_
                            pos+=1
                            

    def generar(self):
        self.horario = []
        turnos = NUM_TURNOS
        dias = self.semanas * 5
        for d in range(dias):
            dia = []
            for t in range(turnos):
                dia.append(self.turno_aleatorio())
            self.horario.append(dia)

    def fucionar(self, horario_b: list[list]) -> None:
        dias = self.semanas * 5
        for i in range(dias):
            if random.randint(0, 100) < 30:
                self.horario[i] = horario_b[i]

    def mutar(self) -> None:
        if random.randint(0, 10000) < 1000 and random.randint(0, 100) > 50:
            dias = self.semanas * 5
            turnos = NUM_TURNOS
            for d in range(dias):
                for t in range(turnos):
                    if (
                        self.horario[d][t].esta_vasio()
                        and random.randint(0, 10000) < 20
                    ):
                        lista_asignaturas = [
                            turn.asignatura
                            for turn in self.horario[d]
                            if not turn.esta_vasio()
                        ]
                        asignaturas_restantes = [
                            elemento
                            for elemento in self.asignaturas
                            if elemento not in lista_asignaturas
                        ]
                        turno_nuevo = self.turno_aleatorio(asignaturas_restantes)
                        self.horario[d][t] = turno_nuevo
                    if (
                        not self.horario[d][t].esta_vasio()
                        and random.randint(0, 10000) < 50
                    ):
                        if random.randint(0, 100) > 80:
                            lista_asignaturas = [
                                turn.asignatura
                                for turn in self.horario[d]
                                if not turn.esta_vasio()
                            ]
                            asignaturas_restantes = [
                                elemento
                                for elemento in self.asignaturas
                                if elemento not in lista_asignaturas
                            ]
                            turno_nuevo = self.turno_aleatorio(asignaturas_restantes)
                            self.horario[d][t] = turno_nuevo
                        else:
                            self.horario[d][t] = Turno()
        else:
            self.mutacion_celectiva()

    def mutacion_celectiva(self) -> None:
        if random.randint(0, 10000) < 2000:
            d = random.randint(0, (self.semanas * 5) - 1)
            t = random.randint(0, NUM_TURNOS-1)
            if random.randint(0, 100) > 50:
                lista_asignaturas = [
                    turn.asignatura for turn in self.horario[d] if not turn.esta_vasio()
                ]
                asignaturas_restantes = [
                    elemento
                    for elemento in self.asignaturas
                    if elemento not in lista_asignaturas
                ]
                if not self.horario[d][t].esta_vasio():
                    asignaturas_restantes.append(self.horario[d][t].asignatura)
                turno_nuevo = self.turno_aleatorio(asignaturas_restantes)
                self.horario[d][t] = turno_nuevo
            else:
                self.horario[d][t] = Turno()

    def calcular_puntuacion(self) -> None:
        self.puntuacion = 0
        turnos = NUM_TURNOS
        dias = self.semanas * 5
        asignaturas_presentes = copy.deepcopy(self.p1)
        for a in asignaturas_presentes:
            asignaturas_presentes[a] = 0
        pos = copy.deepcopy(self.p1)
        for p in pos:
            pos[p] = 0
        for d in range(dias):
            self.encontrar_duplicados(self.horario[d])
            asignaturas_por_dia = {}
            for a in self.asignaturas:
                asignaturas_por_dia[a] = 0
            for t in range(turnos):
                self.validar_restriccion(d,t)
                if not self.horario[d][t].esta_vasio():
                    if asignaturas_por_dia[self.horario[d][t].asignatura] == 0:
                        asignaturas_presentes[self.horario[d][t].asignatura] += 1

                    if pos[self.horario[d][t].asignatura] >= len(
                        self.p1[self.horario[d][t].asignatura]
                    ):
                        self.puntuacion += 10
                    else:
                        if asignaturas_por_dia[self.horario[d][t].asignatura] == 0:
                            if (
                                self.p1[self.horario[d][t].asignatura][pos[self.horario[d][t].asignatura]]
                                is not self.horario[d][t].tipo_clase
                            ):
                                if random.randint(0,1000) < 50:
                                    self.horario[d][t] = self.turno_aleatorio([self.horario[d][t].asignatura], tipo_clase_ = self.p1[self.horario[d][t].asignatura][pos[self.horario[d][t].asignatura]])
                                else:
                                    self.puntuacion += 2
                            pos[self.horario[d][t].asignatura] += 1

                    asignaturas_por_dia[self.horario[d][t].asignatura] = 1

        for key in pos:
            puntos = (
                (len(self.p1[key])) - pos[key] if (len(self.p1[key])) > pos[key] else 0
            )
            self.puntuacion += puntos * 10
        self.puntos_porasigaturas_faltantes(asignaturas_presentes)
        


    def encontrar_duplicados(self, lista: Turno) -> None:
        asignaturas_repetidas = {}
        for elemento in lista:
            if not elemento.esta_vasio():
                if elemento.asignatura in asignaturas_repetidas:
                    asignaturas_repetidas[elemento.asignatura] += 1
                else:
                    asignaturas_repetidas[elemento.asignatura] = 1

        for key in asignaturas_repetidas:
            if asignaturas_repetidas[key] > 1:
                self.puntuacion += asignaturas_repetidas[key]

    def puntos_porasigaturas_faltantes(self, asignaturas: Dict) -> None:
        for key in asignaturas:
            if asignaturas[key] == 0 and len(self.p1[key]) > 0:
                self.puntuacion += 40

    def validar_restriccion(self, d: int, t: int) -> None:
        if self.restricciones:
            self.puntuacion += self.restricciones[d][t].evaluar(self.horario[d][t]) * 45
            if self.restricciones[d][t].evaluar(self.horario[d][t]) == 1:
                if self.restricciones[d][t].tipo == 1:
                    self.horario[d][t] = Turno()
                else:
                    self.horario[d][t] = self.turno_aleatorio()
    
