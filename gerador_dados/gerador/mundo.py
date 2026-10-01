"""O "mundo real" simulado de um ano: calendário, clima, inflação, cardápio e turmas.

Tudo é determinístico a partir da semente e do ano. Por isso as vendas de
qualquer dia podem ser recalculadas a qualquer momento sem guardar estado.
"""

from datetime import date
from functools import lru_cache

from . import alunos, calendario, cardapio, clima, inflacao, vendas
from .utils import rng_para


class Mundo:
    def __init__(self, seed: int, ano: int, min_alunos: int, max_alunos: int):
        self.seed = seed
        self.ano = ano
        self.dias = calendario.gerar_calendario(ano, rng_para(seed, "calendario", ano))
        self.dia_por_data = {d.data: d for d in self.dias}
        self.clima = clima.gerar_clima(ano, rng_para(seed, "clima", ano))
        self.inflacao = inflacao.gerar_inflacao(ano, rng_para(seed, "inflacao", ano))
        vigencia_1 = next(d.data for d in self.dias if d.tipo_dia == "planejamento")
        vigencia_2 = next(d.data for d in self.dias if d.data > date(ano, 7, 5) and d.tem_aula)
        self.cardapios = cardapio.gerar_cardapios(vigencia_1, vigencia_2, self.inflacao,
                                                  rng_para(seed, "cardapio", ano))
        self.turmas = alunos.gerar_turmas(ano, rng_para(seed, "turmas", ano), min_alunos, max_alunos)
        self.alunos_por_id = {a.id: a for t in self.turmas for a in t.alunos}

    def vendas_do_dia(self, d: date, primeiro_id: int = 1) -> list:
        """Todas as vendas que acontecem no dia `d` (em ordem cronológica)."""
        return vendas.simular_dia(self.dia_por_data[d], self.clima[d], self.turmas,
                                  self.cardapios.disponiveis(d), primeiro_id,
                                  rng_para(self.seed, "vendas", d))


@lru_cache(maxsize=4)
def mundo(seed: int, ano: int, min_alunos: int, max_alunos: int) -> Mundo:
    return Mundo(seed, ano, min_alunos, max_alunos)
