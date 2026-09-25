"""1.6 Clima e Temperatura do Dia (JSON).

O clima real é gerado com sazonalidade (verão quente e chuvoso, inverno frio e
seco) e persistência entre dias consecutivos. A versão publicada simula a
resposta de uma API com falhas de requisição, granularidade horária em alguns
dias e um bloco de dias com fuso horário divergente.
"""

from datetime import date, datetime, timedelta

from .config import CIDADE, PROB_CHUVA_MES, TEMP_MEDIA_MES
from .utils import intervalo_datas, rng_para, salvar_json

FONTE = "clima"


def gerar_clima(ano: int, rng) -> dict[date, dict]:
    clima = {}
    anomalia = 0.0
    choveu_ontem = False
    for d in intervalo_datas(date(ano, 1, 1), date(ano, 12, 31)):
        anomalia = 0.7 * anomalia + rng.gauss(0, 1.5)
        prob_chuva = PROB_CHUVA_MES[d.month] + (0.2 if choveu_ontem else 0.0)
        chove = rng.random() < prob_chuva
        media = TEMP_MEDIA_MES[d.month] + anomalia - (1.5 if chove else 0.0)
        if chove:
            if rng.random() < 0.15:
                condicao, precip = "tempestade", rng.uniform(25, 70)
            else:
                condicao, precip = "chuva", rng.uniform(1, 25)
            maxima = media + rng.uniform(2, 4)
        else:
            condicao = rng.choices(["ensolarado", "parcialmente_nublado", "nublado"],
                                   weights=[5, 3, 2])[0]
            precip = rng.uniform(0, 0.8) if condicao == "nublado" and rng.random() < 0.3 else 0.0
            maxima = media + rng.uniform(4, 8)
        clima[d] = {
            "temperatura_media": round(media, 1),
            "temperatura_max": round(maxima, 1),
            "condicao": condicao,
            "precipitacao_mm": round(precip, 1),
        }
        choveu_ontem = chove
    return clima


def _registros_horarios(d: date, c: dict, rng) -> list[dict]:
    """Mesmo dia devolvido em 24 leituras horárias (granularidade diferente)."""
    regs = []
    amplitude = (c["temperatura_max"] - c["temperatura_media"])
    for h in range(24):
        # curva simples: mínimo às 5h, máximo às 15h
        fase = -1 + 2 * max(0.0, 1 - abs(h - 15) / 10)
        temp = c["temperatura_media"] + amplitude * fase + rng.uniform(-0.3, 0.3)
        regs.append({
            "data": datetime(d.year, d.month, d.day, h).isoformat(),
            "temperatura_media": round(temp, 1),
            "temperatura_max": round(temp + rng.uniform(0, 0.6), 1),
            "condicao": c["condicao"],
            "precipitacao_mm": round(c["precipitacao_mm"] / 24, 2),
        })
    return regs


def publicar_clima(clima: dict, pasta, gabarito, taxa, seed, ano, ate: date):
    """Publica as leituras de 01/01 até `ate` (a API não tem dados do futuro)."""
    arquivo = f"clima_{ano}.json"
    datas = sorted(d for d in clima if d <= ate)

    # Bloco de 5 dias em que a API devolveu datas convertidas de UTC para -03:00
    fuso = set()
    if taxa > 0:
        ini = rng_para(seed, "clima_fuso", ano).randrange(30, 350)
        fuso = {date(ano, 1, 1) + timedelta(days=ini + i) for i in range(5)}

    registros = []
    for d in datas:
        c = dict(clima[d])
        reg = {"data": d.isoformat(), **c}
        if d in fuso:
            reg["data"] = (datetime(d.year, d.month, d.day) - timedelta(hours=3)).isoformat() + "-03:00"
            gabarito.registrar(FONTE, arquivo, d.isoformat(), "data", "fuso_horario_divergente",
                               d.isoformat(), reg["data"],
                               "Meia-noite UTC convertida para -03:00 cai no dia anterior")
            registros.append(reg)
            continue
        rng = rng_para(seed, "falha_clima", d)
        if rng.random() >= taxa:
            registros.append(reg)
            continue

        tipo = rng.choices(
            ["requisicao_sem_registro", "requisicao_valores_nulos", "granularidade_horaria",
             "temperatura_absurda", "precipitacao_negativa"],
            weights=[3, 3, 2, 2, 1])[0]
        if tipo == "requisicao_sem_registro":
            gabarito.registrar(FONTE, arquivo, d.isoformat(), "*", "falha_requisicao_dado_ausente",
                               observacao="Dia ausente da resposta da API")
            continue
        if tipo == "requisicao_valores_nulos":
            campos = rng.sample(["temperatura_media", "temperatura_max", "condicao",
                                 "precipitacao_mm"], rng.randint(1, 4))
            for campo in campos:
                gabarito.registrar(FONTE, arquivo, d.isoformat(), campo,
                                   "falha_requisicao_valor_nulo", reg[campo], None)
                reg[campo] = None
            registros.append(reg)
        elif tipo == "granularidade_horaria":
            gabarito.registrar(FONTE, arquivo, d.isoformat(), "data", "granularidade_diferente",
                               "1 registro diário", "24 registros horários")
            registros.extend(_registros_horarios(d, c, rng))
        elif tipo == "temperatura_absurda":
            campo = rng.choice(["temperatura_media", "temperatura_max"])
            novo = rng.choice([round(reg[campo] * 10, 1), -reg[campo], 999.9])
            gabarito.registrar(FONTE, arquivo, d.isoformat(), campo, "valor_absurdo",
                               reg[campo], novo)
            reg[campo] = novo
            registros.append(reg)
        else:
            novo = -round(rng.uniform(1, 30), 1)
            gabarito.registrar(FONTE, arquivo, d.isoformat(), "precipitacao_mm", "valor_negativo",
                               reg["precipitacao_mm"], novo)
            reg["precipitacao_mm"] = novo
            registros.append(reg)

    salvar_json(pasta / arquivo, {
        "fonte": "API meteorológica (simulada)",
        "cidade": CIDADE,
        "unidade_temperatura": "celsius",
        "unidade_precipitacao": "mm",
        "registros": registros,
    })
