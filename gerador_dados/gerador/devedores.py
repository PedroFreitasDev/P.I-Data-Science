"""1.2 Devedores (Excel).

Cada venda "Fiado" gera (ou aumenta) o débito do aluno naquele dia. Os débitos
ficam guardados no estado do gerador e a planilha é republicada a cada execução
com o status calculado na data de hoje. A quitação depende do perfil oculto do
responsável (pontual, atrasa ou inadimplente) e é sempre a mesma para um mesmo
débito, então o status só "anda para frente" com o passar dos dias.

As falhas de cada débito são sorteadas uma única vez, quando ele é criado, e
ficam gravadas no estado. Assim a mesma falha aparece em todas as versões da planilha.
"""

from datetime import date, timedelta

from .utils import rng_para, salvar_excel

FONTE = "devedores"
COLUNAS = ["id_devedor", "id_aluno", "data_divida", "valor_devido", "status", "data_quitacao"]
ARQUIVO = "devedores_atualizado.xlsx"
TIPOS_FALHA = ["id_aluno_inexistente", "status_desatualizado", "quitacao_anterior_divida",
               "registro_duplicado", "valor_invalido", "status_digitacao"]


def registrar_fiado(estado: dict, lote_vendas, seed, taxa):
    """Acrescenta ao estado os débitos gerados pelas vendas fiado do lote."""
    dividas = estado["dividas"]
    por_chave = {(d["id_aluno"], d["data"]): d for d in dividas}
    for v in lote_vendas:
        if v.forma_pagamento != "Fiado":
            continue
        chave = (v.id_aluno, v.data_hora.date().isoformat())
        if chave in por_chave:
            por_chave[chave]["valor"] = round(por_chave[chave]["valor"] + v.valor_total, 2)
            continue
        id_d = estado["proximo_id_devedor"]
        estado["proximo_id_devedor"] += 1
        divida = {"id": id_d, "id_aluno": v.id_aluno, "data": chave[1],
                  "valor": v.valor_total, "falha": None}
        rng = rng_para(seed, "falha_devedor", id_d)
        if taxa > 0 and rng.random() < taxa * 2:
            falha = {"tipo": rng.choice(TIPOS_FALHA), "sorteio": rng.random()}
            if falha["tipo"] == "registro_duplicado":
                falha["id_duplicata"] = estado["proximo_id_devedor"]
                estado["proximo_id_devedor"] += 1
            divida["falha"] = falha
        dividas.append(divida)
        por_chave[chave] = divida


def _situacao(divida: dict, pagador: str, seed, hoje: date):
    data = date.fromisoformat(divida["data"])
    rng = rng_para(seed, "quitacao", divida["id"])
    if pagador == "pontual":
        quitacao = data + timedelta(days=rng.randint(1, 15))
    elif pagador == "atrasa":
        quitacao = data + timedelta(days=rng.randint(20, 75))
    else:
        quitacao = None if rng.random() < 0.7 else data + timedelta(days=rng.randint(60, 150))
    if quitacao and quitacao > hoje:
        quitacao = None
    if quitacao:
        return "Quitado", quitacao
    return ("Atrasado" if (hoje - data).days > 30 else "Em aberto"), None


def publicar_devedores(estado: dict, alunos_por_id: dict, pasta, gabarito, seed, hoje: date):
    linhas, duplicatas = [], []
    for d in estado["dividas"]:
        # débitos de anos anteriores podem ser de alunos que não estão mais na base
        aluno = alunos_por_id.get(d["id_aluno"])
        status, quitacao = _situacao(d, aluno.pagador if aluno else "atrasa", seed, hoje)
        linha = [d["id"], d["id_aluno"], date.fromisoformat(d["data"]), d["valor"], status, quitacao]
        falha = d["falha"]
        if falha:
            dup = _aplicar_falha(linha, falha, set(alunos_por_id), gabarito)
            if dup:
                duplicatas.append(dup)
        linhas.append(linha)

    salvar_excel(pasta / ARQUIVO, COLUNAS, linhas + duplicatas, aba="devedores")


def _aplicar_falha(linha, falha, ids_validos, gabarito):
    """Aplica a falha sorteada na criação do débito. Devolve a linha duplicada, se houver."""
    id_d = linha[0]
    s = falha["sorteio"]  # valor fixo que escolhe a variante da falha

    def reg(campo, tipo, antes=None, depois=None, obs=""):
        gabarito.registrar(FONTE, ARQUIVO, id_d, campo, tipo, antes, depois, obs)

    tipo = falha["tipo"]
    quitado = linha[5] is not None
    if tipo == "id_aluno_inexistente":
        novo = [900 + int(s * 100), linha[1] * 10, 99999][int(s * 3)]
        if novo in ids_validos:
            novo = 99999
        reg("id_aluno", "id_aluno_nao_localizado", linha[1], novo)
        linha[1] = novo
    elif tipo == "status_desatualizado" and linha[4] != "Em aberto":
        obs = ("Pagamento registrado mas status não atualizado" if quitado else
               "Dívida vencida há mais de 30 dias ainda marcada como em aberto")
        reg("status", "status_desatualizado", linha[4], "Em aberto", obs)
        linha[4] = "Em aberto"
    elif tipo == "quitacao_anterior_divida" and quitado:
        novo = linha[2] - timedelta(days=3 + int(s * 37))
        reg("data_quitacao", "quitacao_anterior_divida", linha[5], novo)
        linha[5] = novo
    elif tipo == "registro_duplicado":
        dup = list(linha)
        dup[0] = falha["id_duplicata"]
        gabarito.registrar(FONTE, ARQUIVO, dup[0], "*", "registro_duplicado",
                           observacao=f"Mesmo débito do id_devedor {id_d}")
        return dup
    elif tipo == "valor_invalido":
        novo = [-linha[3], None, round(linha[3] * 100, 2)][int(s * 3)]
        reg("valor_devido", "valor_nulo" if novo is None else
            "valor_negativo" if novo < 0 else "valor_absurdo", linha[3], novo)
        linha[3] = novo
    elif tipo == "status_digitacao":
        novo = [linha[4].lower(), linha[4].upper(), linha[4] + " "][int(s * 3)]
        reg("status", "categoria_digitada_errada", linha[4], novo)
        linha[4] = novo
    # status_desatualizado / quitacao_anterior_divida só se manifestam quando o
    # status do débito permite; até lá a linha sai correta.
    return None
