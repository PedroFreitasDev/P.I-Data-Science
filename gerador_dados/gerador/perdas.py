"""1.4 Perdas / Desperdício (Excel).

Registradas uma vez por dia, no fechamento do expediente. Para produtos
perecíveis, a cantina produz com base na média de vendas dos últimos dias; o
que sobra no fim do dia vira perda. Assim, dias atípicos (chuva, calor, frio)
geram mais desperdício. Também há perdas esporádicas por avaria, vencimento e
erro de preparo.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .utils import salvar_excel

FONTE = "perdas"
COLUNAS = ["id_perda", "data", "id_produto", "quantidade", "motivo", "valor_prejuizo"]
ARQUIVO_HISTORICO = "historico_perdas.xlsx"
DIAS_MEDIA = 5


@dataclass
class Perda:
    id: int
    data: date
    id_produto: int
    quantidade: int
    motivo: str
    valor_prejuizo: float


def gerar_perdas_dia(d: date, vendas_dia, itens, historico: dict, primeiro_id: int, rng) -> list[Perda]:
    """Perdas do dia `d`. Atualiza `historico` ({id_produto: [vendidos nos últimos dias]})."""
    vendido = defaultdict(int)
    for v in vendas_dia:
        vendido[v.id_produto] += v.quantidade

    brutas = []
    for pid, item in sorted(itens.items()):
        qtd_vendida = vendido[pid]
        hist = historico.setdefault(str(pid), [])
        if item.produto.perecivel:
            # sem histórico, a cantina produz perto do que acabou vendendo
            base = sum(hist) / len(hist) if hist else qtd_vendida
            produzido = round(base * rng.uniform(1.0, 1.3)) + rng.randint(0, 2)
            sobra = produzido - qtd_vendida
            if sobra > 0:
                motivo = "Sobra do dia" if rng.random() < 0.85 else "Vencimento"
                brutas.append((d, pid, sobra, motivo, round(sobra * item.custo, 2)))
        hist.append(qtd_vendida)
        del hist[:-DIAS_MEDIA]

        if rng.random() < 0.015:
            motivo = rng.choices(["Queda/avaria", "Erro de preparo", "Contaminação/qualidade",
                                  "Vencimento"], weights=[5, 3, 1, 2])[0]
            qtd = rng.randint(1, 4)
            brutas.append((d, pid, qtd, motivo, round(qtd * item.custo, 2)))

    return [Perda(i, *p) for i, p in enumerate(brutas, start=primeiro_id)]


def gravar_lote(lote: list[Perda], caminho: Path, gabarito, taxa, rng):
    """Grava a planilha de perdas do dia, já com as falhas propositais."""
    arquivo = ARQUIVO_HISTORICO
    linhas = [[p.id, p.data, p.id_produto, p.quantidade, p.motivo, p.valor_prejuizo]
              for p in lote]
    for linha in linhas:
        if not (taxa > 0 and rng.random() < taxa * 1.5):
            continue
        id_p = linha[0]
        tipo = rng.choices(["motivo_vazio", "produto_sem_correspondencia",
                            "quantidade_invalida", "valor_prejuizo_divergente",
                            "formato_data_divergente"], weights=[4, 2, 3, 2, 1])[0]
        if tipo == "motivo_vazio":
            gabarito.registrar(FONTE, arquivo, id_p, "motivo", "valor_nulo", linha[4], None)
            linha[4] = None
        elif tipo == "produto_sem_correspondencia":
            novo = rng.choice([99, 0, linha[2] + 100, linha[2] * 11 if linha[2] > 2 else 99])
            gabarito.registrar(FONTE, arquivo, id_p, "id_produto", "produto_ausente_cardapio",
                               linha[2], novo)
            linha[2] = novo
        elif tipo == "quantidade_invalida":
            novo = rng.choice([0, -linha[3]])
            gabarito.registrar(FONTE, arquivo, id_p, "quantidade", "quantidade_zerada_negativa",
                               linha[3], novo)
            linha[3] = novo
        elif tipo == "valor_prejuizo_divergente":
            novo = rng.choice([round(linha[5] * 10, 2), -linha[5], round(linha[5] + 5, 2)])
            gabarito.registrar(FONTE, arquivo, id_p, "valor_prejuizo",
                               "valor_divergente_calculo", linha[5], novo)
            linha[5] = novo
        else:
            novo = linha[1].strftime(rng.choice(["%d/%m/%Y", "%d-%m-%y", "%Y/%m/%d"]))
            gabarito.registrar(FONTE, arquivo, id_p, "data", "formato_data_divergente",
                               linha[1].isoformat(), novo)
            linha[1] = novo
    salvar_excel(caminho, COLUNAS, linhas, aba="perdas")
