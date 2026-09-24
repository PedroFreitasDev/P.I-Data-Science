"""Gerador de dados fictícios da cantina escolar.

Gera as 8 fontes brutas descritas em DOCS/especificacao_dados_pipeline_cantina.pdf
na estrutura da camada bronze, com falhas propositais (erros humanos e de
integração) registradas em um gabarito.

Uso:
    python gerar_dados.py                   # ano 2025, semente 42, 3% de falhas
    python gerar_dados.py --ano 2026 --seed 7 --taxa-falhas 0.05
    python gerar_dados.py --sem-falhas      # dados limpos (útil para comparação)
"""

import argparse
import random
import shutil
from datetime import date
from pathlib import Path

from gerador import alunos, calendario, cardapio, clima, devedores, inflacao, perdas, vendas
from gerador.falhas import Gabarito


def main():
    parser = argparse.ArgumentParser(description="Gera dados fictícios da cantina escolar.")
    parser.add_argument("--ano", type=int, default=2025, help="Ano letivo (padrão: 2025)")
    parser.add_argument("--seed", type=int, default=42, help="Semente aleatória (padrão: 42)")
    parser.add_argument("--taxa-falhas", type=float, default=0.03,
                        help="Proporção aproximada de registros com falha (padrão: 0.03)")
    parser.add_argument("--sem-falhas", action="store_true", help="Gera os dados sem falhas")
    parser.add_argument("--min-alunos", type=int, default=20, help="Mínimo de alunos por turma")
    parser.add_argument("--max-alunos", type=int, default=28, help="Máximo de alunos por turma")
    parser.add_argument("--saida", type=Path, default=Path(__file__).parent / "saida",
                        help="Pasta de saída (padrão: gerador_dados/saida)")
    args = parser.parse_args()

    taxa = 0.0 if args.sem_falhas else args.taxa_falhas
    rng = random.Random(args.seed)
    rng_falhas = random.Random(args.seed + 1)  # falhas não alteram os dados "reais"
    bronze = args.saida / "bronze"
    if bronze.exists():
        shutil.rmtree(bronze)
    gabarito = Gabarito()

    # ---------------- Dados "reais" (coerentes entre si) ----------------
    dias = calendario.gerar_calendario(args.ano, rng)
    clima_real = clima.gerar_clima(args.ano, rng)
    inflacao_real = inflacao.gerar_inflacao(args.ano, rng)

    vigencia_1 = next(d.data for d in dias if d.tipo_dia == "planejamento")
    vigencia_2 = next(d.data for d in dias
                      if d.data.month >= 7 and d.tem_aula and d.data > date(args.ano, 7, 5))
    data_referencia = max(d.data for d in dias if d.tem_aula)

    cardapios = cardapio.gerar_cardapios(vigencia_1, vigencia_2, inflacao_real, rng)
    turmas = alunos.gerar_turmas(args.ano, rng, args.min_alunos, args.max_alunos)
    lista_vendas = vendas.simular_vendas(dias, clima_real, turmas, cardapios, rng)
    lista_dividas = devedores.gerar_devedores(lista_vendas, turmas, data_referencia, rng)
    lista_perdas = perdas.gerar_perdas(dias, lista_vendas, cardapios, rng)

    # ---------------- Publicação na camada bronze (com falhas) ----------------
    ids_alunos = {a.id for t in turmas for a in t.alunos}
    vendas.publicar_vendas(lista_vendas, bronze / "vendas", gabarito, taxa, rng_falhas)
    devedores.publicar_devedores(lista_dividas, ids_alunos, bronze / "devedores", gabarito,
                                 taxa, rng_falhas, data_referencia)
    cardapio.publicar_cardapios(cardapios, bronze / "cardapio", gabarito, taxa, rng_falhas)
    perdas.publicar_perdas(lista_perdas, bronze / "perdas", gabarito, taxa, rng_falhas)
    calendario.publicar_calendario(dias, bronze / "calendario_escolar", gabarito, taxa,
                                   rng_falhas, args.ano)
    clima.publicar_clima(clima_real, bronze / "clima", gabarito, taxa, rng_falhas, args.ano)
    alunos.publicar_turmas(turmas, bronze / "turmas_alunos", gabarito, taxa, rng_falhas, args.ano)
    inflacao.publicar_inflacao(inflacao_real, bronze / "inflacao", gabarito, taxa, rng_falhas,
                               args.ano, data_referencia.month)
    gabarito.salvar(args.saida / "gabarito_falhas.csv")

    # ---------------- Resumo ----------------
    print(f"Dados gerados em: {args.saida.resolve()}")
    print(f"  Alunos: {len(ids_alunos)} em {len(turmas)} turmas")
    print(f"  Dias com aula: {sum(d.tem_aula for d in dias)}")
    print(f"  Vendas: {len(lista_vendas)} | Dívidas: {len(lista_dividas)} | Perdas: {len(lista_perdas)}")
    print(f"  Falhas inseridas: {len(gabarito.linhas)} (detalhes em gabarito_falhas.csv)")
    for (fonte, tipo), qtd in sorted(gabarito.resumo().items()):
        print(f"    {fonte:<20} {tipo:<35} {qtd}")


if __name__ == "__main__":
    main()
