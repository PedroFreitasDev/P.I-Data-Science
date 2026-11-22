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

Com --periodo, o gerador simula, dia a dia, as execuções que o cron teria feito
num intervalo de datas (por padrão às 13h e às 19h), seguindo exatamente as
mesmas regras de uma execução normal. Serve para criar a base de um período
inteiro de uma vez ou para preencher dias em que o gerador não rodou.

Uso:
    python gerar_dados.py                        # execução normal (horário de Brasília)
    python gerar_dados.py --dia-completo         # registra o dia inteiro de uma vez
    python gerar_dados.py --sem-github           # não envia nada ao GitHub
    python gerar_dados.py --agora "2026-09-24 19:00"   # simula o horário (testes)
    python gerar_dados.py --periodo 2026-01-01 2026-11-22   # simula um período inteiro
"""

import argparse
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

from gerador import alunos, calendario, cardapio, clima, devedores, inflacao, perdas, vendas
from gerador.github import enviar_dados
from gerador.historico import interpretar_data, maior_id_por_dia, vendas_registradas
from gerador.mundo import mundo
from gerador.utils import anexar_excel, consolidar_lote, intervalo_datas, ler_excel, rng_para

try:
    from zoneinfo import ZoneInfo
    FUSO = ZoneInfo("America/Sao_Paulo")
except Exception:  # sem base de fusos no sistema: usa o horário local da máquina
    FUSO = None

RAIZ_GERADOR = Path(__file__).resolve().parent
HORARIOS_PADRAO = "13:00,19:00"  # mesmos horários do cron sugerido no README


def agora_local() -> datetime:
    return datetime.now(FUSO).replace(tzinfo=None) if FUSO else datetime.now()


@dataclass
class Opcoes:
    seed: int
    taxa: float
    min_alunos: int
    max_alunos: int
    saida: Path
    dia_completo: bool
    manter_lote: bool

    @property
    def bronze(self) -> Path:
        return self.saida / "bronze"

    @property
    def lotes(self) -> Path:
        return RAIZ_GERADOR / "lotes"

    @property
    def hist_vendas(self) -> Path:
        return self.bronze / "vendas" / vendas.ARQUIVO_HISTORICO

    @property
    def hist_perdas(self) -> Path:
        return self.bronze / "perdas" / perdas.ARQUIVO_HISTORICO

    def mundo(self, ano: int):
        return mundo(self.seed, ano, self.min_alunos, self.max_alunos)


@dataclass
class Progresso:
    """Até onde o gerador já chegou, reconstruído a partir dos históricos."""
    registradas: dict  # {data: (primeiro id do dia, vendas já registradas no dia)}
    dias_fechados: set  # dias que já têm perdas registradas
    proximo_id_perda: int

    @classmethod
    def ler(cls, op: Opcoes) -> "Progresso":
        registradas = vendas_registradas(maior_id_por_dia(op.hist_vendas))
        _, linhas = ler_excel(op.hist_perdas) if op.hist_perdas.exists() else ([], [])
        fechados = {interpretar_data(l[1]) for l in linhas} - {None}
        proximo = max((l[0] for l in linhas if isinstance(l[0], int)), default=0) + 1
        return cls(registradas, fechados, proximo)

    def ultimo_dia(self) -> date | None:
        return max(self.registradas, default=None)


@dataclass
class Consolidador:
    """Leva os arquivos de lote para os históricos.

    Na execução normal, cada lote é consolidado na hora. Na simulação de um
    período, os lotes ficam acumulados e são consolidados de uma vez a cada mês
    (o resultado é o mesmo, mas sem reabrir a planilha inteira a cada lote).
    """
    manter_lote: bool
    acumular: bool = False
    pendentes: list = field(default_factory=list)  # [(lote, histórico, aba)]

    def adicionar(self, lote: Path, historico: Path, aba: str):
        if self.acumular:
            self.pendentes.append((lote, historico, aba))
        else:
            consolidar_lote(lote, historico, aba, self.manter_lote)

    def descarregar(self):
        por_historico = {}
        for lote, historico, aba in self.pendentes:
            colunas, linhas = ler_excel(lote)
            destino = por_historico.setdefault(historico, {"aba": aba, "colunas": colunas, "linhas": []})
            destino["linhas"] += linhas
        for historico, d in por_historico.items():
            anexar_excel(historico, d["colunas"], d["linhas"], d["aba"])
        if not self.manter_lote:
            for lote, _, _ in self.pendentes:
                lote.unlink()
        self.pendentes.clear()


@dataclass
class ResumoDia:
    tem_aula: bool
    descricao: str
    vendas_agora: int = 0
    vendas_hoje: int = 0
    vendas_total_dia: int = 0
    qtd_perdas: int | None = None
    dia_fechado: bool = False
    fim_expediente: time | None = None


def registrar_dia(op: Opcoes, agora: datetime, prog: Progresso, consolidador: Consolidador) -> ResumoDia:
    """Passos 1 e 2: vendas que já aconteceram até `agora` e, no fechamento, as perdas."""
    hoje = agora.date()
    m = op.mundo(hoje.year)
    dia = m.dia_por_data[hoje]
    registradas = prog.registradas

    ultimo = prog.ultimo_dia()
    if ultimo and ultimo > hoje:
        raise SystemExit(f"O histórico já tem vendas de {ultimo}; "
                         "não é possível gerar dados de uma data anterior.")
    if hoje in registradas:
        primeiro_id, ja_registradas = registradas[hoje]
    else:
        primeiro_id = max((p + n for p, n in registradas.values()), default=1)
        ja_registradas = 0

    # ---------------- Vendas de hoje ----------------
    vendas_dia = m.vendas_do_dia(hoje, primeiro_id)
    pendentes = [v for v in vendas_dia[ja_registradas:] if op.dia_completo or v.data_hora <= agora]
    if pendentes:
        lote = op.lotes / f"vendas_{agora:%Y-%m-%d_%H%M%S}.xlsx"
        vendas.gravar_lote(pendentes, lote, op.taxa, rng_para(op.seed, "falhas_vendas", hoje, pendentes[0].id))
        consolidador.adicionar(lote, op.hist_vendas, "vendas")
        registradas[hoje] = (primeiro_id, ja_registradas + len(pendentes))

    resumo = ResumoDia(dia.tem_aula, dia.descricao, len(pendentes),
                       registradas.get(hoje, (0, 0))[1], len(vendas_dia),
                       dia_fechado=hoje in prog.dias_fechados,
                       fim_expediente=vendas.fim_expediente(dia))

    # ---------------- Perdas (fechamento do expediente) ----------------
    expediente_encerrado = op.dia_completo or agora.time() >= vendas.fim_expediente(dia)
    if (dia.tem_aula and not resumo.dia_fechado and expediente_encerrado
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
        lista_perdas = perdas.gerar_perdas_dia(hoje, vendas_dia, m.cardapios.disponiveis(hoje),
                                               historico_vendido, prog.proximo_id_perda,
                                               rng_para(op.seed, "perdas", hoje))
        if lista_perdas:
            lote = op.lotes / f"perdas_{agora:%Y-%m-%d_%H%M%S}.xlsx"
            perdas.gravar_lote(lista_perdas, lote, op.taxa, rng_para(op.seed, "falhas_perdas", hoje))
            consolidador.adicionar(lote, op.hist_perdas, "perdas")
            prog.dias_fechados.add(hoje)
            prog.proximo_id_perda += len(lista_perdas)
        resumo.qtd_perdas = len(lista_perdas)
    return resumo


def publicar_devedores(op: Opcoes, hoje: date, prog: Progresso) -> int:
    """Passo 3: recalcula os devedores a partir do fiado já registrado."""
    fiado = []
    for d, (p, n) in sorted(prog.registradas.items()):
        fiado += [v for v in op.mundo(d.year).vendas_do_dia(d, p)[:n] if v.forma_pagamento == "Fiado"]
    dividas = devedores.montar_dividas(fiado, op.seed, op.taxa)

    def pagador_de(id_aluno, data):
        # débitos de anos anteriores podem ser de alunos que não estão mais na base
        aluno = op.mundo(data.year).alunos_por_id.get(id_aluno)
        return aluno.pagador if aluno else "atrasa"

    devedores.publicar_devedores(dividas, pagador_de, set(op.mundo(hoje.year).alunos_por_id),
                                 op.bronze / "devedores", op.seed, hoje)
    return len(dividas)


def publicar_referencias(op: Opcoes, hoje: date):
    """Passo 4: fontes de referência, com o que já existe na data de hoje."""
    m, ano, bronze, taxa, seed = op.mundo(hoje.year), hoje.year, op.bronze, op.taxa, op.seed
    cardapio.publicar_cardapios(m.cardapios, bronze / "cardapio", taxa, seed, hoje)
    calendario.publicar_calendario(m.dias, bronze / "calendario_escolar", taxa,
                                   rng_para(seed, "falhas_calendario", ano), ano)
    clima.publicar_clima(m.clima, bronze / "clima", taxa, seed, ano, hoje)
    alunos.publicar_turmas(m.turmas, bronze / "turmas_alunos", taxa,
                           rng_para(seed, "falhas_turmas", ano), ano)
    inflacao.publicar_inflacao(m.inflacao, bronze / "inflacao", taxa, seed, ano, hoje)


def enviar(args, mensagem: str):
    """Passo 5: envio ao GitHub."""
    if args.sem_github:
        print("  GitHub: envio desativado (--sem-github); dados mantidos localmente.")
    else:
        print(f"  GitHub: {enviar_dados(args.saida, mensagem, args.remoto, args.branch)}")


def executar_agora(op: Opcoes, args):
    """Execução normal: um único horário (o atual ou o de --agora)."""
    agora = args.agora or agora_local()
    hoje = agora.date()
    prog = Progresso.ler(op)
    r = registrar_dia(op, agora, prog, Consolidador(op.manter_lote))
    qtd_dividas = publicar_devedores(op, hoje, prog)
    publicar_referencias(op, hoje)

    print(f"Execução de {agora:%d/%m/%Y %H:%M} | dados em: {op.saida.resolve()}")
    if not r.tem_aula:
        print(f"  Hoje não houve aula ({r.descricao}): nenhuma venda gerada.")
    else:
        print(f"  Vendas registradas agora: {r.vendas_agora} (hoje: {r.vendas_hoje} de {r.vendas_total_dia})")
        if r.qtd_perdas is not None:
            print(f"  Dia fechado. Perdas registradas: {r.qtd_perdas}")
        elif r.dia_fechado:
            print("  Dia já fechado em execução anterior; nada novo a registrar.")
        else:
            print(f"  Perdas serão registradas após o fechamento ({r.fim_expediente:%H:%M}).")
    print(f"  Débitos no controle de devedores: {qtd_dividas}")
    enviar(args, f"Dados da cantina: execução de {agora:%d/%m/%Y %H:%M}")


def horarios_execucao(texto: str) -> list[time]:
    try:
        horarios = sorted({time.fromisoformat(h.strip()) for h in texto.split(",") if h.strip()})
    except ValueError:
        raise argparse.ArgumentTypeError(f'horários inválidos: "{texto}" (use por ex. "13:00,19:00")')
    if not horarios:
        raise argparse.ArgumentTypeError("informe pelo menos um horário")
    return horarios


def executar_periodo(op: Opcoes, args):
    """Simula, dia a dia, as execuções que teriam acontecido entre as duas datas.

    Cada execução simulada segue as mesmas regras da execução normal (só grava o
    que já aconteceu até aquele horário, fecha o dia depois do expediente, etc.).
    Devedores e fontes de referência são recalculados a cada execução e dependem
    apenas da data, então basta publicá-los no último dia de cada ano do período
    e no fim dele: o resultado é idêntico ao de ter rodado todos os dias.
    """
    inicio, fim = args.periodo
    agora_real = agora_local()
    if inicio > fim:
        raise SystemExit(f"Período inválido: {inicio} é depois de {fim}.")
    if fim > agora_real.date():
        raise SystemExit(f"O fim do período ({fim}) está no futuro; o gerador nunca grava "
                         "dados de dias que ainda não aconteceram.")

    prog = Progresso.ler(op)
    ultimo = prog.ultimo_dia()
    if ultimo and ultimo > inicio:
        raise SystemExit(
            f"A pasta {op.bronze} já tem vendas até {ultimo:%d/%m/%Y}, depois do início do período "
            f"({inicio:%d/%m/%Y}).\nO período deve começar depois do que já foi gerado. Para gerar do "
            "zero, use outra pasta com --saida ou apague o conteúdo de dados/bronze antes.")

    print(f"Simulando o período de {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} "
          f"(execuções às {', '.join(h.strftime('%H:%M') for h in args.horarios)}) | "
          f"dados em: {op.saida.resolve()}")

    consolidador = Consolidador(op.manter_lote, acumular=True)
    execucoes = vendas_total = perdas_total = dias_letivos = 0
    ultima_execucao = None
    try:
        for d in intervalo_datas(inicio, fim):
            momentos = [datetime.combine(d, h) for h in args.horarios]
            if d == agora_real.date():
                # hoje: só os horários que já passaram, mais uma execução agora
                momentos = [a for a in momentos if a < agora_real] + [agora_real]
            for agora in momentos:
                r = registrar_dia(op, agora, prog, consolidador)
                execucoes += 1
                vendas_total += r.vendas_agora
                perdas_total += r.qtd_perdas or 0
                ultima_execucao = agora
            dias_letivos += r.tem_aula

            fim_do_mes = d == fim or (d + timedelta(days=1)).month != d.month
            if fim_do_mes:
                consolidador.descarregar()
                pendentes = r.tem_aula and r.vendas_hoje < r.vendas_total_dia
                print(f"  {d:%m/%Y}: {vendas_total} vendas e {perdas_total} perdas registradas até agora"
                      + (" (dia atual ainda em andamento)" if pendentes else ""))
            if d != fim and (d + timedelta(days=1)).year != d.year:
                publicar_referencias(op, d)  # fecha as fontes do ano que terminou
    finally:
        consolidador.descarregar()

    hoje = ultima_execucao.date()
    qtd_dividas = publicar_devedores(op, hoje, prog)
    publicar_referencias(op, hoje)

    print(f"  Concluído: {execucoes} execuções simuladas, {dias_letivos} dias com aula, "
          f"{vendas_total} vendas e {perdas_total} perdas registradas.")
    print(f"  Débitos no controle de devedores: {qtd_dividas}")
    enviar(args, f"Dados da cantina: simulação de {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}")


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
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--agora", type=datetime.fromisoformat, default=None,
                      help='Data/hora simulada "AAAA-MM-DD HH:MM" (apenas para testes)')
    modo.add_argument("--periodo", nargs=2, type=date.fromisoformat, metavar=("INICIO", "FIM"),
                      help="Simula todas as execuções entre duas datas, ex.: 2026-01-01 2026-11-22")
    parser.add_argument("--horarios", type=horarios_execucao, default=horarios_execucao(HORARIOS_PADRAO),
                        help=f'Horários das execuções simuladas com --periodo (padrão: "{HORARIOS_PADRAO}")')
    args = parser.parse_args()

    op = Opcoes(seed=args.seed, taxa=0.0 if args.sem_falhas else args.taxa_falhas,
                min_alunos=args.min_alunos, max_alunos=args.max_alunos, saida=args.saida,
                dia_completo=args.dia_completo, manter_lote=args.manter_lote)
    if args.periodo:
        executar_periodo(op, args)
    else:
        executar_agora(op, args)


if __name__ == "__main__":
    main()
