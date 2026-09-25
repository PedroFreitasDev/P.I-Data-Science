"""1.3 Cardápio de Produtos (Excel).

Existem duas versões do cardápio no ano: a do 1º semestre e a do 2º semestre,
reajustada pela inflação acumulada da categoria (apenas meses já publicados).
Na troca, dois produtos saem, dois entram e alguns itens "esquecem" de ser
reajustados (preço desatualizado em relação à inflação).
"""

from dataclasses import dataclass
from datetime import date, timedelta

from .config import (DEFASAGEM_INFLACAO_MESES, DESCONTINUADOS_2_SEMESTRE,
                     DIAS_ESTOQUE_REMANESCENTE, NOVOS_2_SEMESTRE, PRODUTOS,
                     PRODUTOS_1_SEMESTRE, ProdutoBase)
from .inflacao import acumulado
from .utils import arredondar_preco, rng_para, salvar_excel, sortear_indices

FONTE = "cardapio"
COLUNAS = ["id_produto", "nome_produto", "categoria", "preco_venda", "custo_unitario"]


@dataclass
class ItemCardapio:
    produto: ProdutoBase
    preco: float
    custo: float


@dataclass
class Cardapio:
    vigencia: date
    itens: dict[int, ItemCardapio]
    nao_reajustados: set[int]


class Cardapios:
    def __init__(self, versoes: list[Cardapio]):
        self.versoes = sorted(versoes, key=lambda c: c.vigencia)

    def disponiveis(self, d: date) -> dict[int, ItemCardapio]:
        """Produtos que de fato podiam ser vendidos no dia `d`."""
        atual, anterior = None, None
        for v in self.versoes:
            if v.vigencia <= d:
                anterior, atual = atual, v
        if atual is None:
            return {}
        itens = dict(atual.itens)
        # estoque remanescente de produtos descontinuados ainda é vendido por alguns dias
        if anterior and d < atual.vigencia + timedelta(days=DIAS_ESTOQUE_REMANESCENTE):
            for pid, item in anterior.itens.items():
                itens.setdefault(pid, item)
        return itens

    def todos_itens(self) -> dict[int, ItemCardapio]:
        itens = {}
        for v in self.versoes:
            itens.update(v.itens)
        return itens


def gerar_cardapios(vigencia_1: date, vigencia_2: date, inflacao: dict, rng) -> Cardapios:
    v1 = {pid: ItemCardapio(PRODUTOS[pid], PRODUTOS[pid].preco, PRODUTOS[pid].custo)
          for pid in PRODUTOS_1_SEMESTRE}

    # Reajuste usa só os meses cuja inflação já havia sido publicada na data da troca
    meses = range(1, max(2, vigencia_2.month - DEFASAGEM_INFLACAO_MESES + 1))
    mantidos = [pid for pid in PRODUTOS_1_SEMESTRE if pid not in DESCONTINUADOS_2_SEMESTRE]
    nao_reajustados = set(rng.sample(mantidos, 3))
    v2 = {}
    for pid in mantidos + sorted(NOVOS_2_SEMESTRE):
        p = PRODUTOS[pid]
        fator = acumulado(inflacao, p.categoria, meses)
        custo = round(p.custo * fator, 2)
        if pid in nao_reajustados or pid in NOVOS_2_SEMESTRE:
            preco = p.preco
        else:
            preco = arredondar_preco(p.preco * fator)
        v2[pid] = ItemCardapio(p, preco, custo)

    return Cardapios([Cardapio(vigencia_1, v1, set()), Cardapio(vigencia_2, v2, nao_reajustados)])


def publicar_cardapios(cardapios: Cardapios, pasta, gabarito, taxa, seed, hoje: date):
    """Publica as versões do cardápio que já entraram em vigor até `hoje`."""
    for versao in cardapios.versoes:
        if versao.vigencia > hoje:
            continue
        rng = rng_para(seed, "falha_cardapio", versao.vigencia)
        arquivo = f"cardapio_vigencia_{versao.vigencia.isoformat()}.xlsx"
        linhas = [[pid, it.produto.nome, it.produto.categoria, it.preco, it.custo]
                  for pid, it in sorted(versao.itens.items())]

        for pid in sorted(versao.nao_reajustados):
            gabarito.registrar(FONTE, arquivo, pid, "preco_venda",
                               "preco_desatualizado_inflacao", observacao=
                               "Preço mantido do 1º semestre apesar da inflação acumulada")

        # "Custo_unitario ausente" é a falha mais comum desta planilha
        for i in sortear_indices(rng, len(linhas), taxa * 2, minimo=2):
            linha = linhas[i]
            gabarito.registrar(FONTE, arquivo, linha[0], "custo_unitario", "valor_nulo",
                               linha[4], None)
            linha[4] = None

        for i in sortear_indices(rng, len(linhas), taxa, minimo=2):
            linha = linhas[i]
            tipo = rng.choice(["preco_sem_virgula", "custo_negativo", "nome_digitacao",
                               "categoria_digitacao"])
            if tipo == "preco_sem_virgula":
                novo = round(linha[3] * 100, 2)
                gabarito.registrar(FONTE, arquivo, linha[0], "preco_venda", "valor_absurdo",
                                   linha[3], novo, "Separador decimal esquecido")
                linha[3] = novo
            elif tipo == "custo_negativo" and linha[4] is not None:
                gabarito.registrar(FONTE, arquivo, linha[0], "custo_unitario", "valor_negativo",
                                   linha[4], -linha[4])
                linha[4] = -linha[4]
            elif tipo == "nome_digitacao":
                novo = rng.choice([linha[1].upper(), "  " + linha[1], linha[1] + "  "])
                gabarito.registrar(FONTE, arquivo, linha[0], "nome_produto",
                                   "texto_fora_do_padrao", linha[1], novo)
                linha[1] = novo
            else:
                novo = rng.choice([linha[2].lower(), linha[2][:-1], linha[2].upper()])
                gabarito.registrar(FONTE, arquivo, linha[0], "categoria",
                                   "categoria_digitada_errada", linha[2], novo)
                linha[2] = novo

        salvar_excel(pasta / arquivo, COLUNAS, linhas, aba="cardapio")
