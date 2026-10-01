"""Leitura dos históricos já gravados para saber até onde o gerador chegou.

Não existe arquivo de estado: o progresso é reconstruído a partir das próprias
planilhas de histórico. Assim, qualquer máquina que tenha os dados (por exemplo,
um clone do repositório) continua a sequência de onde ela parou.
"""

from datetime import date, datetime
from pathlib import Path

from .utils import ler_excel

FORMATOS_DATA = ["%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                 "%d/%m/%Y", "%d-%m-%y", "%Y/%m/%d", "%Y-%m-%d"]


def interpretar_data(valor) -> date | None:
    """Converte as várias formas de data encontradas nas planilhas (inclusive as com falha)."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        for fmt in FORMATOS_DATA:
            try:
                return datetime.strptime(valor.strip(), fmt).date()
            except ValueError:
                continue
    return None


def maior_id_por_dia(caminho: Path) -> dict[date, int]:
    """{data: maior id da planilha naquele dia}. A 1ª coluna é o id e a 2ª a data."""
    if not caminho.exists():
        return {}
    _, linhas = ler_excel(caminho)
    maiores = {}
    for linha in linhas:
        d = interpretar_data(linha[1])
        if d is not None and isinstance(linha[0], int):
            maiores[d] = max(maiores.get(d, 0), linha[0])
    return maiores


def vendas_registradas(maiores: dict[date, int]) -> dict[date, tuple[int, int]]:
    """{data: (primeiro id do dia, quantidade de vendas já registradas no dia)}.

    Os ids são sequenciais entre os dias, e cada execução grava um prefixo
    cronológico das vendas do dia. Por isso a diferença entre o maior id do dia
    e o maior id dos dias anteriores é o número de vendas já registradas.
    """
    resultado = {}
    anterior = 0
    for d in sorted(maiores):
        resultado[d] = (anterior + 1, maiores[d] - anterior)
        anterior = maiores[d]
    return resultado
