# P.I-Data-Science

Projeto Integrador — Grupo 3 (Data Science): pipeline de dados para uma cantina escolar parceira,
das fontes brutas até tabelas prontas para análise (**Bronze → Silver → Gold**).

Como a empresa parceira trabalha com dados sensíveis, o projeto usa **dados fictícios**. Um gerador
em Python simula a operação diária da cantina e roda em uma máquina virtual provisionada com
OpenTofu e configurada com Ansible. Ao final de cada execução, os dados atualizados são enviados
para este repositório.

```text
OpenTofu ──▶ VM (Libvirt/QEMU + cloud-init) ──▶ Ansible ──▶ cron ──▶ gerador ──▶ dados/ ──▶ GitHub
```

## Sumário

- [Estrutura do repositório](#estrutura-do-repositório)
- [Tecnologias](#tecnologias)
- [Gerador de dados](#gerador-de-dados)
  - [Execução local](#execução-local)
  - [O que acontece em cada execução](#o-que-acontece-em-cada-execução)
  - [Envio ao GitHub](#envio-ao-github)
  - [Arquivos gerados](#arquivos-gerados)
  - [Coerência dos dados](#coerência-dos-dados)
  - [Inconsistências simuladas](#inconsistências-simuladas)
- [Infraestrutura (VM)](#infraestrutura-vm)
- [Observações e limitações](#observações-e-limitações)

## Estrutura do repositório

```text
P.I-Data-Science/
├── DOCS/
│   └── especificacao_dados_pipeline_cantina.pdf   # especificação das fontes e do pipeline
├── dados/
│   └── bronze/                  # dados brutos gerados (atualizados pelo gerador)
├── gerador_dados/
│   ├── gerar_dados.py           # ponto de entrada (linha de comando)
│   ├── requirements.txt
│   └── gerador/
│       ├── config.py            # produtos, nomes, clima médio, inflação média...
│       ├── mundo.py             # "mundo real" simulado de um ano
│       ├── historico.py         # lê os históricos para saber até onde o gerador chegou
│       ├── github.py            # commit e envio dos dados ao GitHub
│       ├── vendas.py            # 1.1 Vendas
│       ├── devedores.py         # 1.2 Devedores
│       ├── cardapio.py          # 1.3 Cardápio de Produtos
│       ├── perdas.py            # 1.4 Perdas/Desperdício
│       ├── calendario.py        # 1.5 Calendário Escolar
│       ├── clima.py             # 1.6 Clima e Temperatura
│       ├── alunos.py            # 1.7 Turmas e Alunos
│       ├── inflacao.py          # 1.8 Índice de Inflação
│       └── utils.py
├── infraestrutura/
│   ├── main.tf                  # VMs com OpenTofu + Libvirt
│   ├── cloud_init.cfg           # usuário e chave SSH das VMs
│   └── ansible/
│       ├── inventory.ini
│       └── playbook.yml         # prepara Python e ambiente virtual na VM
├── .gitignore
└── README.md
```

## Tecnologias

| Área | Ferramentas |
|---|---|
| Dados | Python 3.10+, OpenPyXL |
| Infraestrutura | Ubuntu Server 24.04, OpenTofu, Libvirt/QEMU, cloud-init |
| Configuração e acesso | Ansible, SSH |
| Versionamento | Git / GitHub |

## Gerador de dados

O gerador produz as 8 fontes descritas na seção 1 da [especificação](DOCS/especificacao_dados_pipeline_cantina.pdf),
cada uma no seu formato original, organizadas como a camada **Bronze** em `dados/bronze/<fonte>/`.

Ele foi feito para **rodar 1 ou 2 vezes por dia** e simula a cantina em tempo real: cada execução
gera apenas dados **do dia atual**, sem nada retroativo. A data e a hora usadas são sempre as de
Brasília (`America/Sao_Paulo`), mesmo que o relógio da máquina esteja em UTC.

### Execução local

```bash
cd gerador_dados
pip install -r requirements.txt
python gerar_dados.py              # gera os dados de hoje e envia ao GitHub
python gerar_dados.py --sem-github # gera os dados sem enviar (ficam só no computador)
```

| Opção | Padrão | Descrição |
|---|---|---|
| `--seed` | `42` | Semente aleatória (mesma semente = mesmos dados) |
| `--taxa-falhas` | `0.03` | Proporção aproximada de registros com falha |
| `--sem-falhas` | — | Gera os dados sem falhas propositais |
| `--min-alunos` / `--max-alunos` | `20` / `28` | Alunos por turma |
| `--saida` | `dados/` | Pasta dos dados |
| `--dia-completo` | — | Registra todas as vendas de hoje e fecha o dia, sem esperar o horário |
| `--manter-lote` | — | Não apaga o arquivo do lote depois de consolidá-lo no histórico |
| `--sem-github` | — | Não envia os dados ao GitHub |
| `--remoto` / `--branch` | `origin` / branch atual | Destino do envio |
| `--agora` | horário atual | Simula a data/hora da execução, ex.: `"2026-09-24 19:00"` (só para testes) |

> Use sempre a mesma `--seed` (e o mesmo número de alunos por turma) para uma mesma pasta de
> dados: as vendas de cada dia são recalculadas a partir desses parâmetros, e trocá-los no meio do
> caminho gera dados que não conversam com o histórico.

### O que acontece em cada execução

1. **Vendas do dia:** cada dia letivo tem entre **75 e 150 vendas**. O volume varia com o dia da
   semana, o clima, o início do mês e os eventos. A execução grava apenas as vendas que **já
   aconteceram até aquele horário** e ainda não foram registradas:
   - rodando às 13h, grava as vendas da manhã;
   - rodando às 19h, grava as da tarde;
   - uma nova execução no mesmo dia nunca duplica vendas nem passa do total do dia.
2. **Lote → histórico:** as vendas da execução vão para um arquivo de lote
   (`gerador_dados/lotes/`). O conteúdo dele é acrescentado ao fim de
   `dados/bronze/vendas/historico_vendas.xlsx` e o lote é **apagado** para economizar espaço.
3. **Fechamento do dia:** na primeira execução depois do fim do expediente (18h30; 13h em dias com
   aula só de manhã), as **perdas** do dia são geradas e seguem o mesmo caminho até
   `historico_perdas.xlsx`.
4. **Devedores:** a planilha é recalculada a partir das vendas "Fiado" registradas, com o status
   do dia.
5. **Fontes de referência:** calendário, turmas/alunos, cardápio, clima e inflação são publicados
   com o que já existe na data de hoje. Por exemplo, o clima vai só até hoje e o cardápio do
   2º semestre só aparece depois que entra em vigor.
6. **Envio ao GitHub:** os arquivos que mudaram são enviados (veja abaixo).

Em fins de semana, feriados e férias não há vendas.

**Não existe arquivo de estado.** O gerador descobre até onde já chegou lendo os próprios
históricos: o maior `id_venda` de cada dia indica quantas vendas daquele dia já foram registradas.
Por isso qualquer máquina com uma cópia de `dados/`, como um clone do repositório, continua a
sequência de onde ela parou.

### Envio ao GitHub

Ao terminar, o gerador faz um commit **somente com os arquivos de `dados/` que mudaram** e o envia
para a branch atual do repositório.

- **Nada mudou:** nada é enviado. As planilhas só são regravadas quando o conteúdo muda, então
  uma execução sem novidades não gera commit.
- **Algo mudou:** apenas os arquivos alterados entram no commit, como o histórico de vendas, os
  devedores ou o clima. Os demais arquivos continuam como estão.
- **Envio falhou** (sem internet, sem credenciais ou pasta fora de um repositório git): o
  gerador não para. Os dados continuam salvos no computador, o commit fica guardado localmente e
  é enviado na próxima execução que conseguir.
- **Alguém alterou o repositório nesse meio-tempo:** o gerador integra essas alterações
  (`rebase`) antes de enviar.

Para o envio funcionar, a pasta do projeto precisa ser um **clone git** com permissão de escrita
no GitHub. Na VM, recomenda-se uma *deploy key* (veja o [passo 5 da infraestrutura](#5-clonar-o-repositório-na-vm-com-permissão-de-envio)).
Se o git não tiver nome e e-mail configurados, os commits saem como "Gerador de dados da cantina".

### Arquivos gerados

| Fonte (PDF) | Formato | Arquivo em `dados/bronze/` | Atualização |
|---|---|---|---|
| 1.1 Vendas | Excel | `vendas/historico_vendas.xlsx` | acumulativa (um lote por execução) |
| 1.2 Devedores | Excel | `devedores/devedores_atualizado.xlsx` | recalculada a cada execução |
| 1.3 Cardápio | Excel | `cardapio/cardapio_vigencia_AAAA-MM-DD.xlsx` | uma por versão já vigente |
| 1.4 Perdas | Excel | `perdas/historico_perdas.xlsx` | acumulativa (uma vez por dia, no fechamento) |
| 1.5 Calendário Escolar | JSON | `calendario_escolar/calendario_escolar_AAAA.json` | ano inteiro, publicado no início do ano |
| 1.6 Clima | JSON | `clima/clima_AAAA.json` | de 01/01 até hoje |
| 1.7 Turmas e Alunos | JSON (aninhado) | `turmas_alunos/turmas_alunos_AAAA.json` | fixa no ano |
| 1.8 Inflação | JSON | `inflacao/inflacao_AAAA.json` | meses já publicados (defasagem de 2 meses) |

A fonte "Frequência (CSV externo/SED)", citada no fluxo do pipeline, não é gerada porque a
especificação não define seu schema.

### Coerência dos dados

Primeiro o gerador simula o que "realmente aconteceu". Só depois publica os arquivos, e é nessa
etapa que entram as falhas. Fora as falhas propositais, os dados são consistentes entre si:

- **Idade × série:** a data de nascimento segue a regra de corte de 31/03 (6 anos no 1º ano do EF,
  17 anos na 3ª série do EM). Cerca de 6% dos alunos são um ano mais velhos (repetentes).
- **Turnos e horários:** o EF I tem turmas de manhã e à tarde; o EF II e o EM estudam de manhã.
  As vendas acontecem só no turno do aluno, na entrada, no intervalo ou na saída.
- **Calendário:** não há vendas nem perdas em feriados, férias, recessos, fins de semana e
  planejamento. A Quarta-feira de Cinzas só tem aula à tarde e os conselhos de classe só de manhã.
  A Festa Junina cai num sábado letivo, com movimento maior.
- **Restrições alimentares:** um aluno celíaco não compra coxinha, um intolerante à lactose não
  compra pão de queijo, e assim por diante. Café e açaí só são comprados a partir de certas séries.
- **Clima:** a temperatura acompanha as estações, com verão quente e chuvoso e inverno frio e seco.
  Chuva sempre vem com precipitação > 0 e a máxima nunca fica abaixo da média. Dias quentes vendem
  mais bebidas geladas e picolé, dias frios vendem mais chocolate quente e misto quente, e a chuva
  reduz a presença dos alunos.
- **Preços × inflação:** o cardápio do 2º semestre é reajustado pela inflação acumulada de cada
  categoria, usando só os meses já publicados na data da troca. As vendas usam o preço vigente na
  data e `valor_total = quantidade × valor_unitario`.
- **Devedores:** as dívidas vêm das vendas "Fiado", uma por aluno por dia. O status (Quitado /
  Em aberto / Atrasado) é calculado na data da execução e só avança com o tempo: a data de
  quitação de cada débito é fixa e depende do perfil do responsável.
- **Perdas:** a produção de perecíveis segue a média de vendas dos últimos dias letivos, e o que
  sobra vira perda. Dias atípicos, como os de chuva ou calor, geram mais desperdício.

### Inconsistências simuladas

Todos os tipos de inconsistência previstos na especificação, além de erros humanos evidentes:

| Fonte | Falhas inseridas |
|---|---|
| Vendas | `forma_pagamento` vazia ou digitada errada; `valor_total` diferente do cálculo; linhas duplicadas e `id_venda` repetido; datas em formatos diferentes (lotes inteiros em texto `dd/mm/aaaa` e linhas em `aaaa-mm-dd`); preços negativos; preço sem a vírgula (450 em vez de 4,50); quantidade 0, negativa ou absurda; produto inexistente no cardápio; `id_aluno` vazio |
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

Os IDs têm formatos diferentes entre as fontes, como previsto na especificação: `id_aluno` é
`"ALU01234"` nas vendas e `1234` nos devedores e alunos, e `id_produto` é `"P012"` nas vendas e
`12` no cardápio e nas perdas. Esse mapeamento de chaves fica a cargo da camada Silver.

## Infraestrutura (VM)

O OpenTofu cria duas VMs Ubuntu (`devops-1` e `devops-2`) com Libvirt/QEMU e cloud-init. O
Ansible prepara a `devops-1`, onde o gerador roda.

### Pré-requisitos

Linux com virtualização habilitada e o **OpenTofu** instalado, além de:

```bash
sudo apt update
sudo apt install -y git qemu-kvm libvirt-daemon-system libvirt-clients python3 python3-pip python3-venv ansible
sudo usermod -aG libvirt $USER
sudo usermod -aG kvm $USER
```

### 1. Clonar o projeto e criar a chave SSH das VMs

```bash
git clone https://github.com/PedroFreitasDev/P.I-Data-Science.git
cd P.I-Data-Science
ssh-keygen -t ed25519 -f ~/.ssh/devops_lab
```

A chave privada nunca deve ser enviada ao GitHub.

### 2. Provisionar as VMs

```bash
cd infraestrutura
tofu init
tofu plan
tofu apply
sudo virsh list   # confere as VMs
tofu output       # mostra os IPs
```

### 3. Testar o acesso SSH

```bash
ssh -i ~/.ssh/devops_lab aluno@IP_DA_VM
```

### 4. Configurar a VM com Ansible

Se os IPs mudaram, atualize `infraestrutura/ansible/inventory.ini` antes de rodar:

```bash
cd infraestrutura/ansible
ansible -i inventory.ini servidores -m ping
ansible-playbook -i inventory.ini playbook.yml
```

O playbook instala o Python e as dependências, cria `/home/aluno/projeto-data-science` e o
ambiente virtual do gerador.

### 5. Clonar o repositório na VM (com permissão de envio)

Para que o gerador consiga enviar os dados, o projeto na VM precisa ser um clone git com permissão
de escrita. A forma mais segura é uma **deploy key**, uma chave SSH que dá acesso apenas a este
repositório.

Na VM:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/github_cantina -N ""
cat ~/.ssh/github_cantina.pub
```

No GitHub, em **Settings → Deploy keys → Add deploy key**, cole a chave pública e marque
**Allow write access**. Depois, ainda na VM:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/github_cantina
EOF

# A pasta já existe (criada pelo Ansible), por isso não dá para usar git clone direto
cd /home/aluno/projeto-data-science
git init
git remote add origin git@github.com:PedroFreitasDev/P.I-Data-Science.git
git fetch origin main
git checkout -f -t origin/main
git config user.name  "VM devops-1"
git config user.email "devops-1@users.noreply.github.com"

gerador_dados/.venv/bin/pip install -r gerador_dados/requirements.txt
```

### 6. Executar e agendar o gerador

Teste manual:

```bash
cd /home/aluno/projeto-data-science/gerador_dados
.venv/bin/python gerar_dados.py
```

Agendamento com `crontab -e`: uma execução depois do almoço e outra depois do fechamento. Os
horários do cron seguem o fuso da VM. Se ela estiver em UTC, use `0 16` e `0 22`.

```cron
0 13 * * 1-6  cd /home/aluno/projeto-data-science/gerador_dados && .venv/bin/python gerar_dados.py >> /home/aluno/gerador.log 2>&1
0 19 * * 1-6  cd /home/aluno/projeto-data-science/gerador_dados && .venv/bin/python gerar_dados.py >> /home/aluno/gerador.log 2>&1
```

Se houver só uma execução por dia, agende-a depois das 18h30 para registrar o dia inteiro e as
perdas.

## Observações e limitações

- Não versione chaves SSH privadas, `*.tfstate` nem discos `.qcow2`. O `.gitignore` já cobre
  esses arquivos. Os dados em `dados/` são versionados de propósito.
- Os IPs das VMs podem mudar quando elas são recriadas. Confira com `tofu output`.
- Se nenhuma execução acontecer depois do fechamento de um dia, as vendas que faltavam daquele dia
  e as perdas dele não são registradas, porque o gerador nunca grava nada retroativo.
- A cada ano as turmas são geradas de novo, com IDs de aluno começando em 1001. Não há progressão
  de série entre anos, então um mesmo ID pode representar alunos diferentes em anos diferentes.
