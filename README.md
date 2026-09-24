# P.I-Data-Science

Projeto Integrador — Grupo 3 (Data Science): pipeline de dados para uma cantina escolar
parceira, das fontes brutas até tabelas prontas para análise (Bronze → Silver → Gold).

Como a empresa parceira trabalha com dados sensíveis, o projeto usa **dados fictícios**
produzidos pelo gerador descrito abaixo.

## Estrutura do repositório

```
.
├── DOCS/
│   └── especificacao_dados_pipeline_cantina.pdf   # especificação das fontes e do pipeline
└── gerador_dados/
    ├── gerar_dados.py          # ponto de entrada (linha de comando)
    ├── requirements.txt
    ├── gerador/                # um módulo por fonte de dados
    │   ├── config.py           # produtos, nomes, clima médio, inflação média...
    │   ├── calendario.py       # 1.5 Calendário Escolar
    │   ├── clima.py            # 1.6 Clima e Temperatura
    │   ├── inflacao.py         # 1.8 Índice de Inflação
    │   ├── cardapio.py         # 1.3 Cardápio de Produtos
    │   ├── alunos.py           # 1.7 Turmas e Alunos
    │   ├── vendas.py           # 1.1 Vendas
    │   ├── devedores.py        # 1.2 Devedores
    │   ├── perdas.py           # 1.4 Perdas/Desperdício
    │   ├── falhas.py           # gabarito das falhas inseridas
    │   └── utils.py
    └── saida/                  # gerado ao rodar o script (ignorado pelo git)
```

## Gerador de dados fictícios

Gera as 8 fontes descritas na seção 1 da especificação, já organizadas como a camada
**Bronze** (`saida/bronze/<fonte>/`), cada uma no seu formato e frequência originais.

### Como usar

Requer Python 3.10+.

```bash
cd gerador_dados
pip install -r requirements.txt
python gerar_dados.py
```

Opções:

| Opção | Padrão | Descrição |
|---|---|---|
| `--ano` | `2025` | Ano letivo simulado |
| `--seed` | `42` | Semente aleatória (mesma semente = mesmos dados) |
| `--taxa-falhas` | `0.03` | Proporção aproximada de registros com falha |
| `--sem-falhas` | — | Gera os dados sem falhas de digitação/registro |
| `--min-alunos` / `--max-alunos` | `20` / `28` | Alunos por turma |
| `--saida` | `gerador_dados/saida` | Pasta de saída |

Exemplo: `python gerar_dados.py --ano 2026 --seed 7 --taxa-falhas 0.05`

### Arquivos gerados

| Fonte (PDF) | Formato | Arquivos em `saida/bronze/` |
|---|---|---|
| 1.1 Vendas | Excel | `vendas/vendas_AAAA-Sxx.xlsx` (uma planilha por semana) |
| 1.2 Devedores | Excel | `devedores/devedores_atualizado_AAAA-MM-DD.xlsx` |
| 1.3 Cardápio | Excel | `cardapio/cardapio_vigencia_AAAA-MM-DD.xlsx` (1º e 2º semestre) |
| 1.4 Perdas | Excel | `perdas/perdas_AAAA-MM.xlsx` (uma planilha por mês) |
| 1.5 Calendário Escolar | JSON | `calendario_escolar/calendario_escolar_AAAA.json` |
| 1.6 Clima | JSON | `clima/clima_AAAA.json` |
| 1.7 Turmas e Alunos | JSON (aninhado) | `turmas_alunos/turmas_alunos_AAAA.json` |
| 1.8 Inflação | JSON | `inflacao/inflacao_AAAA.json` |

Além disso, `saida/gabarito_falhas.csv` (separado por `;`) lista **cada falha inserida**:
fonte, arquivo, registro, campo, tipo da falha, valor correto e valor registrado. Ele serve
para conferir se a camada Silver detectou e tratou os problemas — não faz parte da Bronze.

A fonte "Frequência (CSV externo/SED)", citada no fluxo do pipeline, não é gerada porque o
PDF não define seu schema.

### Coerência dos dados

Primeiro o gerador simula o que "realmente aconteceu". Só depois publica os arquivos,
e é nessa etapa que entram as falhas. Por isso, fora as falhas propositais, os dados são
consistentes entre si:

- **Idade × série:** a data de nascimento segue a regra de corte de 31/03 (6 anos no 1º ano do
  EF, 17 anos na 3ª série do EM). Cerca de 6% dos alunos são um ano mais velhos (repetentes).
- **Turnos e horários:** o EF I tem turmas de manhã e à tarde; o EF II e o EM estudam de manhã.
  As vendas acontecem só no turno do aluno, na entrada, no intervalo ou na saída.
- **Calendário:** não há vendas nem perdas em feriados, férias, recessos, fins de semana e
  planejamento. A Quarta-feira de Cinzas só tem aula à tarde e os conselhos de classe só de manhã.
  A Festa Junina cai num sábado letivo, com movimento maior.
- **Restrições alimentares:** um aluno celíaco não compra coxinha, um intolerante à lactose
  não compra pão de queijo, e assim por diante. Café e açaí só são comprados a partir de
  certas séries.
- **Clima:** a temperatura acompanha as estações, com verão quente e chuvoso e inverno frio e seco.
  Chuva sempre vem com precipitação > 0 e a máxima nunca fica abaixo da média. Dias quentes vendem mais
  bebidas geladas e picolé, dias frios vendem mais chocolate quente e misto quente, e a chuva
  reduz a presença dos alunos.
- **Preços × inflação:** o cardápio do 2º semestre é reajustado pela inflação acumulada de
  cada categoria, usando só os meses já publicados na data da troca. As vendas usam o preço
  vigente na data e `valor_total = quantidade × valor_unitario`.
- **Devedores:** as dívidas vêm das vendas "Fiado", fechadas por aluno no fim de cada mês.
  O status (Quitado / Em aberto / Atrasado) é calculado na data de referência da planilha.
- **Perdas:** a produção de perecíveis segue a média de vendas dos dias anteriores, e o que
  sobra vira perda. Dias atípicos, como os de chuva ou calor, geram mais desperdício.

### Inconsistências simuladas

Os tipos abaixo são os da especificação. A lista completa, registro por registro, está no gabarito.

| Fonte | Falhas inseridas |
|---|---|
| Vendas | `forma_pagamento` vazia ou digitada errada; `valor_total` diferente do cálculo; linhas duplicadas e `id_venda` repetido; datas em formatos diferentes (planilhas inteiras em texto `dd/mm/aaaa` e linhas em `aaaa-mm-dd`); preços negativos; preço sem a vírgula (450 em vez de 4,50); quantidade 0, negativa ou absurda; produto inexistente no cardápio; `id_aluno` vazio |
| Devedores | `id_aluno` que não existe na base; status desatualizado; quitação anterior à dívida; o mesmo débito lançado duas vezes; valor negativo, vazio ou absurdo; status digitado errado |
| Cardápio | `custo_unitario` ausente; preço desatualizado em relação à inflação; preço absurdo; custo negativo; nome ou categoria fora do padrão. Produtos descontinuados continuam aparecendo nas vendas por alguns dias (estoque remanescente) |
| Perdas | motivo vazio; produto sem correspondência no cardápio; quantidade zerada ou negativa; `valor_prejuizo` diferente do cálculo; data em formato diferente |
| Calendário | feriado nacional marcado como letivo; greve e reposição que não foram atualizadas no calendário publicado; `tipo_dia` digitado errado; `turno_letivo` ausente |
| Clima | dias ausentes ou com valores nulos (falha na requisição); dias com 24 leituras horárias (granularidade diferente); bloco de dias com fuso horário divergente; temperatura absurda; precipitação negativa |
| Turmas/Alunos | `id_aluno` em outro formato (`"001234"`, `"ALU01234"`); campos aninhados ausentes; homônimos (alunos diferentes com o mesmo nome); data de nascimento inválida ou em outro formato; nome fora do padrão |
| Inflação | defasagem de publicação (últimos 2 meses ausentes); categorias com nomenclatura diferente da do cardápio; índice nulo ou absurdo; mês em outro formato |

As falhas são sempre erros evidentes, como campo vazio, sinal trocado, vírgula esquecida ou data
impossível. O gerador nunca cria dados "plausíveis porém errados", como um aluno do 8º ano com
5 anos de idade.

Mesmo com `--sem-falhas`, algumas situações do mundo real continuam no gabarito, porque fazem
parte do cenário e não são erros de digitação: a greve e a reposição que não entraram no
calendário, a defasagem e a nomenclatura da API de inflação, e os itens do cardápio não reajustados.

Os IDs têm formatos diferentes entre as fontes, como previsto na especificação: `id_aluno` é
`"ALU01234"` nas vendas e `1234` nos devedores e alunos, e `id_produto` é `"P012"` nas vendas e
`12` no cardápio e nas perdas. Esse mapeamento de chaves fica a cargo da camada Silver.
