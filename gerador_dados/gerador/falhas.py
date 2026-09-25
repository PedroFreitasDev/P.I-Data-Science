"""Registro das falhas inseridas propositalmente (gabarito).

Cada falha injetada nos arquivos da camada bronze é anotada aqui, permitindo
conferir depois se a camada silver do pipeline detectou/tratou cada caso.

Fontes acumulativas (vendas, perdas) têm suas falhas acrescentadas ao gabarito a
cada execução. Fontes republicadas por inteiro (devedores, cardápio, clima...)
têm suas linhas do gabarito substituídas a cada execução.
"""

import csv
from collections import Counter
from pathlib import Path

FONTES_ACUMULATIVAS = {"vendas", "perdas"}


class Gabarito:
    CAMPOS = ["fonte", "arquivo", "registro", "campo", "tipo_falha",
              "valor_correto", "valor_registrado", "observacao"]

    def __init__(self):
        self.linhas: list[dict] = []

    def registrar(self, fonte, arquivo, registro, campo, tipo_falha,
                  valor_correto=None, valor_registrado=None, observacao=""):
        self.linhas.append({
            "fonte": fonte,
            "arquivo": arquivo,
            "registro": registro,
            "campo": campo,
            "tipo_falha": tipo_falha,
            "valor_correto": "" if valor_correto is None else valor_correto,
            "valor_registrado": "" if valor_registrado is None else valor_registrado,
            "observacao": observacao,
        })

    def salvar(self, caminho: Path):
        """Mantém o histórico das fontes acumulativas e substitui o das demais."""
        caminho.parent.mkdir(parents=True, exist_ok=True)
        anteriores = []
        if caminho.exists():
            with open(caminho, newline="", encoding="utf-8") as f:
                anteriores = [l for l in csv.DictReader(f, delimiter=";")
                              if l["fonte"] in FONTES_ACUMULATIVAS]
        with open(caminho, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=self.CAMPOS, delimiter=";")
            w.writeheader()
            w.writerows(anteriores)
            w.writerows(self.linhas)

    def resumo(self) -> Counter:
        return Counter((l["fonte"], l["tipo_falha"]) for l in self.linhas)
