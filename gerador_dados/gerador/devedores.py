"""1.2 Devedores (Excel).

As dívidas nascem das vendas "Fiado": no fechamento de cada mês, o total
anotado de cada aluno vira um débito. A quitação depende do perfil oculto do
responsável (pontual, atrasa ou inadimplente). O status é calculado na data
de referência da planilha.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from .utils import salvar_excel, sortear_indices

FONTE = "devedores"
COLUNAS = ["id_devedor", "id_aluno", "data_divida", "valor_devido", "status", "data_quitacao"]


@dataclass
class Divida:
    id: int
    id_aluno: int
    data_divida: date
    valor: float
    status: str
    data_quitacao: date | None


def gerar_devedores(vendas, turmas, data_referencia: date, rng) -> list[Divida]:
    alunos = {a.id: a for t in turmas for a in t.alunos}
    totais = {}
    for v in vendas:
        if v.forma_pagamento == "Fiado":
            chave = (v.id_aluno, v.data_hora.year, v.data_hora.month)
            totais[chave] = totais.get(chave, 0) + v.valor_total

    dividas = []
    for (id_aluno, ano, mes), valor in sorted(totais.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0])):
        fechamento = min(date(ano, mes, calendar.monthrange(ano, mes)[1]), data_referencia)
        perfil = alunos[id_aluno].pagador
        if perfil == "pontual":
            quitacao = fechamento + timedelta(days=rng.randint(1, 15))
        elif perfil == "atrasa":
            quitacao = fechamento + timedelta(days=rng.randint(20, 75))
        else:
            quitacao = None if rng.random() < 0.7 else fechamento + timedelta(days=rng.randint(60, 150))
        if quitacao and quitacao > data_referencia:
            quitacao = None

        if quitacao:
            status = "Quitado"
        elif (data_referencia - fechamento).days > 30:
            status = "Atrasado"
        else:
            status = "Em aberto"
        dividas.append(Divida(len(dividas) + 1, id_aluno, fechamento, round(valor, 2), status, quitacao))
    return dividas


def publicar_devedores(dividas: list[Divida], ids_validos: set[int], pasta, gabarito, taxa, rng,
                       data_referencia: date):
    arquivo = f"devedores_atualizado_{data_referencia.isoformat()}.xlsx"
    linhas = [[d.id, d.id_aluno, d.data_divida, d.valor, d.status, d.data_quitacao]
              for d in dividas]
    extras = []
    proximo_id = len(linhas) + 1
    ex_alunos = [i for i in range(900, 1000)]  # matrículas antigas, fora da base atual

    for i in sorted(sortear_indices(rng, len(linhas), taxa * 2, minimo=4)):
        linha = linhas[i]
        id_d = linha[0]

        def reg(campo, tipo, antes=None, depois=None, obs="", id_d=id_d):
            gabarito.registrar(FONTE, arquivo, id_d, campo, tipo, antes, depois, obs)

        tipo = rng.choice(["id_aluno_inexistente", "status_desatualizado",
                           "quitacao_anterior_divida", "registro_duplicado",
                           "valor_invalido", "status_digitacao"])
        quitado = linha[5] is not None

        if tipo == "id_aluno_inexistente":
            novo = rng.choice(ex_alunos + [linha[1] * 10, 99999])
            if novo in ids_validos:
                novo = 99999
            reg("id_aluno", "id_aluno_nao_localizado", linha[1], novo)
            linha[1] = novo
        elif tipo == "status_desatualizado" and quitado:
            reg("status", "status_desatualizado", linha[4], "Em aberto",
                "Pagamento registrado mas status não atualizado")
            linha[4] = "Em aberto"
        elif tipo == "status_desatualizado" and linha[4] == "Atrasado":
            reg("status", "status_desatualizado", linha[4], "Em aberto",
                "Dívida vencida há mais de 30 dias ainda marcada como em aberto")
            linha[4] = "Em aberto"
        elif tipo == "quitacao_anterior_divida" and quitado:
            novo = linha[2] - timedelta(days=rng.randint(3, 40))
            reg("data_quitacao", "quitacao_anterior_divida", linha[5], novo)
            linha[5] = novo
        elif tipo == "registro_duplicado":
            dup = list(linha)
            dup[0] = proximo_id
            proximo_id += 1
            gabarito.registrar(FONTE, arquivo, dup[0], "*", "registro_duplicado",
                               observacao=f"Mesmo débito do id_devedor {id_d}")
            extras.append(dup)
        elif tipo == "valor_invalido":
            novo = rng.choice([-linha[3], None, round(linha[3] * 100, 2)])
            reg("valor_devido", "valor_nulo" if novo is None else
                "valor_negativo" if novo < 0 else "valor_absurdo", linha[3], novo)
            linha[3] = novo
        else:
            novo = rng.choice([linha[4].lower(), linha[4].upper(), linha[4] + " "])
            reg("status", "categoria_digitada_errada", linha[4], novo)
            linha[4] = novo

    linhas.extend(extras)  # lançamentos repetidos entram no fim, como numa planilha manual
    salvar_excel(pasta / arquivo, COLUNAS, linhas, aba="devedores")
