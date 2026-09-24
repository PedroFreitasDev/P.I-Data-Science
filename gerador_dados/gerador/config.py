"""Parâmetros e tabelas de referência usados pelo gerador de dados fictícios."""

from dataclasses import dataclass, field

NOME_ESCOLA = "Colégio Fictício Horizonte"
CIDADE = "São Paulo/SP"

# ---------------------------------------------------------------------------
# Produtos
# ---------------------------------------------------------------------------
# tags indicam restrições alimentares que impedem a compra:
#   lactose, gluten, amendoim, carne (vegetarianos), acucar (diabéticos)
# clima: "quente" -> vende mais em dias quentes; "frio" -> vende mais em dias frios


@dataclass(frozen=True)
class ProdutoBase:
    id: int
    nome: str
    categoria: str
    preco: float
    custo: float
    perecivel: bool
    tags: frozenset = field(default_factory=frozenset)
    popularidade: float = 1.0
    clima: str | None = None
    serie_min: int = 1  # série mínima que costuma comprar (1 = 1º ano EF)


def _p(id, nome, cat, preco, custo, perec, tags=(), pop=1.0, clima=None, serie_min=1):
    return ProdutoBase(id, nome, cat, preco, custo, perec, frozenset(tags), pop, clima, serie_min)


SALG, LANC, BEB, DOCE, SOBR = "Salgados", "Lanches Naturais", "Bebidas", "Doces", "Sobremesas"
CATEGORIAS = [SALG, LANC, BEB, DOCE, SOBR]

PRODUTOS = {
    p.id: p
    for p in [
        _p(1, "Coxinha de frango", SALG, 6.00, 2.20, True, ("gluten", "carne"), 10),
        _p(2, "Pão de queijo", SALG, 4.00, 1.30, True, ("lactose",), 9),
        _p(3, "Esfiha de carne", SALG, 6.00, 2.30, True, ("gluten", "carne"), 6),
        _p(4, "Enroladinho de salsicha", SALG, 5.50, 2.00, True, ("gluten", "carne"), 6),
        _p(5, "Pastel assado de queijo", SALG, 6.50, 2.40, True, ("gluten", "lactose"), 5),
        _p(6, "Empada de palmito", SALG, 6.50, 2.60, True, ("gluten", "lactose"), 3),
        _p(7, "Misto quente", LANC, 8.00, 3.00, True, ("gluten", "lactose", "carne"), 5, "frio"),
        _p(8, "Sanduíche natural de frango", LANC, 9.50, 3.80, True, ("gluten", "carne"), 4),
        _p(9, "Wrap vegetariano", LANC, 10.00, 4.20, True, ("gluten",), 2, None, 6),
        _p(10, "Tapioca de queijo", LANC, 8.50, 3.20, True, ("lactose",), 3),
        _p(11, "Água mineral 500ml", BEB, 3.00, 1.00, False, (), 7, "quente"),
        _p(12, "Suco natural de laranja 300ml", BEB, 6.00, 2.20, True, (), 6, "quente"),
        _p(13, "Refrigerante lata", BEB, 6.00, 3.00, False, ("acucar",), 6, "quente", 3),
        _p(14, "Achocolatado 200ml", BEB, 4.00, 1.70, False, ("lactose", "acucar"), 6),
        _p(15, "Chá gelado 300ml", BEB, 5.00, 1.80, False, ("acucar",), 3, "quente"),
        _p(16, "Chocolate quente", BEB, 6.00, 2.00, True, ("lactose", "acucar"), 2, "frio"),
        _p(17, "Café expresso", BEB, 4.00, 1.00, False, (), 1.5, "frio", 9),
        _p(18, "Brigadeiro", DOCE, 3.50, 1.10, True, ("lactose", "acucar"), 5),
        _p(19, "Bolo de cenoura (fatia)", DOCE, 5.00, 1.80, True, ("gluten", "lactose", "acucar"), 4),
        _p(20, "Cookie", DOCE, 4.50, 1.60, False, ("gluten", "lactose", "acucar"), 4),
        _p(21, "Barra de cereal", DOCE, 3.50, 1.50, False, ("amendoim",), 3),
        _p(22, "Paçoca", DOCE, 2.00, 0.60, False, ("amendoim", "acucar"), 3),
        _p(23, "Picolé de fruta", SOBR, 5.00, 1.90, False, ("acucar",), 4, "quente"),
        _p(24, "Sorvete de massa (copo)", SOBR, 8.00, 3.00, False, ("lactose", "acucar"), 3, "quente"),
        _p(25, "Salada de frutas", SOBR, 7.00, 2.80, True, (), 2),
        _p(26, "Açaí 300ml", SOBR, 14.00, 5.50, False, ("acucar",), 2.5, "quente", 6),
        _p(27, "Gelatina (copo)", SOBR, 3.50, 1.00, True, ("acucar",), 2),
        # Entram apenas no cardápio do 2º semestre
        _p(28, "Pão de batata recheado", SALG, 6.00, 2.20, True, ("gluten", "lactose"), 5),
        _p(29, "Iogurte com granola", SOBR, 7.50, 3.00, True, ("lactose", "gluten"), 3),
    ]
}

PRODUTOS_1_SEMESTRE = [i for i in PRODUTOS if i <= 27]
DESCONTINUADOS_2_SEMESTRE = {6, 15}
NOVOS_2_SEMESTRE = {28, 29}
# Dias após a troca de cardápio em que a cantina ainda vende o estoque remanescente
DIAS_ESTOQUE_REMANESCENTE = 5

# Itens baratos que costumam ser comprados em mais de uma unidade
ITENS_MULTIPLOS = {2, 11, 18, 22}

# ---------------------------------------------------------------------------
# Alunos
# ---------------------------------------------------------------------------
RESTRICOES = [
    ("Nenhuma", 0.82, frozenset()),
    ("Intolerância à lactose", 0.07, frozenset({"lactose"})),
    ("Doença celíaca", 0.03, frozenset({"gluten"})),
    ("Alergia a amendoim", 0.03, frozenset({"amendoim"})),
    ("Vegetariano", 0.03, frozenset({"carne"})),
    ("Diabetes tipo 1", 0.02, frozenset({"acucar"})),
]
TAGS_POR_RESTRICAO = {nome: tags for nome, _, tags in RESTRICOES}

FORMAS_PAGAMENTO = ["Dinheiro", "Pix", "Cartão de débito", "Cartão de crédito", "Fiado"]

# Pesos de forma de pagamento por segmento (sem o fiado, tratado à parte)
PESOS_PAGAMENTO = {
    "EF1": {"Dinheiro": 50, "Pix": 10, "Cartão de débito": 15, "Cartão de crédito": 5},
    "EF2": {"Dinheiro": 30, "Pix": 35, "Cartão de débito": 20, "Cartão de crédito": 5},
    "EM": {"Dinheiro": 15, "Pix": 50, "Cartão de débito": 20, "Cartão de crédito": 10},
}

NOMES_FEMININOS = [
    "Ana", "Beatriz", "Camila", "Carolina", "Clara", "Cecília", "Débora", "Eduarda", "Elisa",
    "Emanuelly", "Fernanda", "Gabriela", "Giovanna", "Helena", "Isabela", "Isadora", "Julia",
    "Juliana", "Lara", "Larissa", "Laura", "Letícia", "Lívia", "Lorena", "Luana", "Luiza",
    "Manuela", "Maria", "Mariana", "Marina", "Melissa", "Mirella", "Natália", "Nicole", "Olívia",
    "Paula", "Rafaela", "Rebeca", "Sarah", "Sofia", "Valentina", "Vitória", "Yasmin", "Alice",
    "Heloísa", "Lavínia", "Esther", "Agatha", "Bianca", "Catarina",
]
NOMES_MASCULINOS = [
    "Arthur", "Benício", "Bernardo", "Bruno", "Caio", "Daniel", "Davi", "Diego", "Eduardo",
    "Enzo", "Felipe", "Fernando", "Gabriel", "Gustavo", "Heitor", "Henrique", "Igor", "Isaac",
    "João", "Joaquim", "José", "Lorenzo", "Lucas", "Luiz", "Marcelo", "Mateus", "Miguel",
    "Murilo", "Nicolas", "Otávio", "Pedro", "Rafael", "Ravi", "Rodrigo", "Samuel", "Theo",
    "Thiago", "Vicente", "Vinícius", "Vitor", "Leonardo", "Antônio", "Guilherme", "Matheus",
    "Pietro", "Kaique", "Emanuel", "Bryan", "Yuri", "Cauã",
]
SOBRENOMES = [
    "Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", "Pereira", "Lima",
    "Gomes", "Costa", "Ribeiro", "Martins", "Carvalho", "Almeida", "Lopes", "Soares", "Fernandes",
    "Vieira", "Barbosa", "Rocha", "Dias", "Nascimento", "Andrade", "Moreira", "Nunes", "Marques",
    "Machado", "Mendes", "Freitas", "Cardoso", "Ramos", "Gonçalves", "Santana", "Teixeira",
    "Araújo", "Pinto", "Moraes", "Correia", "Cavalcanti", "Campos", "Castro", "Monteiro",
    "Fragoso", "Toledo", "Barros", "Azevedo", "Duarte", "Miranda", "Rezende",
]

# ---------------------------------------------------------------------------
# Clima (médias mensais aproximadas de uma capital do Sudeste)
# ---------------------------------------------------------------------------
TEMP_MEDIA_MES = {1: 23.5, 2: 23.8, 3: 23.0, 4: 21.2, 5: 18.6, 6: 17.4,
                  7: 16.9, 8: 18.0, 9: 19.0, 10: 20.4, 11: 21.5, 12: 22.8}
PROB_CHUVA_MES = {1: 0.55, 2: 0.50, 3: 0.45, 4: 0.30, 5: 0.22, 6: 0.15,
                  7: 0.12, 8: 0.12, 9: 0.25, 10: 0.35, 11: 0.42, 12: 0.52}

# ---------------------------------------------------------------------------
# Inflação (variação mensal média em %, por categoria do cardápio)
# ---------------------------------------------------------------------------
INFLACAO_MEDIA_CATEGORIA = {SALG: 0.45, LANC: 0.40, BEB: 0.35, DOCE: 0.50, SOBR: 0.38}
# A "API" de inflação usa uma nomenclatura própria para algumas categorias,
# o que gera a inconsistência "categoria não compatível com o cardápio".
NOME_CATEGORIA_API = {
    SALG: SALG,
    LANC: "Lanches",
    BEB: "Bebidas não alcoólicas",
    DOCE: DOCE,
    SOBR: "Sobremesas e sorvetes",
}
# Meses de atraso na publicação do índice
DEFASAGEM_INFLACAO_MESES = 2
