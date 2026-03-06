from .horario import Horario
import copy

class CreacionHorario:
    def __init__(self, carga_docente, salones, restricciones, horario = None) -> None:
        asignaturas = [asig for asig in carga_docente]
        if horario:
            self.Horario_final = Horario(
                        1,
                        asignaturas,
                        salones,
                        restricciones,
                        copy.deepcopy(carga_docente),
                        horario
                )
            self.Horario_final.ajuste_de_carga()
        else:
            horarios: list[Horario] = []
            for i in range(1000):
                H = Horario(
                    1,
                    asignaturas,
                    salones,
                    restricciones,
                    copy.deepcopy(carga_docente),
                )
                H.generar()
                H.calcular_puntuacion()
                horarios.append(H)

            for i in range(10000):
                horarios = self.epoca(horarios)
                if i % 10 == 0:
                    horarios.sort(key=lambda x: x.get_puntuacion())
                    # print(horarios[0].get_puntuacion())
                    if horarios[0].get_puntuacion() == 0:
                        break
            self.Horario_final = horarios[0]


    def get_horario(self) -> Horario:
        return copy.deepcopy(self.Horario_final)
    

    def epoca(self, horarios: list[Horario]) -> list[Horario]:
        horarios.sort(key=lambda x: x.get_puntuacion())

        mejores_horarios = horarios[0:10]
        nuevos_horarios: list[Horario] = []
        for i in range(10):
            for j in range(10):
                if i is not j:
                    nuevo_h = copy.deepcopy(mejores_horarios[i])
                    nuevo_h.fucionar(mejores_horarios[j].get_horario())
                    nuevo_h.mutar()
                    nuevo_h.calcular_puntuacion()
                    nuevos_horarios.append(nuevo_h)
        nuevos_horarios.extend(copy.deepcopy(mejores_horarios))

        return nuevos_horarios
