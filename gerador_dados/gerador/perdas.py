"""1.4 Perdas / Desperdício (Excel, uma planilha por mês).

Para produtos perecíveis, a cantina produz com base na média de vendas dos
últimos dias; o que sobra no fim do expediente vira perda. Assim, dias
atípicos (chuva, calor, frio) geram mais desperdício. Também há perdas
esporádicas por avaria, vencimento e erro de preparo.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from .utils import salvar_excel, sortear_indices

FONTE = "perdas"
COLUNAS = ["id_perda", "data", "id_produto", "quantidade", "motivo", "valor_prejuizo"]


@dataclass
class Perda:
    id: int
    data: date
    id_produto: int
    quantidade: int
    motivo: str
    valor_prejuizo: float


def gerar_perdas(dias, vendas, cardapios, rng) -> list[Perda]:
    vendido = defaultdict(int)  # (data, produto) -> unidades
    for v in vendas:
        vendido[(v.data_hora.date(), v.id_produto)] += v.quantidade

    historico = defaultdict(list)  # produto -> vendas dos últimos dias letivos
    brutas = []
    for dia in dias:
        if not dia.tem_aula:
            continue
        d = dia.data
        itens = cardapios.disponiveis(d)
        for pid, item in itens.items():
            qtd_vendida = vendido[(d, pid)]
            hist = historico[pid]
            if item.produto.perecivel and hist:
                media = sum(hist) / len(hist)
                produzido = round(media * rng.uniform(1.0, 1.25))
                sobra = produzido - qtd_vendida
                if sobra > 0:
                    motivo = "Sobra do dia" if rng.random() < 0.85 else "Vencimento"
                    brutas.append((d, pid, sobra, motivo, round(sobra * item.custo, 2)))
            hist.append(qtd_vendida)
            if len(hist) > 5:
                hist.pop(0)

            if rng.random() < 0.015:
                motivo = rng.choices(["Queda/avaria", "Erro de preparo", "Contaminação/qualidade",
                                      "Vencimento"], weights=[5, 3, 1, 2])[0]
                qtd = rng.randint(1, 4)
                brutas.append((d, pid, qtd, motivo, round(qtd * item.custo, 2)))

    return [Perda(i, *p) for i, p in enumerate(brutas, start=1)]


def publicar_perdas(perdas: list[Perda], pasta, gabarito, taxa, rng):
    meses = defaultdict(list)
    for p in perdas:
        meses[(p.data.year, p.data.month)].append(p)

    for (a, m), lista in sorted(meses.items()):
        arquivo = f"perdas_{a}-{m:02d}.xlsx"
        linhas = [[p.id, p.data, p.id_produto, p.quantidade, p.motivo, p.valor_prejuizo]
                  for p in lista]
        for i in sortear_indices(rng, len(linhas), taxa * 1.5, minimo=1):
            linha = linhas[i]
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
        salvar_excel(pasta / arquivo, COLUNAS, linhas, aba="perdas")
