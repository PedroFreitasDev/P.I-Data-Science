"""1.7 Turmas e Alunos (JSON, exportação do sistema de gestão escolar).

A idade de cada aluno é coerente com a série: segue a regra de corte de
31/03 (6 anos completos para o 1º ano do EF), com uma pequena parcela de
alunos um ano mais velhos (repetentes). Cada aluno também recebe um "perfil"
oculto de consumo/pagamento, usado para simular vendas e dívidas.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from .config import (NOMES_FEMININOS, NOMES_MASCULINOS, PESOS_PAGAMENTO, RESTRICOES,
                     SOBRENOMES, TAGS_POR_RESTRICAO)
from .utils import salvar_json, sortear_indices

FONTE = "turmas_alunos"


@dataclass
class Turma:
    nome: str
    serie: int  # 1..9 = Ensino Fundamental, 10..12 = 1ª..3ª série do Ensino Médio
    turno: str
    alunos: list = field(default_factory=list)

    @property
    def segmento(self) -> str:
        return "EF1" if self.serie <= 5 else "EF2" if self.serie <= 9 else "EM"


@dataclass
class Aluno:
    id: int
    nome: str
    data_nascimento: date
    restricao: str
    turma: Turma
    # perfil oculto (não exportado)
    propensao: float = 0.4
    pesos_pagamento: dict = field(default_factory=dict)
    pagador: str = "pontual"  # pontual | atrasa | inadimplente

    @property
    def serie(self):
        return self.turma.serie

    @property
    def turno(self):
        return self.turma.turno

    @property
    def tags_proibidas(self):
        return TAGS_POR_RESTRICAO[self.restricao]


def nome_turma(serie: int, letra: str) -> str:
    return f"{serie}º ano {letra}" if serie <= 9 else f"{serie - 9}ª série EM {letra}"


def _data_nascimento(serie: int, ano: int, rng) -> date:
    """Nascido entre 01/04 e 31/03 de forma a ter (serie + 5) anos em 31/03 do ano letivo."""
    atraso = 1 if serie >= 2 and rng.random() < 0.06 else 0  # repetente
    ini = date(ano - serie - 6 - atraso, 4, 1)
    fim = date(ano - serie - 5 - atraso, 3, 31)
    return ini + timedelta(days=rng.randint(0, (fim - ini).days))


def _nome(rng) -> str:
    primeiro = rng.choice(NOMES_FEMININOS if rng.random() < 0.5 else NOMES_MASCULINOS)
    sobrenomes = rng.sample(SOBRENOMES, rng.choice([1, 2, 2]))
    return " ".join([primeiro, *sobrenomes])


def gerar_turmas(ano: int, rng, min_alunos: int, max_alunos: int) -> list[Turma]:
    turmas = []
    for serie in range(1, 13):
        for letra in "AB":
            turno = "tarde" if serie <= 5 and letra == "B" else "manha"
            turmas.append(Turma(nome_turma(serie, letra), serie, turno))

    restricoes = [r[0] for r in RESTRICOES]
    pesos_restricao = [r[1] for r in RESTRICOES]
    proximo_id = 1001
    # Matrículas mais antigas (ids menores) para as séries mais avançadas
    for turma in sorted(turmas, key=lambda t: -t.serie):
        for _ in range(rng.randint(min_alunos, max_alunos)):
            seg = turma.segmento
            pesos = {k: v * rng.uniform(0.5, 1.5) for k, v in PESOS_PAGAMENTO[seg].items()}
            if rng.random() < (0.25 if seg == "EF1" else 0.12):
                pesos["Fiado"] = 60  # família com conta na cantina
            aluno = Aluno(
                id=proximo_id,
                nome=_nome(rng),
                data_nascimento=_data_nascimento(turma.serie, ano, rng),
                restricao=rng.choices(restricoes, weights=pesos_restricao)[0],
                turma=turma,
                propensao=rng.betavariate(2, 3) * (0.8 if seg == "EF1" else 1.0),
                pesos_pagamento=pesos,
                pagador=rng.choices(["pontual", "atrasa", "inadimplente"], weights=[6, 3, 1])[0],
            )
            turma.alunos.append(aluno)
            proximo_id += rng.choice([1, 1, 1, 2, 3])  # lacunas = transferências antigas

    # Homônimos: alguns alunos diferentes com exatamente o mesmo nome
    todos = [a for t in turmas for a in t.alunos]
    for _ in range(3):
        a, b = rng.sample(todos, 2)
        b.nome = a.nome
    return turmas


def publicar_turmas(turmas: list[Turma], pasta, gabarito, taxa, rng, ano):
    arquivo = f"turmas_alunos_{ano}.json"
    turmas_json = []
    alunos_json = []
    for t in turmas:
        tj = {"turma": t.nome, "ano_letivo": ano, "turno": t.turno, "alunos": []}
        for a in t.alunos:
            aj = {"id_aluno": a.id, "nome": a.nome,
                  "data_nascimento": a.data_nascimento.isoformat(),
                  "restricao_alimentar": a.restricao}
            tj["alunos"].append(aj)
            alunos_json.append(aj)
        turmas_json.append(tj)

    # Homônimos (não é erro de digitação, mas exige cuidado no pipeline)
    vistos = {}
    for aj in alunos_json:
        if aj["nome"] in vistos:
            gabarito.registrar(FONTE, arquivo, aj["id_aluno"], "nome", "nome_duplicado",
                               observacao=f"Mesmo nome do aluno {vistos[aj['nome']]}")
        vistos.setdefault(aj["nome"], aj["id_aluno"])

    for i in sortear_indices(rng, len(turmas_json), taxa, minimo=1):
        tj = turmas_json[i]
        gabarito.registrar(FONTE, arquivo, tj["turma"], "turno", "campo_aninhado_ausente",
                           tj["turno"], None)
        del tj["turno"]

    for i in sortear_indices(rng, len(alunos_json), taxa, minimo=3):
        aj = alunos_json[i]
        tipo = rng.choice(["id_formato_divergente", "id_formato_divergente", "campo_ausente",
                           "data_nascimento_invalida", "data_formato_divergente",
                           "nome_fora_do_padrao"])
        id_ = aj["id_aluno"]
        if tipo == "id_formato_divergente":
            novo = rng.choice([f"{id_:06d}", f"ALU{id_:05d}", str(id_)])
            gabarito.registrar(FONTE, arquivo, id_, "id_aluno", tipo, id_, novo)
            aj["id_aluno"] = novo
        elif tipo == "campo_ausente":
            campo = rng.choice(["data_nascimento", "restricao_alimentar"])
            gabarito.registrar(FONTE, arquivo, id_, campo, "campo_aninhado_ausente", aj[campo], None)
            del aj[campo]
        elif tipo == "data_nascimento_invalida":
            # erros evidentes de digitação/sistema, nunca uma idade "quase plausível"
            novo = rng.choice(["1900-01-01", f"{ano + 1}-{aj['data_nascimento'][5:]}",
                               "0" + aj["data_nascimento"][1:]])
            gabarito.registrar(FONTE, arquivo, id_, "data_nascimento", tipo,
                               aj["data_nascimento"], novo)
            aj["data_nascimento"] = novo
        elif tipo == "data_formato_divergente":
            a, m, d = aj["data_nascimento"].split("-")
            novo = f"{d}/{m}/{a}"
            gabarito.registrar(FONTE, arquivo, id_, "data_nascimento", tipo,
                               aj["data_nascimento"], novo)
            aj["data_nascimento"] = novo
        else:
            novo = rng.choice([aj["nome"].upper(), f" {aj['nome']}  ", aj["nome"].lower()])
            gabarito.registrar(FONTE, arquivo, id_, "nome", "texto_fora_do_padrao", aj["nome"], novo)
            aj["nome"] = novo

    salvar_json(pasta / arquivo, {
        "sistema": "SGE - Sistema de Gestão Escolar (exportação simulada)",
        "ano_letivo": ano,
        "turmas": turmas_json,
    })
