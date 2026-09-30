"""Gerador diário de dados fictícios da cantina escolar.

Pensado para rodar 1 ou 2 vezes por dia (ex.: via cron em uma VM). A cada execução:

1. Vendas: gera apenas as vendas de HOJE (75 a 150 no dia) que já aconteceram até
   o horário atual e ainda não foram registradas. Elas são gravadas num arquivo
   de lote, que é acrescentado à planilha de histórico e depois apagado.
2. Perdas: no fechamento do expediente, gera as perdas do dia (mesmo esquema de
   lote -> histórico).
3. Devedores: recalcula a planilha a partir das vendas "Fiado" do histórico,
   com o status de hoje.
4. Republica as fontes de referência (calendário, turmas/alunos, cardápio,
   clima e inflação), limitadas ao que já existe na data de hoje.
5. Envia ao GitHub os arquivos de dados que mudaram.

Não há arquivo de estado: o progresso é lido dos próprios históricos.

Uso:
    python gerar_dados.py                        # execução normal (horário de Brasília)
    python gerar_dados.py --dia-completo         # registra o dia inteiro de uma vez
    python gerar_dados.py --sem-github           # não envia nada ao GitHub
    python gerar_dados.py --agora "2026-09-24 19:00"   # simula o horário (testes)
"""

import argparse
from datetime import datetime
from pathlib import Path

from gerador import alunos, calendario, cardapio, clima, devedores, inflacao, perdas, vendas
from gerador.github import enviar_dados
from gerador.historico import interpretar_data, maior_id_por_dia, vendas_registradas
from gerador.mundo import mundo
from gerador.utils import consolidar_lote, ler_excel, rng_para

try:
    from zoneinfo import ZoneInfo
    FUSO = ZoneInfo("America/Sao_Paulo")
except Exception:  # sem base de fusos no sistema: usa o horário local da máquina
    FUSO = None

RAIZ_GERADOR = Path(__file__).resolve().parent


def agora_local() -> datetime:
    return datetime.now(FUSO).replace(tzinfo=None) if FUSO else datetime.now()


def main():
    parser = argparse.ArgumentParser(description="Gera os dados fictícios do dia da cantina escolar.")
    parser.add_argument("--seed", type=int, default=42, help="Semente aleatória (padrão: 42)")
    parser.add_argument("--taxa-falhas", type=float, default=0.03,
                        help="Proporção aproximada de registros com falha (padrão: 0.03)")
    parser.add_argument("--sem-falhas", action="store_true", help="Gera os dados sem falhas")
    parser.add_argument("--min-alunos", type=int, default=20, help="Mínimo de alunos por turma")
    parser.add_argument("--max-alunos", type=int, default=28, help="Máximo de alunos por turma")
    parser.add_argument("--saida", type=Path, default=RAIZ_GERADOR.parent / "dados",
                        help="Pasta dos dados (padrão: dados/ na raiz do repositório)")
    parser.add_argument("--dia-completo", action="store_true",
                        help="Registra todas as vendas de hoje e fecha o dia, sem esperar o horário")
    parser.add_argument("--manter-lote", action="store_true",
                        help="Não apaga os arquivos de lote após consolidar no histórico")
    parser.add_argument("--sem-github", action="store_true",
                        help="Não envia os dados ao GitHub (ficam apenas no computador local)")
    parser.add_argument("--remoto", default="origin", help="Remoto git para envio (padrão: origin)")
    parser.add_argument("--branch", default=None,
                        help="Branch de destino no GitHub (padrão: a branch atual do repositório)")
    parser.add_argument("--agora", type=datetime.fromisoformat, default=None,
                        help='Data/hora simulada "AAAA-MM-DD HH:MM" (apenas para testes)')
    args = parser.parse_args()

    taxa = 0.0 if args.sem_falhas else args.taxa_falhas
    seed = args.seed
    agora = args.agora or agora_local()
    hoje = agora.date()
    bronze = args.saida / "bronze"
    lotes = RAIZ_GERADOR / "lotes"
    hist_vendas = bronze / "vendas" / vendas.ARQUIVO_HISTORICO
    hist_perdas = bronze / "perdas" / perdas.ARQUIVO_HISTORICO

    def mundo_de(ano):
        return mundo(seed, ano, args.min_alunos, args.max_alunos)

    m = mundo_de(hoje.year)
    dia = m.dia_por_data[hoje]

    # ---------------- Progresso lido do histórico de vendas ----------------
    registradas = vendas_registradas(maior_id_por_dia(hist_vendas))
    if registradas and max(registradas) > hoje:
        raise SystemExit(f"O histórico já tem vendas de {max(registradas)}; "
                         "não é possível gerar dados de uma data anterior.")
    if hoje in registradas:
        primeiro_id, ja_registradas = registradas[hoje]
    else:
        primeiro_id = max((p + n for p, n in registradas.values()), default=1)
        ja_registradas = 0

    # ---------------- Vendas de hoje ----------------
    vendas_dia = m.vendas_do_dia(hoje, primeiro_id)
    pendentes = [v for v in vendas_dia[ja_registradas:] if args.dia_completo or v.data_hora <= agora]
    if pendentes:
        lote = lotes / f"vendas_{agora:%Y-%m-%d_%H%M%S}.xlsx"
        vendas.gravar_lote(pendentes, lote, taxa, rng_para(seed, "falhas_vendas", hoje, pendentes[0].id))
        consolidar_lote(lote, hist_vendas, "vendas", args.manter_lote)
        registradas[hoje] = (primeiro_id, ja_registradas + len(pendentes))

    # ---------------- Perdas (fechamento do expediente) ----------------
    qtd_perdas = None
    _, linhas_perdas = ler_excel(hist_perdas) if hist_perdas.exists() else ([], [])
    dia_fechado = any(interpretar_data(l[1]) == hoje for l in linhas_perdas)
    expediente_encerrado = args.dia_completo or agora.time() >= vendas.fim_expediente(dia)
    if (dia.tem_aula and not dia_fechado and expediente_encerrado
            and ja_registradas + len(pendentes) == len(vendas_dia)):
        # A produção de perecíveis segue as vendas dos últimos dias letivos
        anteriores = [d.data for d in m.dias if d.tem_aula and d.data < hoje][-perdas.DIAS_MEDIA:]
        historico_vendido = {}
        for d in anteriores:
            vendidos = {}
            for v in m.vendas_do_dia(d):
                vendidos[v.id_produto] = vendidos.get(v.id_produto, 0) + v.quantidade
            for pid in m.cardapios.disponiveis(hoje):
                historico_vendido.setdefault(str(pid), []).append(vendidos.get(pid, 0))
        proximo_id_perda = max((l[0] for l in linhas_perdas if isinstance(l[0], int)), default=0) + 1
        lista_perdas = perdas.gerar_perdas_dia(hoje, vendas_dia, m.cardapios.disponiveis(hoje),
                                               historico_vendido, proximo_id_perda,
                                               rng_para(seed, "perdas", hoje))
        if lista_perdas:
            lote = lotes / f"perdas_{agora:%Y-%m-%d_%H%M%S}.xlsx"
            perdas.gravar_lote(lista_perdas, lote, taxa, rng_para(seed, "falhas_perdas", hoje))
            consolidar_lote(lote, hist_perdas, "perdas", args.manter_lote)
        qtd_perdas = len(lista_perdas)

    # ---------------- Devedores (a partir do fiado já registrado) ----------------
    fiado = []
    for d, (p, n) in sorted(registradas.items()):
        fiado += [v for v in mundo_de(d.year).vendas_do_dia(d, p)[:n] if v.forma_pagamento == "Fiado"]
    dividas = devedores.montar_dividas(fiado, seed, taxa)

    def pagador_de(id_aluno, data):
        # débitos de anos anteriores podem ser de alunos que não estão mais na base
        aluno = mundo_de(data.year).alunos_por_id.get(id_aluno)
        return aluno.pagador if aluno else "atrasa"

    devedores.publicar_devedores(dividas, pagador_de, set(m.alunos_por_id), bronze / "devedores",
                                 seed, hoje)

    # ---------------- Fontes de referência ----------------
    ano = hoje.year
    cardapio.publicar_cardapios(m.cardapios, bronze / "cardapio", taxa, seed, hoje)
    calendario.publicar_calendario(m.dias, bronze / "calendario_escolar", taxa,
                                   rng_para(seed, "falhas_calendario", ano), ano)
    clima.publicar_clima(m.clima, bronze / "clima", taxa, seed, ano, hoje)
    alunos.publicar_turmas(m.turmas, bronze / "turmas_alunos", taxa,
                           rng_para(seed, "falhas_turmas", ano), ano)
    inflacao.publicar_inflacao(m.inflacao, bronze / "inflacao", taxa, seed, ano, hoje)

    # ---------------- Resumo ----------------
    print(f"Execução de {agora:%d/%m/%Y %H:%M} | dados em: {args.saida.resolve()}")
    if not dia.tem_aula:
        print(f"  Hoje não houve aula ({dia.descricao}): nenhuma venda gerada.")
    else:
        total = registradas.get(hoje, (0, 0))[1]
        print(f"  Vendas registradas agora: {len(pendentes)} (hoje: {total} de {len(vendas_dia)})")
        if qtd_perdas is not None:
            print(f"  Dia fechado. Perdas registradas: {qtd_perdas}")
        elif dia_fechado:
            print("  Dia já fechado em execução anterior; nada novo a registrar.")
        else:
            print(f"  Perdas serão registradas após o fechamento ({vendas.fim_expediente(dia):%H:%M}).")
    print(f"  Débitos no controle de devedores: {len(dividas)}")

    # ---------------- Envio ao GitHub ----------------
    if args.sem_github:
        print("  GitHub: envio desativado (--sem-github); dados mantidos localmente.")
    else:
        resumo = enviar_dados(args.saida, f"Dados da cantina: execução de {agora:%d/%m/%Y %H:%M}",
                              args.remoto, args.branch)
        print(f"  GitHub: {resumo}")


if __name__ == "__main__":
    main()
