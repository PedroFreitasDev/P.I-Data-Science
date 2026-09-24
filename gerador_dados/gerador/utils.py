"""Funções auxiliares: gravação de arquivos, datas e sorteios."""

import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter


def intervalo_datas(inicio: date, fim: date):
    d = inicio
    while d <= fim:
        yield d
        d += timedelta(days=1)


def arredondar_preco(valor: float, passo: float = 0.50) -> float:
    """Arredonda para cima no múltiplo de `passo` (como a cantina faz nos reajustes)."""
    return round(math.ceil(round(valor / passo, 6)) * passo, 2)


def sortear_indices(rng, total: int, taxa: float, minimo: int = 1) -> set[int]:
    """Escolhe quais registros receberão falhas.

    Garante pelo menos `minimo` falhas em fontes pequenas (ex.: cardápio),
    a menos que a taxa seja zero.
    """
    if taxa <= 0 or total == 0:
        return set()
    qtd = min(total, max(minimo, round(total * taxa)))
    return set(rng.sample(range(total), qtd))


def escolha_ponderada(rng, opcoes: dict):
    return rng.choices(list(opcoes), weights=list(opcoes.values()), k=1)[0]


def salvar_excel(caminho: Path, colunas: list[str], linhas: list[list], aba: str = "dados"):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = aba
    ws.append(colunas)
    for cel in ws[1]:
        cel.font = Font(bold=True)
    for linha in linhas:
        ws.append(linha)
    for i, col in enumerate(colunas, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(14, len(col) + 4)
        for cel in ws.iter_rows(min_row=2, min_col=i, max_col=i):
            v = cel[0].value
            if isinstance(v, datetime):
                cel[0].number_format = "dd/mm/yyyy hh:mm:ss"
            elif isinstance(v, date):
                cel[0].number_format = "dd/mm/yyyy"
    wb.save(caminho)


def salvar_json(caminho: Path, conteudo):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(conteudo, f, ensure_ascii=False, indent=2, default=str)
