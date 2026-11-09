#!/usr/bin/env Rscript
# =============================================================================
#  Limpeza dos dados da cantina: camada Bronze -> camada Silver
# -----------------------------------------------------------------------------
#  Lê os arquivos brutos de dados/bronze/ (do jeito que o gerador publica),
#  corrige as inconsistências previstas na especificação e grava uma tabela
#  limpa por fonte em dados/silver/, no formato que o notebook
#  Projeto_Cantina_BigData.ipynb espera.
#
#  Ciclo completo:  gerador (Python) -> limpeza (este script, R) -> notebook (Gold)
#
#  Etapas da Silver (seção 2.4 da especificação):
#    padronização de schema -> deduplicação -> mapeamento de chaves ->
#    tratamento de nulos/outliers -> conciliação temporal
#
#  Como rodar, na raiz do projeto:
#      Rscript limpeza_dados/limpeza_silver.R
#  ou informando a raiz do projeto:
#      Rscript limpeza_dados/limpeza_silver.R "C:/caminho/P.I-Data-Science"
#
#  Saída em dados/silver/:
#      vendas.csv, devedores.csv, cardapio.csv, perdas.csv, calendario.csv,
#      clima.csv, alunos.csv, inflacao.csv e relatorio_limpeza.csv
#      (o relatório lista cada problema encontrado, quantas linhas e o que foi feito)
# =============================================================================


# ---- 0. Pacotes e configuração ----------------------------------------------

pacotes <- c("readxl", "jsonlite", "dplyr", "tidyr", "stringr", "lubridate", "readr", "purrr")
faltando <- pacotes[!vapply(pacotes, requireNamespace, logical(1), quietly = TRUE)]
if (length(faltando) > 0) {
  message("Instalando pacotes: ", paste(faltando, collapse = ", "))
  install.packages(faltando, repos = "https://cloud.r-project.org")
}
suppressPackageStartupMessages(invisible(lapply(pacotes, library, character.only = TRUE)))

# Limites usados para reconhecer erros evidentes
PRECO_MAXIMO      <- 50    # R$ por item; acima disso é preço sem a vírgula (450 -> 4,50)
QTD_MAXIMA        <- 10    # unidades do mesmo produto numa venda
DIVIDA_MAXIMA     <- 150   # R$ de fiado de um aluno num dia; acima disso é valor sem a vírgula
TEMP_MIN          <- 0     # °C (São Paulo)
TEMP_MAX          <- 45
INFLACAO_MAX      <- 5     # % ao mês; acima disso é índice sem a vírgula
DIAS_PARA_ATRASO  <- 30    # fiado em aberto há mais de 30 dias = "Atrasado"
IDADE_MIN         <- 4     # idade aceitável de um aluno no ano letivo
IDADE_MAX         <- 25
DEFASAGEM_INFLACAO_MESES <- 2

CATEGORIAS <- c("Salgados", "Lanches Naturais", "Bebidas", "Doces", "Sobremesas")
# A "API" de inflação usa outros nomes para algumas categorias: de-para para o cardápio
CATEGORIAS_API  <- c(CATEGORIAS, "Lanches", "Bebidas não alcoólicas", "Sobremesas e sorvetes")
CATEGORIAS_PARA <- c(CATEGORIAS, "Lanches Naturais", "Bebidas", "Sobremesas")
TIPOS_DIA <- c("letivo", "sabado_letivo", "feriado", "fim_de_semana", "ferias", "recesso",
               "planejamento")

# Pastas
args <- commandArgs(trailingOnly = TRUE)
if (length(args) >= 1) {
  RAIZ <- args[1]
} else {
  candidatos <- c(".", "..")
  RAIZ <- candidatos[dir.exists(file.path(candidatos, "dados", "bronze"))][1]
  if (is.na(RAIZ)) {
    stop("Não encontrei dados/bronze. Rode na raiz do projeto ou informe o caminho:\n",
         "  Rscript limpeza_dados/limpeza_silver.R <raiz do projeto>")
  }
}
BRONZE <- file.path(RAIZ, "dados", "bronze")
SILVER <- file.path(RAIZ, "dados", "silver")
dir.create(SILVER, recursive = TRUE, showWarnings = FALSE)


# ---- 1. Funções auxiliares --------------------------------------------------

# Relatório do que foi corrigido (vira dados/silver/relatorio_limpeza.csv)
relatorio <- tibble(tabela = character(), problema = character(),
                    linhas = integer(), acao = character())
registrar <- function(tabela, problema, linhas, acao) {
  linhas <- sum(linhas, na.rm = TRUE)  # aceita uma contagem ou um vetor lógico
  if (linhas > 0) {
    relatorio <<- add_row(relatorio, tabela = tabela, problema = problema,
                          linhas = as.integer(linhas), acao = acao)
  }
  invisible(linhas)
}

`%||%` <- function(a, b) if (is.null(a)) b else a

# Campos de JSON (lidos com simplifyVector = FALSE): ausente/null -> NA
campo_txt <- function(x) if (is.null(x) || length(x) == 0) NA_character_ else as.character(x[[1]])
campo_num <- function(x) if (is.null(x) || length(x) == 0) NA_real_ else suppressWarnings(as.numeric(x[[1]]))

# Células de Excel lidas com col_types = "list": cada célula mantém o tipo original
# (número, texto ou data), o que permite enxergar datas digitadas como texto.
celula_txt <- function(col) {
  vapply(col, function(v) {
    if (length(v) == 0 || is.na(v[1])) return(NA_character_)
    if (inherits(v, "POSIXt")) return(format(v, "%Y-%m-%d %H:%M:%S", tz = "UTC"))
    if (inherits(v, "Date")) return(format(v, "%Y-%m-%d"))
    if (is.numeric(v)) return(format(v[1], scientific = FALSE, trim = TRUE, digits = 15))
    as.character(v[1])
  }, character(1), USE.NAMES = FALSE)
}
celula_num <- function(col) suppressWarnings(as.numeric(str_replace(celula_txt(col), ",", ".")))
celula_eh_texto <- function(col) vapply(col, is.character, logical(1), USE.NAMES = FALSE)

# Texto sem acento, minúsculo e sem espaços sobrando (para comparar)
chave <- function(x) str_squish(str_to_lower(stringi::stri_trans_general(x, "Latin-ASCII")))

# "ALU01234" -> 1234 ; "P012" -> 12 ; "001234" -> 1234
so_digitos <- function(x) suppressWarnings(as.integer(str_extract(x, "\\d+")))

# Datas e horas em vários formatos -> POSIXct (horário de Brasília guardado como "UTC" ingênuo)
texto_para_datahora <- function(x) {
  x <- str_trim(x)
  saida <- .POSIXct(rep(NA_real_, length(x)), tz = "UTC")
  iso <- str_detect(x, "^\\d{4}-\\d{1,2}-\\d{1,2}") %in% TRUE   # aaaa-mm-dd hh:mm[:ss]
  br  <- str_detect(x, "^\\d{1,2}/\\d{1,2}/\\d{4}") %in% TRUE   # dd/mm/aaaa hh:mm[:ss]
  saida[iso] <- suppressWarnings(ymd_hms(x[iso], tz = "UTC", truncated = 3))
  saida[br]  <- suppressWarnings(dmy_hms(x[br], tz = "UTC", truncated = 3))
  saida
}

# Datas em vários formatos -> Date (datas impossíveis viram NA)
texto_para_data <- function(x) {
  x <- str_trim(x)
  saida <- as.Date(rep(NA_character_, length(x)))
  formatos <- list(c("^\\d{4}-\\d{2}-\\d{2}", "%Y-%m-%d"),
                   c("^\\d{4}/\\d{2}/\\d{2}", "%Y/%m/%d"),
                   c("^\\d{2}/\\d{2}/\\d{4}", "%d/%m/%Y"),
                   c("^\\d{2}-\\d{2}-\\d{2}$", "%d-%m-%y"))
  for (f in formatos) {
    m <- str_detect(x, f[1]) %in% TRUE
    saida[m] <- as.Date(substr(x[m], 1, 10), format = f[2])
  }
  saida
}

# Casa um texto digitado com a lista oficial: igual (ignorando caixa/acentos/espaços)
# ou começo do nome oficial (ex.: "Doce" -> "Doces"). Sem casamento único -> NA.
casar_por_prefixo <- function(x, referencia, rotulos = referencia) {
  ref <- chave(referencia)
  vapply(chave(x), function(k) {
    if (is.na(k) || nchar(k) < 3) return(NA_character_)
    achou <- unique(rotulos[ref == k])
    if (length(achou) == 0) achou <- unique(rotulos[startsWith(ref, k)])
    if (length(achou) == 1) achou else NA_character_
  }, character(1), USE.NAMES = FALSE)
}

# Versão do cardápio em vigor em cada data
vigencia_na_data <- function(datas, vigencias) {
  vigencias <- sort(unique(vigencias))
  i <- findInterval(as.numeric(datas), as.numeric(vigencias))
  saida <- as.Date(rep(NA_character_, length(datas)))
  ok <- !is.na(i) & i > 0
  saida[ok] <- vigencias[i[ok]]
  saida
}

# Feriados nacionais (mesma regra usada pelo gerador)
pascoa <- function(ano) {
  a <- ano %% 19; b <- ano %/% 100; cc <- ano %% 100; d <- b %/% 4; e <- b %% 4
  f <- (b + 8) %/% 25; g <- (b - f + 1) %/% 3; h <- (19 * a + b - d - g + 15) %% 30
  i <- cc %/% 4; k <- cc %% 4; l <- (32 + 2 * e + 2 * i - h - k) %% 7
  m <- (a + 11 * h + 22 * l) %/% 451
  mes <- (h + l - 7 * m + 114) %/% 31
  dia <- ((h + l - 7 * m + 114) %% 31) + 1
  as.Date(sprintf("%d-%02d-%02d", ano, mes, dia))
}
feriados_nacionais <- function(ano) {
  tibble(
    data = c(as.Date(paste0(ano, "-01-01")), pascoa(ano) - 2,
             as.Date(paste0(ano, c("-04-21", "-05-01", "-09-07", "-10-12", "-11-02",
                                   "-11-15", "-11-20", "-12-25")))),
    nome_feriado = c("Confraternização Universal", "Sexta-feira Santa", "Tiradentes",
                     "Dia do Trabalho", "Independência do Brasil", "Nossa Senhora Aparecida",
                     "Finados", "Proclamação da República",
                     "Dia Nacional de Zumbi e da Consciência Negra", "Natal"))
}

# Agregações que devolvem NA (e não NaN/-Inf) quando tudo é NA
media_na <- function(x) if (all(is.na(x))) NA_real_ else mean(x, na.rm = TRUE)
max_na   <- function(x) if (all(is.na(x))) NA_real_ else max(x, na.rm = TRUE)
soma_na  <- function(x) if (all(is.na(x))) NA_real_ else sum(x, na.rm = TRUE)
moda     <- function(x) {
  x <- x[!is.na(x)]
  if (length(x) == 0) NA_character_ else names(which.max(table(x)))
}
interpolar <- function(x) {
  if (sum(!is.na(x)) < 2) return(x)
  approx(seq_along(x), x, xout = seq_along(x), rule = 2)$y
}

listar <- function(pasta, padrao) {
  arqs <- list.files(file.path(BRONZE, pasta), padrao, full.names = TRUE)
  if (length(arqs) == 0) stop("Nenhum arquivo encontrado em ", file.path(BRONZE, pasta))
  arqs
}


# ---- 2. Cardápio ------------------------------------------------------------
# Vem primeiro porque vendas e perdas dependem dele (produtos válidos e custos).
message("Limpando cardápio...")

cardapio <- map_dfr(listar("cardapio", "^cardapio_vigencia_\\d{4}-\\d{2}-\\d{2}\\.xlsx$"), function(arq) {
  b <- read_excel(arq, col_types = "list")
  tibble(vigencia        = as.Date(str_extract(basename(arq), "\\d{4}-\\d{2}-\\d{2}")),
         id_produto      = so_digitos(celula_txt(b$id_produto)),
         nome_bruto      = celula_txt(b$nome_produto),
         categoria_bruta = celula_txt(b$categoria),
         preco_venda     = celula_num(b$preco_venda),
         custo_unitario  = celula_num(b$custo_unitario))
}) |>
  filter(!is.na(id_produto)) |>
  distinct(vigencia, id_produto, .keep_all = TRUE)

# Nome: espaços sobrando ou tudo em maiúsculas/minúsculas. O nome correto é
# copiado da outra versão do cardápio; se não houver, padroniza a caixa.
cardapio <- cardapio |>
  mutate(nome_produto = str_squish(nome_bruto),
         nome_fora_padrao = (nome_produto != nome_bruto |
                               nome_produto == str_to_upper(nome_produto) |
                               nome_produto == str_to_lower(nome_produto)) %in% TRUE)
nomes_oficiais <- cardapio |>
  filter(!nome_fora_padrao, !is.na(nome_produto)) |>
  transmute(id_produto, nome_oficial = nome_produto) |>
  distinct(id_produto, .keep_all = TRUE)
cardapio <- cardapio |>
  left_join(nomes_oficiais, by = "id_produto") |>
  mutate(nome_produto = if_else(nome_fora_padrao,
                                coalesce(nome_oficial, str_to_sentence(str_to_lower(nome_produto), locale = "pt")),
                                nome_produto))
registrar("cardapio", "nome do produto fora do padrão (caixa alta ou espaços)",
          cardapio$nome_fora_padrao, "corrigido pela outra versão do cardápio ou caixa padronizada")

# Categoria: minúsculas, maiúsculas ou cortada ("Doce", "SALGADOS")
cardapio <- cardapio |>
  mutate(categoria = casar_por_prefixo(categoria_bruta, CATEGORIAS)) |>
  group_by(id_produto) |>
  mutate(categoria = coalesce(categoria, first(na.omit(categoria)))) |>
  ungroup()
registrar("cardapio", "categoria fora do padrão",
          (cardapio$categoria != cardapio$categoria_bruta) %in% TRUE, "padronizada")

# Preço sem a vírgula (450 em vez de 4,50) e custo negativo
cardapio <- cardapio |>
  mutate(preco_sem_virgula = (abs(preco_venda) > PRECO_MAXIMO) %in% TRUE,
         preco_venda = round(if_else(preco_sem_virgula, abs(preco_venda) / 100, abs(preco_venda)), 2),
         custo_negativo = (custo_unitario < 0) %in% TRUE,
         custo_unitario = abs(custo_unitario))
registrar("cardapio", "preço absurdo (digitado sem a vírgula)", cardapio$preco_sem_virgula, "dividido por 100")
registrar("cardapio", "custo_unitario negativo", cardapio$custo_negativo, "sinal corrigido")

# Custo ausente: estimado pela margem típica (custo/preço) da categoria naquela versão
cardapio <- cardapio |>
  mutate(custo_imputado = is.na(custo_unitario)) |>
  group_by(vigencia, categoria) |>
  mutate(proporcao_custo = median(custo_unitario / preco_venda, na.rm = TRUE),
         custo_unitario = if_else(custo_imputado, round(preco_venda * proporcao_custo, 2), custo_unitario)) |>
  ungroup()
registrar("cardapio", "custo_unitario ausente", cardapio$custo_imputado,
          "estimado pela proporção custo/preço da categoria (coluna custo_imputado = TRUE)")

# Preço desatualizado em relação à inflação: igual ao da versão anterior do cardápio
cardapio <- cardapio |>
  arrange(id_produto, vigencia) |>
  group_by(id_produto) |>
  mutate(preco_sem_reajuste = (abs(preco_venda - lag(preco_venda)) < 0.005) %in% TRUE) |>
  ungroup()
registrar("cardapio", "preço não reajustado na troca de cardápio (desatualizado em relação à inflação)",
          cardapio$preco_sem_reajuste, "mantido e sinalizado na coluna preco_sem_reajuste")

cardapio <- cardapio |>
  select(id_produto, nome_produto, categoria, preco_venda, custo_unitario,
         vigencia, custo_imputado, preco_sem_reajuste) |>
  arrange(vigencia, id_produto)   # o notebook fica com a versão mais recente de cada produto


# ---- 3. Vendas --------------------------------------------------------------
message("Limpando vendas...")

vb <- read_excel(file.path(BRONZE, "vendas", "historico_vendas.xlsx"), col_types = "list")
vendas <- tibble(id_venda        = as.integer(celula_num(vb$id_venda)),
                 data_hora_bruta = celula_txt(vb$data_hora),
                 data_em_texto   = celula_eh_texto(vb$data_hora),
                 id_aluno_bruto  = celula_txt(vb$id_aluno),
                 id_produto      = so_digitos(celula_txt(vb$id_produto)),
                 quantidade      = celula_num(vb$quantidade),
                 valor_unitario  = celula_num(vb$valor_unitario),
                 valor_total     = celula_num(vb$valor_total),
                 forma_bruta     = celula_txt(vb$forma_pagamento))

# 3.1 Deduplicação: linhas idênticas
duplicada <- duplicated(vendas)
registrar("vendas", "linha duplicada", duplicada, "removida")
vendas <- vendas[!duplicada, ]

# 3.2 id_venda repetido em vendas diferentes. Os ids são sequenciais, então o id
# certo da linha repetida é o seguinte (id + 1), que ficou "faltando" na sequência.
repetido <- duplicated(vendas$id_venda) & !is.na(vendas$id_venda)
usados <- vendas$id_venda
for (i in which(repetido)) {
  novo <- vendas$id_venda[i] + 1L
  if (novo %in% usados) novo <- max(usados, na.rm = TRUE) + 1L
  vendas$id_venda[i] <- novo
  usados <- c(usados, novo)
}
registrar("vendas", "id_venda repetido em vendas diferentes", repetido, "renumerado com o id que faltava na sequência")

# 3.3 Datas: lotes inteiros em texto dd/mm/aaaa e linhas soltas em aaaa-mm-dd
vendas <- vendas |> mutate(data_hora = texto_para_datahora(data_hora_bruta))
registrar("vendas", "data digitada como texto (dd/mm/aaaa ou aaaa-mm-dd)",
          vendas$data_em_texto & !is.na(vendas$data_hora), "convertida para data/hora")
registrar("vendas", "data/hora ilegível", is.na(vendas$data_hora), "removida")
vendas <- filter(vendas, !is.na(data_hora))

# 3.4 Mapeamento de chaves: "ALU01234" -> 1234 e "P012" -> 12 (formato das outras tabelas)
vendas <- vendas |> mutate(id_aluno = so_digitos(id_aluno_bruto))
registrar("vendas", "id_aluno/id_produto em formato texto (ALU01234 / P012)", nrow(vendas),
          "convertidos para número, como em alunos, devedores e cardápio")
registrar("vendas", "id_aluno vazio", is.na(vendas$id_aluno),
          "mantida (entra no faturamento, mas fica sem turma)")

produto_inexistente <- !(vendas$id_produto %in% cardapio$id_produto)
registrar("vendas", "produto inexistente no cardápio (P999, P000...)", produto_inexistente, "removida")
vendas <- vendas[!produto_inexistente, ]

# 3.5 Valores: sinal trocado, preço sem a vírgula, quantidade inválida e total divergente
vendas <- vendas |>
  mutate(sinal_negativo = (valor_unitario < 0 | valor_total < 0) %in% TRUE,
         valor_unitario = abs(valor_unitario),
         valor_total = abs(valor_total),
         sem_virgula = (valor_unitario > PRECO_MAXIMO) %in% TRUE,
         valor_unitario = if_else(sem_virgula, valor_unitario / 100, valor_unitario))
registrar("vendas", "preço/valor negativo", vendas$sinal_negativo, "sinal corrigido")
registrar("vendas", "valor_unitario sem a vírgula (450 em vez de 4,50)", vendas$sem_virgula, "dividido por 100")

# Quantidade 0, negativa ou absurda: recuperada pela conta valor_total / valor_unitario
vendas <- vendas |>
  mutate(qtd_invalida = !(quantidade %in% 1:QTD_MAXIMA),
         pela_conta = valor_total / valor_unitario,
         qtd_pela_conta = if_else(abs(pela_conta - round(pela_conta)) < 0.01 &
                                    round(pela_conta) %in% 1:QTD_MAXIMA,
                                  round(pela_conta), NA_real_),
         quantidade = case_when(!qtd_invalida ~ quantidade,
                                !is.na(qtd_pela_conta) ~ qtd_pela_conta,
                                abs(quantidade) %in% 1:QTD_MAXIMA ~ abs(quantidade),
                                TRUE ~ NA_real_))
registrar("vendas", "quantidade zerada, negativa ou absurda", vendas$qtd_invalida & !is.na(vendas$quantidade),
          "recuperada por valor_total / valor_unitario")
registrar("vendas", "quantidade inválida sem como recuperar", is.na(vendas$quantidade), "removida")
vendas <- filter(vendas, !is.na(quantidade))

vendas <- vendas |>
  mutate(total_calculado = round(quantidade * valor_unitario, 2),
         total_divergente = (abs(valor_total - total_calculado) > 0.009) %in% TRUE | is.na(valor_total),
         valor_total = total_calculado)
registrar("vendas", "valor_total diferente de quantidade × valor_unitario", vendas$total_divergente, "recalculado")

# 3.6 Forma de pagamento: grafias diferentes e vazios
vendas <- vendas |>
  mutate(forma_pagamento = {
    k <- chave(forma_bruta)
    case_when(str_detect(k, "^din") ~ "Dinheiro",
              str_detect(k, "pix") ~ "Pix",
              str_detect(k, "deb") ~ "Cartão de débito",
              str_detect(k, "cred") ~ "Cartão de crédito",
              str_detect(k, "fiad|anotad") ~ "Fiado",
              TRUE ~ NA_character_)
  })
registrar("vendas", "forma_pagamento digitada fora do padrão (pix, Dinhero, Anotado...)",
          !is.na(vendas$forma_bruta) & (vendas$forma_pagamento != vendas$forma_bruta) %in% TRUE, "padronizada")

# Vazio: os itens de uma mesma compra (mesmo aluno, segundos de diferença) têm a
# mesma forma de pagamento, então ela é copiada dos outros itens da compra.
preencher_unica <- function(f) {
  conhecidas <- unique(f[!is.na(f)])
  if (length(conhecidas) == 1) coalesce(f, conhecidas) else f
}
vendas <- vendas |>
  mutate(forma_faltava = is.na(forma_pagamento)) |>
  arrange(id_aluno, data_hora, id_venda) |>
  group_by(id_aluno) |>
  mutate(compra = cumsum(c(TRUE, diff(as.numeric(data_hora)) > 60))) |>
  group_by(id_aluno, compra) |>
  mutate(forma_pagamento = if (is.na(id_aluno[1])) forma_pagamento else preencher_unica(forma_pagamento)) |>
  ungroup()
registrar("vendas", "forma_pagamento vazia", vendas$forma_faltava & !is.na(vendas$forma_pagamento),
          "preenchida com a forma dos outros itens da mesma compra")
registrar("vendas", "forma_pagamento vazia sem como deduzir", is.na(vendas$forma_pagamento),
          "preenchida com 'Não informado'")
vendas <- vendas |> mutate(forma_pagamento = coalesce(forma_pagamento, "Não informado"))

# 3.7 Conciliação com o cardápio vigente: produtos descontinuados ainda vendidos (estoque)
vendas <- vendas |>
  mutate(vigencia = vigencia_na_data(as_date(data_hora), cardapio$vigencia),
         fora_cardapio_vigente = !(paste(id_produto, vigencia) %in% paste(cardapio$id_produto, cardapio$vigencia)))
registrar("vendas", "produto ausente do cardápio vigente (estoque remanescente de produto descontinuado)",
          vendas$fora_cardapio_vigente, "mantida e sinalizada em fora_cardapio_vigente")

vendas <- vendas |>
  transmute(id_venda, data_hora, id_aluno, id_produto,
            quantidade = as.integer(quantidade), valor_unitario = round(valor_unitario, 2),
            valor_total, forma_pagamento, fora_cardapio_vigente) |>
  arrange(id_venda)


# ---- 4. Turmas e alunos -----------------------------------------------------
message("Limpando turmas e alunos...")

alunos <- map_dfr(listar("turmas_alunos", "^turmas_alunos_\\d{4}\\.json$"), function(arq) {
  js <- fromJSON(arq, simplifyVector = FALSE)
  map_dfr(js$turmas, function(t) {
    if (length(t$alunos) == 0) return(NULL)
    tibble(turma           = campo_txt(t$turma),
           ano_letivo      = as.integer(campo_num(t$ano_letivo %||% js$ano_letivo)),
           turno_bruto     = campo_txt(t$turno),
           id_aluno_bruto  = map_chr(t$alunos, \(a) campo_txt(a$id_aluno)),
           nome_bruto      = map_chr(t$alunos, \(a) campo_txt(a$nome)),
           nasc_bruto      = map_chr(t$alunos, \(a) campo_txt(a$data_nascimento)),
           restricao_bruta = map_chr(t$alunos, \(a) campo_txt(a$restricao_alimentar)))
  })
})

# id_aluno em outro formato ("001234", "ALU01234", "1234" em texto)
alunos <- alunos |>
  mutate(id_aluno = so_digitos(id_aluno_bruto),
         id_fora_padrao = !str_detect(id_aluno_bruto, "^[1-9]\\d*$") %in% TRUE)
registrar("alunos", "id_aluno em formato diferente (001234, ALU01234)", alunos$id_fora_padrao, "convertido para número")
registrar("alunos", "id_aluno ausente", is.na(alunos$id_aluno), "removido")
alunos <- filter(alunos, !is.na(id_aluno))

# Nome fora do padrão (MAIÚSCULAS, minúsculas, espaços)
alunos <- alunos |>
  mutate(nome = str_squish(nome_bruto),
         caixa_errada = (nome == str_to_upper(nome) | nome == str_to_lower(nome)) %in% TRUE,
         nome_fora_padrao = caixa_errada | (nome != nome_bruto) %in% TRUE,
         nome = if_else(caixa_errada, str_to_title(nome, locale = "pt"), nome))
registrar("alunos", "nome fora do padrão (caixa ou espaços)", alunos$nome_fora_padrao, "padronizado")

# Data de nascimento: outro formato, impossível (1900, ano futuro, ano 0016) ou ausente
alunos <- alunos |>
  mutate(data_nascimento = texto_para_data(nasc_bruto),
         nasc_outro_formato = !is.na(nasc_bruto) & !str_detect(nasc_bruto, "^\\d{4}-\\d{2}-\\d{2}$"),
         idade = ano_letivo - year(data_nascimento),
         nasc_invalida = !is.na(nasc_bruto) &
           (is.na(data_nascimento) | idade < IDADE_MIN | idade > IDADE_MAX) %in% TRUE,
         data_nascimento = if_else(nasc_invalida, as.Date(NA), data_nascimento))
registrar("alunos", "data de nascimento em outro formato (dd/mm/aaaa)",
          alunos$nasc_outro_formato & !alunos$nasc_invalida, "convertida para aaaa-mm-dd")
registrar("alunos", "data de nascimento inválida (1900, ano futuro, ano 0016)", alunos$nasc_invalida,
          "deixada vazia (o notebook preenche a idade pela mediana)")
registrar("alunos", "data_nascimento ausente (campo aninhado)", is.na(alunos$nasc_bruto), "mantida vazia")

alunos <- alunos |>
  mutate(restricao_alimentar = coalesce(str_squish(restricao_bruta), "Não informado"))
registrar("alunos", "restricao_alimentar ausente (campo aninhado)", is.na(alunos$restricao_bruta),
          "preenchida com 'Não informado'")

# Turno ausente na turma: deduzido pelo horário das compras dos alunos dela
# (turma da manhã compra perto de 9h30; turma da tarde, perto de 15h10)
turno_pelas_vendas <- vendas |>
  filter(!is.na(id_aluno), wday(data_hora, week_start = 1) <= 5) |>
  mutate(ano_letivo = as.integer(year(data_hora))) |>
  inner_join(distinct(alunos, ano_letivo, id_aluno, turma), by = c("ano_letivo", "id_aluno")) |>
  group_by(ano_letivo, turma) |>
  summarise(turno_inferido = if_else(median(hour(data_hora) + minute(data_hora) / 60) >= 12.75,
                                     "tarde", "manha"), .groups = "drop")
alunos <- alunos |>
  left_join(turno_pelas_vendas, by = c("ano_letivo", "turma")) |>
  mutate(turno_ausente = is.na(turno_bruto),
         turno = coalesce(chave(turno_bruto), turno_inferido))
registrar("alunos", "turno da turma ausente (campo aninhado) - contagem em turmas",
          n_distinct(alunos$turma[alunos$turno_ausente & !is.na(alunos$turno)]),
          "deduzido pelo horário das compras dos alunos da turma")
registrar("alunos", "turno ausente e turma sem compras - contagem em turmas",
          n_distinct(alunos$turma[is.na(alunos$turno)]), "preenchido com 'manha' (turno mais comum)")
alunos <- alunos |> mutate(turno = coalesce(turno, "manha"))

# Deduplicação e homônimos (alunos diferentes com o mesmo nome não são erro)
duplicado <- duplicated(alunos[, c("ano_letivo", "id_aluno")])
registrar("alunos", "aluno repetido (mesmo id no mesmo ano)", duplicado, "removido")
alunos <- alunos[!duplicado, ]

alunos <- alunos |>
  mutate(chave_nome = paste(ano_letivo, chave(nome)),
         nome_repetido = duplicated(chave_nome) | duplicated(chave_nome, fromLast = TRUE))
registrar("alunos", "homônimos (alunos diferentes com o mesmo nome)", alunos$nome_repetido,
          "mantidos (a chave é id_aluno); sinalizados em nome_repetido")

alunos <- alunos |>
  select(turma, ano_letivo, turno, id_aluno, nome, data_nascimento, restricao_alimentar, nome_repetido) |>
  arrange(ano_letivo, id_aluno)


# ---- 5. Devedores -----------------------------------------------------------
message("Limpando devedores...")

db <- read_excel(file.path(BRONZE, "devedores", "devedores_atualizado.xlsx"), col_types = "list")
devedores <- tibble(id_devedor    = as.integer(celula_num(db$id_devedor)),
                    id_aluno      = so_digitos(celula_txt(db$id_aluno)),
                    data_divida   = texto_para_data(celula_txt(db$data_divida)),
                    valor_devido  = celula_num(db$valor_devido),
                    status_bruto  = celula_txt(db$status),
                    data_quitacao = texto_para_data(celula_txt(db$data_quitacao))) |>
  arrange(id_devedor)

# 5.1 O mesmo débito lançado duas vezes (tudo igual menos o id_devedor)
duplicado <- duplicated(select(devedores, -id_devedor))
registrar("devedores", "mesmo débito lançado mais de uma vez", duplicado, "removido (fica o primeiro id)")
devedores <- devedores[!duplicado, ]
registrar("devedores", "data_divida ilegível", is.na(devedores$data_divida), "removido")
devedores <- filter(devedores, !is.na(data_divida))

# 5.2 Status digitado errado ("quitado", "ATRASADO", "Em aberto ")
devedores <- devedores |>
  mutate(status = {
    k <- chave(status_bruto)
    case_when(str_detect(k, "quit") ~ "Quitado",
              str_detect(k, "atras") ~ "Atrasado",
              str_detect(k, "aberto") ~ "Em aberto",
              TRUE ~ NA_character_)
  })
registrar("devedores", "status digitado fora do padrão", (devedores$status != devedores$status_bruto) %in% TRUE,
          "padronizado (Quitado / Em aberto / Atrasado)")

# 5.3 id_aluno que não existe na base de alunos. As dívidas nascem das vendas
# "Fiado" (uma por aluno por dia), então o aluno certo é recuperado pela venda
# fiado do mesmo dia e mesmo valor, quando ela é única.
fiado_dia <- vendas |>
  filter(forma_pagamento == "Fiado", !is.na(id_aluno)) |>
  group_by(id_aluno, data_divida = as_date(data_hora)) |>
  summarise(valor_vendas = round(sum(valor_total), 2), .groups = "drop")

devedores <- devedores |>
  mutate(ano_letivo = as.integer(year(data_divida))) |>
  left_join(transmute(alunos, ano_letivo, id_aluno, existe = TRUE), by = c("ano_letivo", "id_aluno")) |>
  mutate(aluno_inexistente = is.na(existe))

ja_tem_divida <- devedores |> filter(!aluno_inexistente) |> distinct(id_aluno, data_divida)
recuperados <- devedores |>
  filter(aluno_inexistente) |>
  select(id_devedor, data_divida, valor_devido) |>
  inner_join(anti_join(fiado_dia, ja_tem_divida, by = c("id_aluno", "data_divida")),
             by = "data_divida", relationship = "many-to-many") |>
  filter(abs(valor_vendas - abs(valor_devido)) < 0.01) |>
  group_by(id_devedor) |>
  filter(n() == 1) |>
  ungroup() |>
  select(id_devedor, id_recuperado = id_aluno)

devedores <- devedores |>
  left_join(recuperados, by = "id_devedor") |>
  mutate(id_aluno = if_else(aluno_inexistente & !is.na(id_recuperado), id_recuperado, id_aluno))
registrar("devedores", "id_aluno não localizado na base de alunos",
          devedores$aluno_inexistente & !is.na(devedores$id_recuperado),
          "recuperado pela venda Fiado do mesmo dia e valor")
registrar("devedores", "id_aluno não localizado e sem venda fiado correspondente",
          devedores$aluno_inexistente & is.na(devedores$id_recuperado), "removido")
devedores <- filter(devedores, !(aluno_inexistente & is.na(id_recuperado)))

# 5.4 Valor negativo, vazio ou absurdo
devedores <- devedores |>
  left_join(fiado_dia, by = c("id_aluno", "data_divida")) |>
  mutate(valor_negativo = (valor_devido < 0) %in% TRUE,
         valor_absurdo = (abs(valor_devido) > DIVIDA_MAXIMA) %in% TRUE,
         valor_vazio = is.na(valor_devido),
         valor_devido = case_when(valor_vazio ~ valor_vendas,
                                  valor_absurdo ~ round(abs(valor_devido) / 100, 2),
                                  TRUE ~ abs(valor_devido)))
registrar("devedores", "valor_devido negativo", devedores$valor_negativo, "sinal corrigido")
registrar("devedores", "valor_devido absurdo (sem a vírgula)", devedores$valor_absurdo, "dividido por 100")
registrar("devedores", "valor_devido vazio", devedores$valor_vazio & !is.na(devedores$valor_devido),
          "preenchido com a soma das vendas fiado do aluno no dia")
registrar("devedores", "valor_devido vazio sem venda correspondente", is.na(devedores$valor_devido), "removido")
devedores <- filter(devedores, !is.na(valor_devido))

# 5.5 Quitação anterior à dívida: a data é impossível, mas o débito foi quitado
devedores <- devedores |>
  mutate(quitacao_invalida = (data_quitacao < data_divida) %in% TRUE,
         data_quitacao = if_else(quitacao_invalida, as.Date(NA), data_quitacao))
registrar("devedores", "data_quitacao anterior à data_divida", devedores$quitacao_invalida,
          "data apagada; status mantido como Quitado (sinalizado em quitacao_invalida)")

# 5.6 Status desatualizado. A planilha é recalculada a cada execução do gerador,
# então a data de referência é a mais recente encontrada nos dados. Um status só
# "anda para frente": Em aberto -> Atrasado / Quitado (nunca o contrário).
DATA_REFERENCIA <- max(c(as_date(vendas$data_hora), devedores$data_divida, devedores$data_quitacao), na.rm = TRUE)
devedores <- devedores |>
  mutate(dias_em_aberto = as.numeric(DATA_REFERENCIA - data_divida),
         status_correto = case_when(!is.na(data_quitacao) ~ "Quitado",
                                    status %in% c("Em aberto", NA) & dias_em_aberto > DIAS_PARA_ATRASO ~ "Atrasado",
                                    is.na(status) ~ "Em aberto",
                                    TRUE ~ status))
registrar("devedores", paste0("status desatualizado (referência: ", format(DATA_REFERENCIA, "%d/%m/%Y"), ")"),
          (devedores$status_correto != devedores$status) %in% TRUE | is.na(devedores$status),
          "recalculado pela data de quitação e pelos dias em aberto")

devedores <- devedores |>
  transmute(id_devedor, id_aluno, data_divida, valor_devido = round(valor_devido, 2),
            status = status_correto, data_quitacao, quitacao_invalida) |>
  arrange(id_devedor)


# ---- 6. Perdas --------------------------------------------------------------
message("Limpando perdas...")

pb <- read_excel(file.path(BRONZE, "perdas", "historico_perdas.xlsx"), col_types = "list")
perdas <- tibble(id_perda       = as.integer(celula_num(pb$id_perda)),
                 data_bruta     = celula_txt(pb$data),
                 data_em_texto  = celula_eh_texto(pb$data),
                 id_produto     = so_digitos(celula_txt(pb$id_produto)),
                 quantidade     = celula_num(pb$quantidade),
                 motivo         = str_squish(celula_txt(pb$motivo)),
                 valor_prejuizo = celula_num(pb$valor_prejuizo))

duplicada <- duplicated(perdas)
registrar("perdas", "linha duplicada", duplicada, "removida")
perdas <- perdas[!duplicada, ]

perdas <- perdas |> mutate(data = texto_para_data(data_bruta))
registrar("perdas", "data em formato diferente (dd/mm/aaaa, dd-mm-aa, aaaa/mm/dd)",
          perdas$data_em_texto & !is.na(perdas$data), "convertida para aaaa-mm-dd")
registrar("perdas", "data ilegível", is.na(perdas$data), "removida")
perdas <- filter(perdas, !is.na(data))

# Produto sem correspondência no cardápio + custo da versão em vigor na data
# (a versão anterior vale para o estoque remanescente de produtos descontinuados)
n_antes <- nrow(perdas)
perdas <- perdas |>
  mutate(linha = row_number()) |>
  inner_join(select(cardapio, id_produto, vigencia, custo_unitario, custo_imputado),
             by = "id_produto", relationship = "many-to-many") |>
  filter(vigencia <= data) |>
  group_by(linha) |>
  slice_max(vigencia, n = 1, with_ties = FALSE) |>
  ungroup()
registrar("perdas", "produto sem correspondência no cardápio", n_antes - nrow(perdas), "removida")

# Quantidade zerada ou negativa: recuperada por valor_prejuizo / custo
perdas <- perdas |>
  mutate(qtd_invalida = !(quantidade >= 1) %in% TRUE,
         pela_conta = round(abs(valor_prejuizo) / custo_unitario),
         quantidade = case_when(!qtd_invalida ~ quantidade,
                                (quantidade < 0) %in% TRUE ~ abs(quantidade),
                                (pela_conta >= 1) %in% TRUE ~ pela_conta,
                                TRUE ~ NA_real_))
registrar("perdas", "quantidade zerada ou negativa", perdas$qtd_invalida & !is.na(perdas$quantidade),
          "sinal corrigido ou recuperada por valor_prejuizo / custo")
registrar("perdas", "quantidade inválida sem como recuperar", is.na(perdas$quantidade), "removida")
perdas <- filter(perdas, !is.na(quantidade))

# valor_prejuizo diferente de quantidade × custo (quando o custo é confiável)
perdas <- perdas |>
  mutate(esperado = round(quantidade * custo_unitario, 2),
         valor_divergente = is.na(valor_prejuizo) |
           (!custo_imputado & (abs(valor_prejuizo - esperado) > 0.009) %in% TRUE),
         valor_negativo = (valor_prejuizo < 0) %in% TRUE,
         valor_prejuizo = if_else(valor_divergente, esperado, abs(valor_prejuizo)))
registrar("perdas", "valor_prejuizo diferente de quantidade × custo_unitario", perdas$valor_divergente, "recalculado")
registrar("perdas", "valor_prejuizo negativo (custo do produto estimado)", perdas$valor_negativo & !perdas$valor_divergente,
          "sinal corrigido")

registrar("perdas", "motivo não preenchido", is.na(perdas$motivo) | perdas$motivo == "", "preenchido com 'Não informado'")
perdas <- perdas |>
  mutate(motivo = coalesce(na_if(motivo, ""), "Não informado")) |>
  transmute(id_perda, data, id_produto, quantidade = as.integer(quantidade), motivo, valor_prejuizo) |>
  arrange(id_perda)


# ---- 7. Calendário escolar --------------------------------------------------
message("Limpando calendário escolar...")

calendario <- map_dfr(listar("calendario_escolar", "^calendario_escolar_\\d{4}\\.json$"), function(arq) {
  js <- fromJSON(arq, simplifyVector = FALSE)
  tibble(data        = as.Date(map_chr(js$dias, \(d) campo_txt(d$data)), format = "%Y-%m-%d"),
         tipo_bruto  = map_chr(js$dias, \(d) campo_txt(d$tipo_dia)),
         descricao   = map_chr(js$dias, \(d) campo_txt(d$descricao)),
         turno_bruto = map_chr(js$dias, \(d) campo_txt(d$turno_letivo)))
}) |>
  filter(!is.na(data)) |>
  distinct(data, .keep_all = TRUE)

# tipo_dia digitado errado ("LETIVO", "letivos", "fim de semana", "férias")
calendario <- calendario |>
  mutate(tipo_dia = str_replace_all(chave(tipo_bruto), "[ -]+", "_"),
         tipo_dia = if_else(!tipo_dia %in% TIPOS_DIA & str_remove(tipo_dia, "s$") %in% TIPOS_DIA,
                            str_remove(tipo_dia, "s$"), tipo_dia))
registrar("calendario", "tipo_dia digitado fora do padrão", (calendario$tipo_dia != calendario$tipo_bruto) %in% TRUE,
          "padronizado")

# Feriado nacional marcado como dia letivo
calendario <- calendario |>
  left_join(map_dfr(unique(year(calendario$data)), feriados_nacionais), by = "data") |>
  mutate(feriado_como_letivo = !is.na(nome_feriado) & tipo_dia != "feriado",
         tipo_dia = if_else(feriado_como_letivo, "feriado", tipo_dia),
         descricao = if_else(feriado_como_letivo, nome_feriado, descricao),
         turno_bruto = if_else(feriado_como_letivo, "nenhum", turno_bruto))
registrar("calendario", "feriado nacional marcado como dia letivo", calendario$feriado_como_letivo,
          "corrigido para feriado")

# turno_letivo ausente: deduzido do tipo do dia e da descrição
calendario <- calendario |>
  mutate(desc = chave(descricao),
         turno_letivo = case_when(!is.na(turno_bruto) ~ chave(turno_bruto),
                                  tipo_dia == "letivo" & str_detect(desc, "somente a tarde") ~ "tarde",
                                  tipo_dia == "letivo" & str_detect(desc, "sem aulas a tarde") ~ "manha",
                                  tipo_dia == "letivo" ~ "integral",
                                  tipo_dia == "sabado_letivo" ~ "manha",
                                  TRUE ~ "nenhum"))
registrar("calendario", "turno_letivo ausente", is.na(calendario$turno_bruto), "deduzido do tipo do dia e da descrição")

# Conciliação com as vendas: o calendário publicado não foi atualizado depois da
# greve e das reposições. Dia sem aula com vendas = reposição; dia letivo sem
# vendas fica sinalizado (pode ser greve ou um dia em que o gerador não rodou).
dias_com_venda <- unique(as_date(vendas$data_hora))
ultimo_dia_vendas <- max(dias_com_venda)
calendario <- calendario |>
  mutate(houve_vendas = data %in% dias_com_venda,
         reposicao = houve_vendas & !tipo_dia %in% c("letivo", "sabado_letivo"),
         sabado = wday(data, week_start = 1) == 6,
         tipo_dia = if_else(reposicao, if_else(sabado, "sabado_letivo", "letivo"), tipo_dia),
         descricao = if_else(reposicao, "Reposição de aulas (identificada pelas vendas; calendário publicado não atualizado)",
                             descricao),
         turno_letivo = if_else(reposicao, if_else(sabado, "manha", "integral"), turno_letivo),
         houve_vendas = if_else(data > ultimo_dia_vendas, NA, houve_vendas))
registrar("calendario", "dia sem aula no calendário, mas com vendas (reposição não atualizada)",
          calendario$reposicao, "marcado como dia letivo de reposição")
registrar("calendario", "dia letivo sem nenhuma venda (possível greve ou dia sem registro)",
          calendario$tipo_dia %in% c("letivo", "sabado_letivo") & calendario$houve_vendas %in% FALSE &
            calendario$data >= min(dias_com_venda),
          "mantido como letivo e sinalizado em houve_vendas = FALSE")

calendario <- calendario |>
  select(data, tipo_dia, descricao, turno_letivo, houve_vendas) |>
  arrange(data)


# ---- 8. Clima ---------------------------------------------------------------
message("Limpando clima...")

clima_bruto <- map_dfr(listar("clima", "^clima_\\d{4}\\.json$"), function(arq) {
  regs <- fromJSON(arq, simplifyVector = FALSE)$registros
  tibble(data_bruta        = map_chr(regs, \(r) campo_txt(r$data)),
         temperatura_media = map_dbl(regs, \(r) campo_num(r$temperatura_media)),
         temperatura_max   = map_dbl(regs, \(r) campo_num(r$temperatura_max)),
         condicao          = map_chr(regs, \(r) campo_txt(r$condicao)),
         precipitacao_mm   = map_dbl(regs, \(r) campo_num(r$precipitacao_mm)))
})

# Fuso divergente ("2026-03-04T21:00:00-03:00" = 05/03 em UTC) e leituras horárias
clima_bruto <- clima_bruto |>
  mutate(com_fuso = str_detect(data_bruta, "[+-]\\d{2}:\\d{2}$") %in% TRUE,
         horaria = str_detect(data_bruta, "T\\d{2}:") %in% TRUE & !com_fuso,
         data = if_else(com_fuso, as_date(ymd_hms(data_bruta, quiet = TRUE)),
                        as.Date(substr(data_bruta, 1, 10), format = "%Y-%m-%d")),
         condicao = str_replace_all(chave(condicao), " ", "_"))
registrar("clima", "data com fuso horário divergente", clima_bruto$com_fuso, "convertida para o dia correto")
registrar("clima", "dia com 24 leituras horárias (granularidade diferente) - contagem em dias",
          n_distinct(clima_bruto$data[clima_bruto$horaria]),
          "agregado: média das temperaturas, máxima das máximas e soma da chuva")

# Valores absurdos viram vazio (e depois são preenchidos)
absurda <- function(t) (t < TEMP_MIN | t > TEMP_MAX) %in% TRUE
registrar("clima", "temperatura absurda (999,9, sinal trocado, ×10)",
          absurda(clima_bruto$temperatura_media) | absurda(clima_bruto$temperatura_max), "descartada e interpolada")
registrar("clima", "precipitação negativa", (clima_bruto$precipitacao_mm < 0) %in% TRUE, "descartada e estimada")
clima_bruto <- clima_bruto |>
  mutate(temperatura_media = if_else(absurda(temperatura_media), NA_real_, temperatura_media),
         temperatura_max = if_else(absurda(temperatura_max), NA_real_, temperatura_max),
         precipitacao_mm = if_else((precipitacao_mm < 0) %in% TRUE, NA_real_, precipitacao_mm))

clima <- clima_bruto |>
  filter(!is.na(data)) |>
  group_by(data) |>
  summarise(temperatura_media = media_na(temperatura_media),
            temperatura_max = max_na(temperatura_max),
            condicao = moda(condicao),
            precipitacao_mm = soma_na(precipitacao_mm),
            .groups = "drop")

# Dias ausentes (falha de requisição) entram na série para serem preenchidos
todos_os_dias <- tibble(data = seq(floor_date(min(clima$data), "year"), max(clima$data), by = "day"))
registrar("clima", "dia ausente (falha de requisição)", !todos_os_dias$data %in% clima$data,
          "incluído e preenchido (imputado = TRUE)")
clima <- todos_os_dias |>
  left_join(clima, by = "data") |>
  arrange(data) |>
  mutate(imputado = is.na(temperatura_media) | is.na(temperatura_max) |
           is.na(condicao) | is.na(precipitacao_mm))
registrar("clima", "dia com campos nulos ou descartados", clima$imputado,
          "temperaturas interpoladas entre os dias vizinhos; condição e chuva estimadas")

clima <- clima |>
  mutate(temperatura_media = round(interpolar(temperatura_media), 1),
         temperatura_max = round(interpolar(temperatura_max), 1),
         condicao = case_when(!is.na(condicao) ~ condicao,
                              (precipitacao_mm >= 25) %in% TRUE ~ "tempestade",
                              (precipitacao_mm >= 1) %in% TRUE ~ "chuva",
                              TRUE ~ NA_character_)) |>
  fill(condicao, .direction = "downup")
mediana_chuva <- clima |>
  filter(condicao %in% c("chuva", "tempestade"), !is.na(precipitacao_mm)) |>
  group_by(condicao) |>
  summarise(chuva_tipica = median(precipitacao_mm), .groups = "drop")
amplitude <- median(clima$temperatura_max - clima$temperatura_media, na.rm = TRUE)
clima <- clima |>
  left_join(mediana_chuva, by = "condicao") |>
  mutate(precipitacao_mm = round(case_when(!is.na(precipitacao_mm) ~ precipitacao_mm,
                                           condicao %in% c("chuva", "tempestade") ~ chuva_tipica,
                                           TRUE ~ 0), 1),
         temperatura_max = if_else(temperatura_max < temperatura_media,
                                   round(temperatura_media + amplitude, 1), temperatura_max)) |>
  select(data, temperatura_media, temperatura_max, condicao, precipitacao_mm, imputado)


# ---- 9. Inflação ------------------------------------------------------------
message("Limpando inflação...")

inflacao <- map_dfr(listar("inflacao", "^inflacao_\\d{4}\\.json$"), function(arq) {
  dados <- fromJSON(arq, simplifyVector = FALSE)$dados
  if (length(dados) == 0) return(NULL)
  tibble(mes_bruto       = map_chr(dados, \(r) campo_txt(r$mes_referencia)),
         indice_inflacao = map_dbl(dados, \(r) campo_num(r$indice_inflacao)),
         categoria_bruta = map_chr(dados, \(r) campo_txt(r$categoria_produto)))
})
if (nrow(inflacao) == 0) {
  inflacao <- tibble(mes_bruto = character(), indice_inflacao = numeric(), categoria_bruta = character())
}

# Mês em outro formato ("03/2026" -> "2026-03")
padronizar_mes <- function(x) {
  iso <- str_match(x, "^(\\d{4})-(\\d{1,2})$")
  br  <- str_match(x, "^(\\d{1,2})/(\\d{4})$")
  ano <- coalesce(iso[, 2], br[, 3])
  mes <- coalesce(iso[, 3], br[, 2])
  if_else(is.na(ano) | is.na(mes), NA_character_, sprintf("%s-%02d", ano, suppressWarnings(as.integer(mes))))
}
inflacao <- inflacao |> mutate(mes_referencia = padronizar_mes(mes_bruto))
registrar("inflacao", "mês em outro formato (mm/aaaa)", (inflacao$mes_referencia != inflacao$mes_bruto) %in% TRUE,
          "convertido para aaaa-mm")
registrar("inflacao", "mês ilegível", is.na(inflacao$mes_referencia), "removido")
inflacao <- filter(inflacao, !is.na(mes_referencia))

# Categoria com nomenclatura da API ("Bebidas não alcoólicas") ou digitada errada
inflacao <- inflacao |> mutate(categoria_produto = casar_por_prefixo(categoria_bruta, CATEGORIAS_API, CATEGORIAS_PARA))
registrar("inflacao", "categoria diferente da usada no cardápio (nome da API ou digitação)",
          (inflacao$categoria_produto != inflacao$categoria_bruta) %in% TRUE, "mapeada para a categoria do cardápio")
registrar("inflacao", "categoria irreconhecível", is.na(inflacao$categoria_produto), "removida")
inflacao <- filter(inflacao, !is.na(categoria_produto))

# Índice sem a vírgula ou nulo
inflacao <- inflacao |>
  mutate(sem_virgula = (abs(indice_inflacao) > INFLACAO_MAX) %in% TRUE,
         indice_inflacao = if_else(sem_virgula, indice_inflacao / 100, indice_inflacao),
         imputado = is.na(indice_inflacao)) |>
  group_by(mes_referencia) |>
  mutate(indice_inflacao = if_else(imputado, mean(indice_inflacao, na.rm = TRUE), indice_inflacao)) |>
  ungroup() |>
  mutate(indice_inflacao = if_else(is.nan(indice_inflacao), NA_real_, round(indice_inflacao, 2)))
registrar("inflacao", "índice absurdo (sem a vírgula)", inflacao$sem_virgula, "dividido por 100")
registrar("inflacao", "índice nulo", inflacao$imputado, "preenchido com a média das outras categorias no mês")

duplicado <- duplicated(inflacao[, c("mes_referencia", "categoria_produto")])
registrar("inflacao", "mês/categoria repetido", duplicado, "removido")
inflacao <- inflacao[!duplicado, ]

# Conciliação temporal: o índice de um mês só é publicado 2 meses depois
meses_sem_indice <- setdiff(unique(format(vendas$data_hora, "%Y-%m")), inflacao$mes_referencia)
registrar("inflacao", paste0("meses com vendas e sem índice publicado (defasagem): ",
                             paste(sort(meses_sem_indice), collapse = ", ")),
          length(meses_sem_indice), "não inventados; a coluna disponivel_em indica quando cada índice sai")
inflacao <- inflacao |>
  mutate(disponivel_em = ymd(paste0(mes_referencia, "-01")) %m+% months(DEFASAGEM_INFLACAO_MESES)) |>
  select(mes_referencia, indice_inflacao, categoria_produto, disponivel_em, imputado) |>
  arrange(mes_referencia, match(categoria_produto, CATEGORIAS))


# ---- 10. Gravação da camada Silver ------------------------------------------
message("\nGravando em ", normalizePath(SILVER), ":")

salvar <- function(df, nome) {
  write_csv(df, file.path(SILVER, paste0(nome, ".csv")), na = "")
  message(sprintf("  %-20s %7d linhas", paste0(nome, ".csv"), nrow(df)))
}

# data_hora sai como texto "aaaa-mm-dd hh:mm:ss" (sem fuso), igual às outras datas
salvar(mutate(vendas, data_hora = format(data_hora, "%Y-%m-%d %H:%M:%S", tz = "UTC")), "vendas")
salvar(devedores, "devedores")
salvar(cardapio, "cardapio")
salvar(perdas, "perdas")
salvar(calendario, "calendario")
salvar(clima, "clima")
salvar(alunos, "alunos")
salvar(inflacao, "inflacao")
salvar(relatorio, "relatorio_limpeza")

message("\nResumo da limpeza:")
print(relatorio, n = Inf, width = Inf)
