"""1.2 Devedores (Excel).

Cada dia em que um aluno compra "Fiado" gera um débito (a soma do fiado dele no
dia). A planilha é recalculada a cada execução a partir das vendas já
registradas no histórico, com o status do dia de hoje. A quitação depende do
perfil oculto do responsável (pontual, atrasa ou inadimplente) e é sempre a
mesma para um mesmo débito, então o status só "anda para frente" com o tempo.

Os ids e as falhas de cada débito dependem apenas da ordem cronológica dos
débitos, que nunca muda (débitos novos entram sempre no fim). Assim a mesma
falha aparece no mesmo débito em todas as versões da planilha.
"""

from datetime import date, timedelta

from .utils import rng_para, salvar_excel

COLUNAS = ["id_devedor", "id_aluno", "data_divida", "valor_devido", "status", "data_quitacao"]
ARQUIVO = "devedores_atualizado.xlsx"
TIPOS_FALHA = ["id_aluno_inexistente", "status_desatualizado", "quitacao_anterior_divida",
               "registro_duplicado", "valor_invalido", "status_digitacao"]


def montar_dividas(vendas_fiado, seed, taxa) -> list[dict]:
    """Agrupa o fiado por (aluno, dia) na ordem em que os débitos surgiram."""
    dividas, por_chave = [], {}
    proximo_id = 1
    for v in sorted(vendas_fiado, key=lambda v: (v.data_hora, v.id)):
        chave = (v.id_aluno, v.data_hora.date())
        if chave in por_chave:
            por_chave[chave]["valor"] = round(por_chave[chave]["valor"] + v.valor_total, 2)
            continue
        divida = {"id": proximo_id, "id_aluno": v.id_aluno, "data": chave[1],
                  "valor": v.valor_total, "falha": None}
        proximo_id += 1
        rng = rng_para(seed, "falha_devedor", divida["id"])
        if taxa > 0 and rng.random() < taxa * 2:
            divida["falha"] = {"tipo": rng.choice(TIPOS_FALHA), "sorteio": rng.random()}
            if divida["falha"]["tipo"] == "registro_duplicado":
                divida["falha"]["id_duplicata"] = proximo_id
                proximo_id += 1
        dividas.append(divida)
        por_chave[chave] = divida
    return dividas


def _situacao(divida: dict, pagador: str, seed, hoje: date):
    data = divida["data"]
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


def publicar_devedores(dividas: list[dict], pagador_de, ids_validos: set, pasta, seed,
                       hoje: date) -> bool:
    """`pagador_de(id_aluno, data)` devolve o perfil de pagamento do aluno."""
    linhas, duplicatas = [], []
    for d in dividas:
        status, quitacao = _situacao(d, pagador_de(d["id_aluno"], d["data"]), seed, hoje)
        linha = [d["id"], d["id_aluno"], d["data"], d["valor"], status, quitacao]
        if d["falha"]:
            dup = _aplicar_falha(linha, d["falha"], ids_validos)
            if dup:
                duplicatas.append(dup)
        linhas.append(linha)
    return salvar_excel(pasta / ARQUIVO, COLUNAS, linhas + duplicatas, aba="devedores")


def _aplicar_falha(linha, falha, ids_validos):
    """Aplica a falha sorteada para o débito. Devolve a linha duplicada, se houver."""
    s = falha["sorteio"]  # valor fixo que escolhe a variante da falha
    tipo = falha["tipo"]
    quitado = linha[5] is not None
    if tipo == "id_aluno_inexistente":
        novo = [900 + int(s * 100), linha[1] * 10, 99999][int(s * 3)]
        linha[1] = 99999 if novo in ids_validos else novo
    elif tipo == "status_desatualizado" and linha[4] != "Em aberto":
        # pago (ou vencido há mais de 30 dias), mas o status não foi atualizado
        linha[4] = "Em aberto"
    elif tipo == "quitacao_anterior_divida" and quitado:
        linha[5] = linha[2] - timedelta(days=3 + int(s * 37))
    elif tipo == "registro_duplicado":
        dup = list(linha)
        dup[0] = falha["id_duplicata"]
        return dup
    elif tipo == "valor_invalido":
        linha[3] = [-linha[3], None, round(linha[3] * 100, 2)][int(s * 3)]
    elif tipo == "status_digitacao":
        linha[4] = [linha[4].lower(), linha[4].upper(), linha[4] + " "][int(s * 3)]
    # status_desatualizado / quitacao_anterior_divida só se manifestam quando o
    # status do débito permite; até lá a linha sai correta.
    return None
