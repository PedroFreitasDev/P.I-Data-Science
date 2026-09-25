"""1.1 Vendas (Excel).

Cada execução gera apenas vendas do próprio dia, entre 75 e 150 no total. O
conjunto de vendas do dia é determinístico (depende só da semente e da data), e
cada execução grava somente as que já aconteceram até o horário atual e ainda
não foram registradas. Assim, uma execução às 13h registra a manhã e outra às
19h registra a tarde, sem duplicar nada.

A simulação respeita:
- só há vendas em dias em que realmente houve aula (greve = sem vendas;
  reposição aos sábados = com vendas, mesmo fora do calendário publicado);
- cada aluno compra apenas no seu turno e nos horários de entrada/intervalo/saída;
- restrições alimentares (ex.: celíaco não compra coxinha) e faixa etária;
- clima do dia (dias quentes vendem mais bebidas geladas/picolé, dias frios
  mais chocolate quente/misto quente; chuva reduz a presença);
- preço vigente do cardápio na data da venda.
"""

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path

from .config import ITENS_MULTIPLOS
from .utils import escolha_ponderada, salvar_excel

FONTE = "vendas"
COLUNAS = ["id_venda", "data_hora", "id_aluno", "id_produto", "quantidade",
           "valor_unitario", "valor_total", "forma_pagamento"]
ARQUIVO_HISTORICO = "historico_vendas.xlsx"
VENDAS_MIN_DIA, VENDAS_MAX_DIA = 75, 150

FATOR_DIA_SEMANA = {0: 0.95, 1: 1.0, 2: 1.0, 3: 1.02, 4: 1.15, 5: 1.0}
JANELAS = {
    "manha": [((6, 45), (7, 10), 15), ((9, 30), (9, 50), 70), ((12, 20), (12, 40), 15)],
    "tarde": [((12, 45), (13, 10), 15), ((15, 10), (15, 30), 70), ((17, 50), (18, 10), 15)],
    "sabado": [((8, 0), (12, 0), 100)],
}


@dataclass
class Venda:
    id: int
    data_hora: datetime
    id_aluno: int
    id_produto: int
    quantidade: int
    valor_unitario: float
    valor_total: float
    forma_pagamento: str


def fim_expediente(dia) -> time:
    """Horário a partir do qual não há mais vendas no dia (fechamento da cantina)."""
    if dia.sabado_letivo:
        return time(12, 30)
    return time(18, 30) if dia.aula_tarde else time(13, 0)


def _horario(d, janela, rng) -> datetime:
    (h1, m1), (h2, m2), _ = janela
    ini = datetime.combine(d, time(h1, m1))
    fim = datetime.combine(d, time(h2, m2))
    return ini + timedelta(seconds=rng.randint(0, int((fim - ini).total_seconds())))


def _peso_produto(item, clima_dia) -> float:
    p = item.produto
    w = p.popularidade
    if p.clima == "quente":
        w *= min(3.0, max(0.3, math.exp((clima_dia["temperatura_max"] - 26) / 4)))
    elif p.clima == "frio":
        w *= min(3.0, max(0.3, math.exp((19 - clima_dia["temperatura_media"]) / 3)))
    return w


def simular_dia(dia, clima_dia, turmas, itens, primeiro_id: int, rng) -> list[Venda]:
    """Todas as vendas do dia, em ordem cronológica, com ids a partir de `primeiro_id`."""
    if not dia.tem_aula:
        return []
    chuva = clima_dia["condicao"] in ("chuva", "tempestade")
    presenca = 0.87 if chuva else 0.93
    if dia.sabado_letivo:
        presenca = 0.75 if dia.evento == "festa_junina" else 0.85

    presentes = []
    for aluno in (a for t in turmas for a in t.alunos):
        if dia.sabado_letivo:
            janelas = JANELAS["sabado"]
        elif (aluno.turno == "manha" and dia.aula_manha) or (aluno.turno == "tarde" and dia.aula_tarde):
            janelas = JANELAS[aluno.turno]
        else:
            continue
        if rng.random() < presenca:
            presentes.append((aluno, janelas))
    if not presentes:
        return []

    # Volume do dia: clima, dia da semana, início do mês (mesada) e eventos
    fator = FATOR_DIA_SEMANA[dia.data.weekday()] * (0.9 if chuva else 1.0)
    if dia.data.day <= 7:
        fator *= 1.1
    if dia.evento == "festa_junina":
        fator *= 1.5
    if not (dia.aula_manha and dia.aula_tarde) and not dia.sabado_letivo:
        fator *= 0.8  # só um turno com aula
    alvo = max(VENDAS_MIN_DIA, min(VENDAS_MAX_DIA, round(rng.randint(85, 125) * fator)))

    pesos_base = {pid: _peso_produto(it, clima_dia) for pid, it in itens.items()}
    pesos_alunos = [a.propensao for a, _ in presentes]
    brutas = []
    while len(brutas) < alvo:
        aluno, janelas = rng.choices(presentes, weights=pesos_alunos)[0]
        permitidos = {pid: w for pid, w in pesos_base.items()
                      if not (itens[pid].produto.tags & aluno.tags_proibidas)
                      and aluno.serie >= itens[pid].produto.serie_min}
        if not permitidos:
            continue
        max_itens = 2 if aluno.turma.segmento == "EF1" else 3
        n_itens = rng.choices([1, 2, 3][:max_itens], weights=[60, 30, 10][:max_itens])[0]
        n_itens = min(n_itens, len(permitidos), alvo - len(brutas))
        momento = _horario(dia.data, rng.choices(janelas, weights=[j[2] for j in janelas])[0], rng)
        forma = escolha_ponderada(rng, aluno.pesos_pagamento)
        for _ in range(n_itens):
            pid = escolha_ponderada(rng, permitidos)
            del permitidos[pid]
            qtd = rng.choices([1, 2, 3], weights=[75, 20, 5])[0] if pid in ITENS_MULTIPLOS else 1
            preco = itens[pid].preco
            brutas.append((momento, aluno.id, pid, qtd, preco, round(qtd * preco, 2), forma))
            momento += timedelta(seconds=rng.randint(2, 15))

    brutas.sort(key=lambda v: v[0])
    return [Venda(i, *v) for i, v in enumerate(brutas, start=primeiro_id)]


def gravar_lote(lote: list[Venda], caminho: Path, gabarito, taxa, rng):
    """Grava o arquivo do lote (vendas desta execução), já com as falhas propositais."""
    rotulo = caminho.stem
    # Alguns lotes são digitados por outro operador, que escreve a data como texto
    data_como_texto = taxa > 0 and rng.random() < 0.15
    if data_como_texto:
        gabarito.registrar(FONTE, ARQUIVO_HISTORICO, f"ids {lote[0].id}-{lote[-1].id}", "data_hora",
                           "formato_data_divergente", "datetime", "texto dd/mm/aaaa hh:mm",
                           f"Lote {rotulo} inteiro com datas digitadas como texto")
    linhas = []
    for v in lote:
        dh = v.data_hora.strftime("%d/%m/%Y %H:%M") if data_como_texto else v.data_hora
        linhas.append([v.id, dh, f"ALU{v.id_aluno:05d}", f"P{v.id_produto:03d}", v.quantidade,
                       v.valor_unitario, v.valor_total, v.forma_pagamento])

    extras = []
    for i in range(len(linhas)):
        if taxa > 0 and rng.random() < taxa:
            extras += _aplicar_falha(linhas, i, ARQUIVO_HISTORICO, gabarito, rng)
    for pos, linha in sorted(extras, key=lambda e: -e[0]):
        linhas.insert(pos, linha)
    salvar_excel(caminho, COLUNAS, linhas, aba="vendas")


def _aplicar_falha(linhas, i, arquivo, gabarito, rng):
    """Altera linhas[i] in-place; devolve linhas extras [(posição, linha)] a inserir."""
    linha = linhas[i]
    id_v = linha[0]
    tipo = rng.choices(
        ["forma_pagamento_nula", "forma_pagamento_digitacao", "valor_total_divergente",
         "registro_duplicado", "id_venda_repetido", "formato_data_divergente",
         "preco_negativo", "quantidade_invalida", "valor_unitario_sem_virgula",
         "produto_inexistente", "id_aluno_vazio"],
        weights=[14, 8, 12, 10, 5, 8, 8, 8, 6, 5, 6])[0]
    def reg(campo, tipo_, antes=None, depois=None, obs=""):
        gabarito.registrar(FONTE, arquivo, id_v, campo, tipo_, antes, depois, obs)

    if tipo == "forma_pagamento_nula":
        reg("forma_pagamento", "valor_nulo", linha[7], None)
        linha[7] = None
    elif tipo == "forma_pagamento_digitacao":
        variacoes = {"Dinheiro": ["dinheiro", "Dinhero", "DINHEIRO"], "Pix": ["pix", "PIX", "Pix "],
                     "Cartão de débito": ["Cartao debito", "débito", "Debito"],
                     "Cartão de crédito": ["Cartao credito", "crédito", "Credito"],
                     "Fiado": ["fiado", "Fiado ", "Anotado"]}
        novo = rng.choice(variacoes[linha[7]])
        reg("forma_pagamento", "categoria_digitada_errada", linha[7], novo)
        linha[7] = novo
    elif tipo == "valor_total_divergente":
        novo = round(linha[6] + rng.choice([-1, 1]) * rng.choice([0.5, 1, 2, 5, 10]), 2)
        if novo <= 0 or novo == linha[6]:
            novo = round(linha[6] * 10, 2)
        reg("valor_total", "valor_total_divergente_calculo", linha[6], novo)
        linha[6] = novo
    elif tipo == "registro_duplicado":
        reg("id_venda", "registro_duplicado", obs="Linha lançada duas vezes")
        return [(i + 1, list(linha))]
    elif tipo == "id_venda_repetido" and i > 0:
        novo = linhas[i - 1][0]
        reg("id_venda", "id_venda_duplicado", id_v, novo,
            "Venda distinta lançada com o id da venda anterior")
        linha[0] = novo
    elif tipo == "formato_data_divergente":
        dh = linha[1]
        if isinstance(dh, datetime):
            novo = dh.strftime("%Y-%m-%d %H:%M:%S")
        else:
            novo = datetime.strptime(dh, "%d/%m/%Y %H:%M").strftime("%Y-%m-%d %H:%M")
        reg("data_hora", "formato_data_divergente", str(dh), novo)
        linha[1] = novo
    elif tipo == "preco_negativo":
        reg("valor_unitario", "valor_negativo", linha[5], -linha[5])
        linha[5] = -linha[5]
        linha[6] = -linha[6]
    elif tipo == "quantidade_invalida":
        novo = rng.choice([0, -linha[4], linha[4] * 100, linha[4] * 10 + linha[4]])
        reg("quantidade", "quantidade_invalida", linha[4], novo)
        linha[4] = novo
    elif tipo == "valor_unitario_sem_virgula":
        novo = round(linha[5] * 100, 2)
        reg("valor_unitario", "valor_absurdo", linha[5], novo, "Separador decimal esquecido")
        linha[5] = novo
    elif tipo == "produto_inexistente":
        novo = rng.choice(["P999", "P000", "P" + linha[3][1:][::-1], "P099"])
        if novo == linha[3]:
            novo = "P999"
        reg("id_produto", "produto_ausente_cardapio", linha[3], novo)
        linha[3] = novo
    elif tipo == "id_aluno_vazio":
        reg("id_aluno", "valor_nulo", linha[2], None)
        linha[2] = None
    return []
