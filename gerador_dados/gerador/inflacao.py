"""1.8 Índice de Preços / Inflação (JSON, simulando uma API mensal).

`indice_inflacao` é a variação mensal em % por categoria de produto. O mesmo
índice real é usado para reajustar o cardápio do 2º semestre, então preços e
inflação ficam coerentes entre si.
"""

from datetime import date

from .config import (CATEGORIAS, DEFASAGEM_INFLACAO_MESES, INFLACAO_MEDIA_CATEGORIA,
                     NOME_CATEGORIA_API)
from .utils import rng_para, salvar_json

FONTE = "inflacao"


def gerar_inflacao(ano: int, rng) -> dict[tuple[int, str], float]:
    """Retorna {(mes, categoria): variação %}."""
    inflacao = {}
    choque = {m: rng.gauss(0, 0.15) for m in range(1, 13)}  # choque comum a todas as categorias
    for mes in range(1, 13):
        for cat in CATEGORIAS:
            v = INFLACAO_MEDIA_CATEGORIA[cat] + choque[mes] + rng.gauss(0, 0.18)
            inflacao[(mes, cat)] = round(v, 2)
    return inflacao


def acumulado(inflacao: dict, categoria: str, meses: range) -> float:
    fator = 1.0
    for m in meses:
        fator *= 1 + inflacao[(m, categoria)] / 100
    return fator


def publicar_inflacao(inflacao: dict, pasta, gabarito, taxa, seed, ano, hoje: date):
    """Publica os meses já divulgados até `hoje` (com a defasagem de publicação)."""
    arquivo = f"inflacao_{ano}.json"
    mes_final = hoje.month
    ultimo_publicado = mes_final - DEFASAGEM_INFLACAO_MESES
    for mes in range(ultimo_publicado + 1, mes_final + 1):
        gabarito.registrar(FONTE, arquivo, f"{ano}-{mes:02d}", "*", "defasagem_publicacao",
                           observacao="Índice do mês ainda não publicado pela fonte")
    for cat, nome_api in NOME_CATEGORIA_API.items():
        if cat != nome_api:
            gabarito.registrar(FONTE, arquivo, "*", "categoria_produto",
                               "categoria_incompativel_cardapio", cat, nome_api,
                               "Nomenclatura da fonte difere da do cardápio")

    registros = [
        {"mes_referencia": f"{ano}-{mes:02d}",
         "indice_inflacao": inflacao[(mes, cat)],
         "categoria_produto": NOME_CATEGORIA_API[cat]}
        for mes in range(1, ultimo_publicado + 1)
        for cat in CATEGORIAS
    ]

    for r in registros:
        chave = f"{r['mes_referencia']}|{r['categoria_produto']}"
        rng = rng_para(seed, "falha_inflacao", chave)
        if rng.random() >= taxa:
            continue
        tipo = rng.choice(["indice_nulo", "indice_sem_virgula", "categoria_digitada_errada",
                           "formato_mes_divergente"])
        if tipo == "indice_nulo":
            gabarito.registrar(FONTE, arquivo, chave, "indice_inflacao", "valor_nulo",
                               r["indice_inflacao"], None)
            r["indice_inflacao"] = None
        elif tipo == "indice_sem_virgula":
            novo = round(r["indice_inflacao"] * 100, 2)
            gabarito.registrar(FONTE, arquivo, chave, "indice_inflacao", "valor_absurdo",
                               r["indice_inflacao"], novo, "Separador decimal esquecido")
            r["indice_inflacao"] = novo
        elif tipo == "categoria_digitada_errada":
            novo = rng.choice([r["categoria_produto"].lower(), r["categoria_produto"].upper(),
                               r["categoria_produto"][:-1], r["categoria_produto"] + " "])
            gabarito.registrar(FONTE, arquivo, chave, "categoria_produto",
                               "categoria_digitada_errada", r["categoria_produto"], novo)
            r["categoria_produto"] = novo
        else:
            a, m = r["mes_referencia"].split("-")
            novo = f"{m}/{a}"
            gabarito.registrar(FONTE, arquivo, chave, "mes_referencia", "formato_data_divergente",
                               r["mes_referencia"], novo)
            r["mes_referencia"] = novo

    salvar_json(pasta / arquivo, {
        "fonte": "API de índices de preços (simulada)",
        "descricao": "Variação percentual mensal por categoria de produto",
        "consultado_em": hoje.isoformat(),
        "dados": registros,
    })
