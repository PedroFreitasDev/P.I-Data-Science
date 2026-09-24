"""1.5 Calendário Escolar (JSON).

Gera o calendário "real" (o que de fato aconteceu, usado para simular vendas e
perdas) e publica a versão oficial em JSON — que, como no mundo real, não foi
atualizada após a greve e as reposições, além de conter erros de digitação.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from .config import NOME_ESCOLA
from .utils import intervalo_datas, salvar_json, sortear_indices

FONTE = "calendario_escolar"


@dataclass
class Dia:
    data: date
    # Versão publicada (oficial)
    tipo_dia: str
    descricao: str
    turno_letivo: str  # integral | manha | tarde | nenhum
    # O que realmente aconteceu
    aula_manha: bool = False
    aula_tarde: bool = False
    sabado_letivo: bool = False  # todos os alunos vêm pela manhã (festa, reposição)
    evento: str = ""

    @property
    def tem_aula(self) -> bool:
        return self.aula_manha or self.aula_tarde or self.sabado_letivo


def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_nacionais(ano: int) -> dict[date, str]:
    p = pascoa(ano)
    return {
        date(ano, 1, 1): "Confraternização Universal",
        p - timedelta(days=2): "Sexta-feira Santa",
        date(ano, 4, 21): "Tiradentes",
        date(ano, 5, 1): "Dia do Trabalho",
        date(ano, 9, 7): "Independência do Brasil",
        date(ano, 10, 12): "Nossa Senhora Aparecida",
        date(ano, 11, 2): "Finados",
        date(ano, 11, 15): "Proclamação da República",
        date(ano, 11, 20): "Dia Nacional de Zumbi e da Consciência Negra",
        date(ano, 12, 25): "Natal",
    }


def _proximo_dia_semana(d: date, dia_semana: int) -> date:
    return d + timedelta(days=(dia_semana - d.weekday()) % 7)


def gerar_calendario(ano: int, rng) -> list[Dia]:
    feriados = feriados_nacionais(ano)
    p = pascoa(ano)
    recessos = {
        p - timedelta(days=48): "Carnaval (ponto facultativo)",
        p - timedelta(days=47): "Carnaval (ponto facultativo)",
        p + timedelta(days=60): "Corpus Christi (ponto facultativo)",
        date(ano, 10, 15): "Dia do Professor",
    }
    # Emendas: feriado na terça -> segunda livre; feriado na quinta -> sexta livre
    for f, nome in list(feriados.items()) + list(recessos.items()):
        if f.weekday() == 1:
            recessos.setdefault(f - timedelta(days=1), f"Emenda de feriado ({nome.split(' (')[0]})")
        elif f.weekday() == 3:
            recessos.setdefault(f + timedelta(days=1), f"Emenda de feriado ({nome.split(' (')[0]})")
    quarta_cinzas = p - timedelta(days=46)

    inicio_aulas = _proximo_dia_semana(date(ano, 2, 1), 0)
    inicio_planejamento = inicio_aulas - timedelta(days=7)
    ferias_jul_ini = _proximo_dia_semana(date(ano, 7, 5), 0)
    ferias_jul_fim = ferias_jul_ini + timedelta(days=18)
    fim_aulas = _proximo_dia_semana(date(ano, 12, 1), 4) + timedelta(days=14)

    # Conselhos de classe (fim de bimestre): tarde dispensada
    conselhos = {
        _proximo_dia_semana(date(ano, 4, 24), 4),
        ferias_jul_ini - timedelta(days=3),
        _proximo_dia_semana(date(ano, 9, 24), 4),
        _proximo_dia_semana(date(ano, 12, 1), 4),
    }
    # Festa junina: último sábado de junho
    festa_junina = _proximo_dia_semana(date(ano, 6, 24), 5)

    dias = []
    for d in intervalo_datas(date(ano, 1, 1), date(ano, 12, 31)):
        fim_semana = d.weekday() >= 5
        if d in feriados:
            dia = Dia(d, "feriado", feriados[d], "nenhum")
        elif d == festa_junina:
            dia = Dia(d, "sabado_letivo", "Festa Junina", "manha", sabado_letivo=True,
                      evento="festa_junina")
        elif fim_semana:
            dia = Dia(d, "fim_de_semana", "Fim de semana", "nenhum")
        elif d < inicio_planejamento or d > fim_aulas:
            dia = Dia(d, "ferias", "Férias escolares", "nenhum")
        elif d < inicio_aulas:
            dia = Dia(d, "planejamento", "Planejamento pedagógico (sem alunos)", "nenhum")
        elif ferias_jul_ini <= d <= ferias_jul_fim:
            dia = Dia(d, "ferias", "Férias escolares de julho", "nenhum")
        elif d in recessos:
            dia = Dia(d, "recesso", recessos[d], "nenhum")
        elif d == quarta_cinzas:
            dia = Dia(d, "letivo", "Quarta-feira de Cinzas - aulas somente à tarde", "tarde",
                      aula_tarde=True)
        elif d in conselhos:
            dia = Dia(d, "letivo", "Conselho de classe - sem aulas à tarde", "manha",
                      aula_manha=True, evento="conselho")
        else:
            desc = "Início do ano letivo" if d == inicio_aulas else "Dia letivo"
            dia = Dia(d, "letivo", desc, "integral", aula_manha=True, aula_tarde=True)
        dias.append(dia)

    _simular_greve_e_reposicao(dias, rng)
    return dias


def _simular_greve_e_reposicao(dias: list[Dia], rng):
    """Greve de 1 semana em set/out e reposição aos sábados de novembro.

    O calendário publicado NÃO é atualizado: continua marcando a semana de greve
    como letiva e os sábados de reposição como fim de semana.
    """
    por_data = {d.data: d for d in dias}
    candidatas = []
    for d in dias:
        if d.data.weekday() == 0 and d.data.month in (9, 10):
            semana = [por_data.get(d.data + timedelta(days=i)) for i in range(5)]
            if all(s and s.tipo_dia == "letivo" and s.turno_letivo == "integral" for s in semana):
                candidatas.append(semana)
    if not candidatas:
        return
    semana = rng.choice(candidatas)
    for s in semana:
        s.aula_manha = s.aula_tarde = False
        s.evento = "greve"

    sabados = [d for d in dias if d.data.month == 11 and d.data.weekday() == 5
               and d.tipo_dia == "fim_de_semana"]
    for s in sabados[:len(semana)]:
        s.sabado_letivo = True
        s.evento = "reposicao"


def publicar_calendario(dias: list[Dia], pasta, gabarito, taxa, rng, ano):
    arquivo = f"calendario_escolar_{ano}.json"
    registros = [
        {"data": d.data.isoformat(), "tipo_dia": d.tipo_dia,
         "descricao": d.descricao, "turno_letivo": d.turno_letivo}
        for d in dias
    ]

    # Inconsistências "estruturais" (acontecem mesmo com taxa baixa)
    for d in dias:
        if d.evento == "greve":
            gabarito.registrar(FONTE, arquivo, d.data.isoformat(), "tipo_dia",
                               "calendario_desatualizado", "sem_aula (greve)", d.tipo_dia,
                               "Greve não refletida no calendário publicado")
        elif d.evento == "reposicao":
            gabarito.registrar(FONTE, arquivo, d.data.isoformat(), "tipo_dia",
                               "calendario_desatualizado", "sabado_letivo (reposição)",
                               d.tipo_dia, "Reposição de aulas não refletida no calendário")

    if taxa > 0:
        # Conflito: feriado nacional marcado como dia letivo
        feriados_uteis = [i for i, d in enumerate(dias)
                          if d.tipo_dia == "feriado" and d.data.weekday() < 5
                          and d.data.month not in (1, 12)]
        for i in rng.sample(feriados_uteis, min(2, len(feriados_uteis))):
            r = registros[i]
            gabarito.registrar(FONTE, arquivo, r["data"], "tipo_dia", "conflito_feriado_letivo",
                               "feriado", "letivo", f"Feriado nacional: {r['descricao']}")
            r.update(tipo_dia="letivo", descricao="Dia letivo", turno_letivo="integral")

    variacoes = {"letivo": ["Letivo", "letivo ", "LETIVO", "letivos"],
                 "fim_de_semana": ["fim de semana", "Fim_de_semana"],
                 "feriado": ["Feriado", "feriado "],
                 "ferias": ["férias", "Ferias"],
                 "recesso": ["Recesso"]}
    for i in sortear_indices(rng, len(registros), taxa * 0.5, minimo=3):
        r = registros[i]
        if rng.random() < 0.6 and r["tipo_dia"] in variacoes:
            novo = rng.choice(variacoes[r["tipo_dia"]])
            gabarito.registrar(FONTE, arquivo, r["data"], "tipo_dia", "categoria_digitada_errada",
                               r["tipo_dia"], novo)
            r["tipo_dia"] = novo
        else:
            gabarito.registrar(FONTE, arquivo, r["data"], "turno_letivo", "campo_ausente",
                               r["turno_letivo"], None)
            del r["turno_letivo"]

    salvar_json(pasta / arquivo, {
        "escola": NOME_ESCOLA,
        "ano": ano,
        "publicado_em": f"{ano - 1}-12-10",
        "dias": registros,
    })
