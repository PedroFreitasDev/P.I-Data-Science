# Entendendo o notebook da cantina — explicado sem complicação

Este documento explica, em linguagem simples, o que faz o arquivo
**`Projeto_Cantina_BigData.ipynb`** e por que cada parte existe. Não é preciso saber programar
para acompanhar.

---

## 1. A ideia geral em uma frase

> Pegamos tudo o que a cantina registra (vendas, fiado, desperdício, cardápio, alunos, clima,
> calendário e inflação), juntamos essas informações e transformamos em **respostas** e
> **previsões** que ajudam a cantina a vender mais, desperdiçar menos e controlar o fiado.

## 2. De onde vêm os dados

O projeto inteiro funciona como uma **linha de montagem** em três andares, chamada de
"arquitetura medalhão":

| Andar | Apelido | O que tem | Comparação do dia a dia |
|---|---|---|---|
| 🥉 Bronze | dados brutos | Planilhas e arquivos do jeito que chegam, com erros de digitação, datas trocadas, linhas repetidas | As compras do mercado ainda nas sacolas |
| 🥈 Silver | dados limpos | Os mesmos dados, mas corrigidos e padronizados | As compras lavadas e guardadas nos armários |
| 🥇 Gold | dados prontos | Resumos que respondem perguntas de negócio | O prato pronto, servido |

**A limpeza (Bronze → Silver) é feita em outra etapa do projeto.** Este notebook já começa com os
dados limpos e cuida do andar **Gold** e das **previsões**.

> Os dados são **fictícios**: a cantina parceira tem informações sensíveis, então um programa
> simula o dia a dia dela de forma realista.

## 3. O que é um "notebook" e o Google Colab

Um **notebook** é um documento que mistura textos explicativos e pequenos blocos de código
("células"). Cada célula é executada em ordem, como as etapas de uma receita.

O **Google Colab** é um site do Google que roda esse notebook **na nuvem**, de graça: não é
preciso instalar nada no computador.

### Como rodar

1. Acesse [colab.research.google.com](https://colab.research.google.com) e abra o arquivo
   `Projeto_Cantina_BigData.ipynb` (menu **Arquivo → Fazer upload de notebook**, ou pela aba GitHub).
2. Na primeira célula de configuração (seção 1), confira de onde virão os dados limpos:
   - `"github"` (padrão): o notebook baixa sozinho os dados do repositório do projeto, na pasta `dados/silver/`;
   - `"drive"`: os dados estão numa pasta do seu Google Drive.
3. Clique em **Ambiente de execução → Executar tudo** e espere. Tabelas e gráficos vão aparecendo
   abaixo de cada célula.

Se faltar algum arquivo ou coluna, o notebook avisa **exatamente** qual está faltando.

### Quais arquivos limpos o notebook espera

Um arquivo por tabela (pode ser `.csv`, `.parquet` ou `.xlsx`), com estes nomes:
`vendas`, `devedores`, `cardapio`, `perdas`, `calendario`, `clima`, `alunos` e `inflacao`.
As colunas de cada um são as mesmas da especificação do projeto
(`DOCS/especificacao_dados_pipeline_cantina.pdf`) e estão listadas no começo do notebook.
A tabela de alunos deve vir "achatada": uma linha por aluno, com a turma ao lado.

---

## 4. O que o notebook faz, parte por parte

### Parte 1 — Carregar e conferir

O notebook lê as 8 tabelas e confere se cada uma tem as colunas combinadas. É como conferir a
nota fiscal ao receber uma entrega antes de assinar.

### Parte 2 — Juntar as informações

Sozinha, uma venda diz pouco: *"aluno 1234 comprou o produto 7"*.
Cruzando com as outras tabelas, ela vira:
*"um aluno do 7º ano A comprou um **misto quente** (Lanches) numa **terça-feira fria e chuvosa**"*.

É esse cruzamento que permite responder às perguntas das próximas partes. Também é criada uma
tabela com **um resumo por dia de aula** (quanto vendeu, como estava o tempo, que tipo de dia era).

### Parte 3 — As tabelas Gold (respostas para o negócio)

| Pergunta | O que mostra | Para que serve |
|---|---|---|
| **Quanto cada turma compra por mês?** | Faturamento, itens, lucro e gasto médio por compra | Saber quais turmas são os principais clientes |
| **Quem está devendo?** | Valor vendido fiado e quanto está atrasado, por turma e mês | Agir cedo na cobrança, antes que a dívida cresça |
| **O tempo muda as vendas?** | Média de vendas por tipo de tempo e faixa de temperatura | Em dia quente vende mais bebida gelada e picolé; no frio, chocolate quente |
| **O que mais vai para o lixo?** | Prejuízo com desperdício por categoria e produto | Produzir menos do que sobra |
| **Qual o dia e horário de pico?** | Mapa de calor turma × dia da semana e dia × hora | Reforçar a equipe e o estoque nos momentos certos |
| **O preço acompanhou a inflação?** (bônus) | Reajuste de preços × inflação acumulada | Ver se a margem de lucro está encolhendo |

Os "mapas de calor" são tabelas coloridas: **quanto mais escura a cor, maior o número**.

### Parte 4 — Big Data com Hadoop (Aula 08)

Quando os dados são grandes demais para um computador só, o trabalho é dividido entre vários.
O **Hadoop** é um conjunto de ferramentas que organiza essa divisão. Usamos três ideias dele:

- **MapReduce** — imagine contar os votos de uma eleição: cada mesa conta os próprios votos
  (*map*), os votos de cada candidato são reunidos (*shuffle*) e depois somados (*reduce*).
  O notebook faz isso para descobrir os **produtos mais vendidos** e o **faturamento por forma
  de pagamento**, e confere que o resultado bate com a conta feita do jeito tradicional.
- **Sqoop** — "transportadora" que leva os dados para um **banco de dados**. O notebook grava
  tudo num arquivo `cantina.db`, que pode ser aberto em ferramentas de relatórios (Power BI, etc.).
- **Hive** — permite fazer perguntas aos dados em **SQL**, a "língua" universal dos bancos de dados.
  Exemplos: quais produtos dão mais lucro, qual o gasto médio por série e turno, quais turmas
  têm mais dívida atrasada.

> As outras ferramentas vistas na aula (YARN, Pig e HBase) **não foram usadas** porque não
> acrescentam nada aqui: o que elas fariam já é coberto pelas partes acima.

### Parte 5 — Prever quanto vai vender (Regressão, Aula 06)

**O problema:** a cantina prepara salgados e lanches **antes** de saber quantos alunos vão comprar.
Preparou demais → vai para o lixo. Preparou de menos → perde venda.

**A solução:** um modelo de **regressão**, que é um programa que **prevê um número**. Ele olha os
dias passados e aprende, por exemplo, que *"sexta-feira de calor vende mais"* e *"dia de
chuva forte vende menos"*.

- **O que ele prevê:** quantos itens serão vendidos no dia.
- **O que ele usa como pista:** dia da semana, dia do mês, temperatura, chuva, tipo de tempo e
  tipo de dia letivo.
- **O modelo usado:** *Random Forest* ("floresta aleatória") — centenas de árvores de decisão
  (como fluxogramas de "se… então…") que votam juntas. A média dos votos é a previsão.

**Como saber se funciona?** Ele aprende com os dias mais antigos e é testado nos dias mais
recentes, que ele nunca viu — exatamente como seria usado na vida real. Comparamos com um
"chute" (prever sempre a média). Os números mostrados são:

| Medida | O que significa |
|---|---|
| **MAE** | Em média, quantos itens o modelo erra por dia. Quanto **menor**, melhor |
| **RMSE** | Parecido com o MAE, mas pune mais os erros grandes |
| **R²** | De 0 a 1: quanto da variação das vendas o modelo consegue explicar. Quanto **mais perto de 1**, melhor (negativo = pior que o chute) |

No final, você informa a previsão do tempo de um dia e o notebook sugere **quanto preparar
de cada produto**.

### Parte 6 — Prever se o fiado vai atrasar (Classificação, Aula 05)

**O problema:** parte das vendas é fiado, e algumas dívidas demoram a ser pagas.

**A solução:** um modelo de **classificação**, que é um programa que **escolhe entre categorias**
— aqui, *"vai pagar em dia"* ou *"vai atrasar"* (mais de 30 dias).

- **Pistas usadas:** valor da compra, quantas vezes o aluno já comprou fiado antes e quanto
  isso somava, série, idade, turno, restrição alimentar e dia da compra.
- Só entram dívidas com mais de 30 dias, porque as recentes ainda não tiveram tempo de atrasar.
- Como os atrasos são minoria, o modelo recebe a instrução de **dar mais atenção a eles**, para
  não sair dizendo "todo mundo paga em dia" e acertar por preguiça.

Os números mostrados:

| Medida | Pergunta que responde |
|---|---|
| **Acurácia** | De todas as previsões, quantas acertou? |
| **Precisão** | Quando o modelo diz "vai atrasar", quantas vezes acerta? |
| **Recall** | De todas as dívidas que realmente atrasaram, quantas o modelo encontrou? |
| **F1** | Um equilíbrio entre precisão e recall |

A **matriz de confusão** é uma tabela 2×2 que mostra os acertos (na diagonal) e os erros
(fora dela). No final, o notebook calcula a **chance de atraso** de uma nova compra fiado —
útil para decidir, por exemplo, quando avisar o responsável.

### Parte 7 — Apache Spark (Aula 09)

O **Spark** é uma ferramenta de Big Data muito rápida, que divide o trabalho entre vários
computadores e também consegue processar dados **que chegam aos poucos** (*streaming*).

1. **Spark SQL:** refazemos um dos resumos usando o Spark e conferimos que dá o mesmo valor.
2. **Streaming — o "painel ao vivo":** as vendas da cantina chegam em lotes ao longo do dia.
   O notebook simula isso entregando **um dia de vendas por vez** numa pasta. O Spark "vigia" a
   pasta e, a cada lote novo, **atualiza sozinho** o faturamento por categoria — como o placar
   de um jogo sendo atualizado a cada gol.

### Parte 8 — Resumo e arquivos finais

Uma tabela com os principais números (faturamento, lucro, prejuízo com desperdício, produto
mais vendido, dia e horário de pico, porcentagem do fiado em atraso, erro da previsão).

Tudo é salvo na pasta `/content/resultados` do Colab:
- `gold_*.csv` — cada tabela Gold, que abre no Excel;
- `cantina.db` — o banco de dados com todas as tabelas;
- `resultados_cantina.zip` — tudo compactado (mude `BAIXAR_RESULTADOS = True` para baixar).

> Atenção: os arquivos do Colab são apagados quando a sessão fecha. Baixe o `.zip` se quiser guardar.

---

## 5. Relação com as aulas da disciplina

| Aula | Conteúdo | Onde aparece no projeto |
|---|---|---|
| 05 | Aprendizado supervisionado — Classificação | Parte 6: previsão de atraso do fiado |
| 06 | Aprendizado supervisionado — Regressão | Parte 5: previsão de vendas e sugestão de produção |
| 08 | Hadoop (MapReduce, Hive, Sqoop, YARN, Pig, HBase) | Parte 4: MapReduce, Hive e Sqoop |
| 09 | Spark e Structured Streaming | Parte 7: Spark SQL e painel ao vivo |

Os modelos seguem a mesma estrutura das aulas (preenchimento de vazios, padronização dos números,
transformação de categorias em números e Random Forest, tudo dentro de uma *pipeline*), com dois
ajustes para ficarem mais próximos da vida real: na regressão, o teste é feito nos dias mais
recentes, e na classificação, os atrasos recebem mais peso.

## 6. Pequeno glossário

| Termo | Significado simples |
|---|---|
| **Big Data** | Dados em volume, velocidade ou variedade grandes demais para ferramentas comuns |
| **Pipeline** | Sequência de etapas automáticas, como uma linha de montagem |
| **Modelo** | Programa que aprende padrões com exemplos do passado para prever o futuro |
| **Treino / teste** | Parte dos dados usada para ensinar o modelo / parte guardada para conferir se ele aprendeu |
| **Feature (pista)** | Informação que o modelo usa para prever (ex.: temperatura) |
| **Alvo** | O que o modelo tenta prever (ex.: itens vendidos) |
| **SQL** | Linguagem para fazer perguntas a bancos de dados |
| **Streaming** | Processar dados à medida que chegam, em vez de esperar juntar tudo |
| **Correlação** | Número de -1 a 1 que mostra se duas coisas sobem juntas (positivo) ou em sentidos opostos (negativo) |
| **Ticket médio** | Valor médio gasto por compra |
