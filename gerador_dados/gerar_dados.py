"""Gerador diário de dados fictícios da cantina escolar.

Pensado para rodar 1 ou 2 vezes por dia (ex.: via cron em uma VM). A cada execução:

1. Vendas: gera apenas as vendas de HOJE (75 a 150 no dia) que já aconteceram até
   o horário atual e ainda não foram registradas. Elas são gravadas num arquivo
   de lote, que é acrescentado à planilha de histórico e depois apagado.
2. Perdas: no fechamento do expediente, gera as perdas do dia (mesmo esquema de
   lote -> histórico).
3. Devedores: registra os débitos das vendas "Fiado" e republica a planilha com
   o status de hoje.
4. Republica as fontes de referência (calendário, turmas/alunos, cardápio,
   clima e inflação), limitadas ao que já existe na data de hoje.

O progresso fica em `saida/estado.json`. Apagar esse arquivo e a pasta `saida/`
recomeça tudo do zero.

Uso:
    python gerar_dados.py                        # execução normal (horário de Brasília)
    python gerar_dados.py --dia-completo         # registra o dia inteiro de uma vez
    python gerar_dados.py --agora "2026-09-24 19:00"   # simula o horário (testes)
"""

import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path

from gerador import alunos, calendario, cardapio, clima, devedores, inflacao, perdas, vendas
from gerador.falhas import Gabarito
from gerador.utils import consolidar_lote, rng_para

try:
    from zoneinfo import ZoneInfo
    FUSO = ZoneInfo("America/Sao_Paulo")
except Exception:  # sem base de fusos no sistema: usa o horário local da máquina
    FUSO = None


def agora_local() -> datetime:
    return datetime.now(FUSO).replace(tzinfo=None) if FUSO else datetime.now()


def carregar_estado(caminho: Path, seed: int) -> dict:
    if caminho.exists():
        estado = json.loads(caminho.read_text(encoding="utf-8"))
        if estado["seed"] != seed:
            raise SystemExit(f"A pasta de saída foi iniciada com --seed {estado['seed']}. "
                             "Use a mesma semente ou outra pasta (--saida).")
        return estado
    return {"seed": seed, "dia": None, "primeiro_id_venda_dia": 1, "vendas_registradas_dia": 0,
            "dia_fechado": False, "proximo_id_venda": 1, "proximo_id_perda": 1,
            "proximo_id_devedor": 1, "vendido_recente": {}, "dividas": [], "execucoes": []}


def salvar_estado(caminho: Path, estado: dict):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, caminho)  # gravação atômica: não corrompe o estado se a VM cair


def main():
    parser = argparse.ArgumentParser(description="Gera os dados fictícios do dia da cantina escolar.")
    parser.add_argument("--seed", type=int, default=42, help="Semente aleatória (padrão: 42)")
    parser.add_argument("--taxa-falhas", type=float, default=0.03,
                        help="Proporção aproximada de registros com falha (padrão: 0.03)")
    parser.add_argument("--sem-falhas", action="store_true", help="Gera os dados sem falhas")
    parser.add_argument("--min-alunos", type=int, default=20, help="Mínimo de alunos por turma")
    parser.add_argument("--max-alunos", type=int, default=28, help="Máximo de alunos por turma")
    parser.add_argument("--saida", type=Path, default=Path(__file__).parent / "saida",
                        help="Pasta de saída (padrão: gerador_dados/saida)")
    parser.add_argument("--dia-completo", action="store_true",
                        help="Registra todas as vendas de hoje e fecha o dia, sem esperar o horário")
    parser.add_argument("--manter-lote", action="store_true",
                        help="Não apaga os arquivos de lote após consolidar no histórico")
    parser.add_argument("--agora", type=datetime.fromisoformat, default=None,
                        help='Data/hora simulada "AAAA-MM-DD HH:MM" (apenas para testes)')
    args = parser.parse_args()

    taxa = 0.0 if args.sem_falhas else args.taxa_falhas
    seed = args.seed
    agora = args.agora or agora_local()
    hoje = agora.date()
    ano = hoje.year
    bronze = args.saida / "bronze"
    lotes = args.saida / "lotes"
    caminho_estado = args.saida / "estado.json"
    estado = carregar_estado(caminho_estado, seed)
    if estado["dia"] and date.fromisoformat(estado["dia"]) > hoje:
        raise SystemExit(f"O estado já registra o dia {estado['dia']}; não é possível voltar no tempo.")
    gabarito = Gabarito()

    # ---------------- Mundo "real" do ano (determinístico pela semente) ----------------
    dias = calendario.gerar_calendario(ano, rng_para(seed, "calendario", ano))
    clima_real = clima.gerar_clima(ano, rng_para(seed, "clima", ano))
    inflacao_real = inflacao.gerar_inflacao(ano, rng_para(seed, "inflacao", ano))
    vigencia_1 = next(d.data for d in dias if d.tipo_dia == "planejamento")
    vigencia_2 = next(d.data for d in dias if d.data > date(ano, 7, 5) and d.tem_aula)
    cardapios = cardapio.gerar_cardapios(vigencia_1, vigencia_2, inflacao_real,
                                         rng_para(seed, "cardapio", ano))
    turmas = alunos.gerar_turmas(ano, rng_para(seed, "turmas", ano), args.min_alunos, args.max_alunos)
    alunos_por_id = {a.id: a for t in turmas for a in t.alunos}
    dia = next(d for d in dias if d.data == hoje)

    if estado["dia"] != hoje.isoformat():
        estado.update(dia=hoje.isoformat(), primeiro_id_venda_dia=estado["proximo_id_venda"],
                      vendas_registradas_dia=0, dia_fechado=False)

    # ---------------- Vendas de hoje ----------------
    itens = cardapios.disponiveis(hoje)
    vendas_dia = vendas.simular_dia(dia, clima_real[hoje], turmas, itens,
                                    estado["primeiro_id_venda_dia"], rng_para(seed, "vendas", hoje))
    ja_registradas = estado["vendas_registradas_dia"]
    pendentes = [v for v in vendas_dia[ja_registradas:]
                 if args.dia_completo or v.data_hora <= agora]
    if pendentes:
        lote = lotes / f"vendas_{agora:%Y-%m-%d_%H%M%S}.xlsx"
        vendas.gravar_lote(pendentes, lote, gabarito, taxa,
                           rng_para(seed, "falhas_vendas", hoje, pendentes[0].id))
        consolidar_lote(lote, bronze / "vendas" / vendas.ARQUIVO_HISTORICO, "vendas", args.manter_lote)
        devedores.registrar_fiado(estado, pendentes, seed, taxa)
        estado["vendas_registradas_dia"] += len(pendentes)
        estado["proximo_id_venda"] = pendentes[-1].id + 1
        salvar_estado(caminho_estado, estado)

    # ---------------- Perdas (fechamento do expediente) ----------------
    qtd_perdas = None
    expediente_encerrado = args.dia_completo or agora.time() >= vendas.fim_expediente(dia)
    if (dia.tem_aula and not estado["dia_fechado"] and expediente_encerrado
            and estado["vendas_registradas_dia"] == len(vendas_dia)):
        lista_perdas = perdas.gerar_perdas_dia(hoje, vendas_dia, itens, estado["vendido_recente"],
                                               estado["proximo_id_perda"], rng_para(seed, "perdas", hoje))
        if lista_perdas:
            lote = lotes / f"perdas_{agora:%Y-%m-%d_%H%M%S}.xlsx"
            perdas.gravar_lote(lista_perdas, lote, gabarito, taxa, rng_para(seed, "falhas_perdas", hoje))
            consolidar_lote(lote, bronze / "perdas" / perdas.ARQUIVO_HISTORICO, "perdas", args.manter_lote)
            estado["proximo_id_perda"] = lista_perdas[-1].id + 1
        qtd_perdas = len(lista_perdas)
        estado["dia_fechado"] = True

    # ---------------- Fontes republicadas a cada execução ----------------
    devedores.publicar_devedores(estado, alunos_por_id, bronze / "devedores", gabarito, seed, hoje)
    cardapio.publicar_cardapios(cardapios, bronze / "cardapio", gabarito, taxa, seed, hoje)
    calendario.publicar_calendario(dias, bronze / "calendario_escolar", gabarito, taxa,
                                   rng_para(seed, "falhas_calendario", ano), ano)
    clima.publicar_clima(clima_real, bronze / "clima", gabarito, taxa, seed, ano, hoje)
    alunos.publicar_turmas(turmas, bronze / "turmas_alunos", gabarito, taxa,
                           rng_para(seed, "falhas_turmas", ano), ano)
    inflacao.publicar_inflacao(inflacao_real, bronze / "inflacao", gabarito, taxa, seed, ano, hoje)
    gabarito.salvar(args.saida / "gabarito_falhas.csv")

    estado["execucoes"] = (estado["execucoes"] + [{
        "em": agora.isoformat(timespec="seconds"), "vendas": len(pendentes), "perdas": qtd_perdas or 0,
    }])[-60:]
    salvar_estado(caminho_estado, estado)

    # ---------------- Resumo ----------------
    print(f"Execução de {agora:%d/%m/%Y %H:%M} | saída: {args.saida.resolve()}")
    if not dia.tem_aula:
        print(f"  Hoje não houve aula ({dia.descricao}): nenhuma venda gerada.")
    else:
        print(f"  Vendas registradas agora: {len(pendentes)} "
              f"(hoje: {estado['vendas_registradas_dia']} de {len(vendas_dia)})")
        if qtd_perdas is not None:
            print(f"  Dia fechado. Perdas registradas: {qtd_perdas}")
        elif estado["dia_fechado"]:
            print("  Dia já fechado em execução anterior; nada novo a registrar.")
        else:
            print(f"  Perdas serão registradas após o fechamento ({vendas.fim_expediente(dia):%H:%M}).")
    print(f"  Débitos no controle de devedores: {len(estado['dividas'])}")


if __name__ == "__main__":
    main()
