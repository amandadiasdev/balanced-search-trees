# Árvore AVL aumentada do grupo 5

Este projeto implementa uma árvore de busca balanceada. A estrutura é uma AVL com chaves inteiras únicas.

Cada nó armazena referências para os filhos e para o pai, além dos metadados `height`, `size` e `subtree_max`.

O projeto também inclui um executor de cargas, uma referência baseada em lista ordenada, um benchmark e testes.

## Configuração do grupo 5

| Parâmetro         | Valor                                |
| ----------------- | ------------------------------------ |
| Conjunto de dados | `amzn`, arquivo `books_200M_uint32`  |
| Theta             | `0.99`                               |
| Mistura nominal   | `45:25:30` para I:D:S                |
| Agregado          | máximo no intervalo fechado `[a, b]` |
| Ordem de inserção | `ordenada`                           |
| Semente           | `5`                                  |

## Estrutura do projeto

```text
balanced_search_tree/
├── src/
│   ├── augmented_avl.py      # Node e AugmentedAVLTree
│   ├── benchmark.py          # medições da AVL e da referência
│   ├── helper_functions.py   # bisseções e parser compartilhado em PT-BR
│   ├── run_experiments.py    # matriz JSON, checkpoints e retomada
│   ├── run_trace.py          # execução e comparação com o oráculo
│   └── workload_generator.py # gerador e verificador fornecido
├── tests/                    # testes comportamentais, diferenciais e de CLI
├── docs/                     # instruções, material didático e plano
├── pyproject.toml            # dependências e configuração das ferramentas
└── README.md
```

`helper_functions.py` implementa `bisect_left` e `bisect_right` por busca binária e centraliza a tradução das CLIs. Isso
torna explícito o algoritmo usado pela lista de referência. Nos testes diferenciais, as funções da biblioteca padrão
continuam sendo usadas como referência independente.

## Como a correção é verificada

A correção é observada em três níveis complementares.

1. `tests/test_augmented_avl.py` compara as operações públicas da AVL com um `set` e uma lista ordenada independentes.
2. `AugmentedAVLTree.assert_valid()` verifica ordenação, balanceamento AVL, links `parent`, ausência de ciclos e todos os
   metadados aumentados.
3. `src/run_trace.py --esperado ...` compara cada busca produzida com o arquivo `.expected`. O programa também detecta
   se o oráculo tem linhas faltando ou excedentes e retorna código diferente de zero em caso de divergência.

O modo `--mostrar-passos` é destinado a explicações e cargas pequenas. Ele mostra os caminhos de entrada e saída no
início e depois descreve cada operação. Uma busca exibe simultaneamente o valor obtido, o esperado e `OK` ou
`DIVERGÊNCIA`.

```text
╒═══════════╤═══════════════════════════╕
│ Arquivo   │ Caminho                   │
╞═══════════╪═══════════════════════════╡
│ Rastro    │ /caminho/g5-demo.trace    │
│ Candidato │ /caminho/candidate.out    │
│ Oráculo   │ /caminho/g5-demo.expected │
╘═══════════╧═══════════════════════════╛
╒═════════╤════════════╤══════════╤══════════╤═══════════╤═════════════╕
│ Linha   │ Operação   │ Ação     │ Obtido   │ Esperado  │ Conferência │
╞═════════╪════════════╪══════════╪══════════╪═══════════╪═════════════╡
│ 1       │ I 10       │ inserida │ -        │ sem saída │ -           │
├─────────┼────────────┼──────────┼──────────┼───────────┼─────────────┤
│ 2       │ S 10       │ busca    │ 10 FOUND │ 10 FOUND  │ OK          │
╘═════════╧════════════╧══════════╧══════════╧═══════════╧═════════════╛
[oráculo] 1/1 respostas de busca conferem
```

Para cargas grandes, omita `--mostrar-passos`. A comparação com `--esperado` continua sendo feita como fluxo, sem
carregar os arquivos inteiros na memória.

## Preparação

Instale o [`uv`](https://docs.astral.sh/uv/) e sincronize o ambiente do projeto.

```bash
uv sync
```

## Exemplo mínimo da API

Como os módulos estão em `src/`, execute este exemplo com `PYTHONPATH=src` ou importe-os a partir de outro módulo do
mesmo diretório.

```bash
PYTHONPATH=src uv run python - <<'PY'
from augmented_avl import AugmentedAVLTree

tree = AugmentedAVLTree()
tree.insert(30)
tree.insert(10)
tree.insert(20)

assert tree.search(20)
assert tree.rank(30) == 2
assert tree.select(1) == 20
assert tree.range_agg(15, 30) == 30
tree.assert_valid()
PY
```

Contratos principais da árvore:

- `insert` e `delete` retornam `bool`. Duplicatas e remoções ausentes não alteram a árvore.
- `rank(k)` conta chaves estritamente menores que `k`.
- `select(i)` usa índice baseado em zero e levanta `IndexError` fora da faixa.
- `range_agg(a, b)` inclui as duas pontas, retorna `None` quando o intervalo está vazio e levanta `ValueError` se
  `a > b`.
- `root.parent` é sempre `None`. Todo filho aponta de volta para seu pai.

## Execução didática com o oráculo

Primeiro, gere uma carga pequena com a configuração do grupo 5.

```bash
uv run python src/workload_generator.py gerar \
    --sintetico 100 \
    --operacoes 30 \
    --universo 100 \
    --mistura 45:25:30 \
    --theta 0.99 \
    --ordem-insercao ordenada \
    --semente 5 \
    --saida g5-demo
```

Depois, execute a AVL e acompanhe cada operação comparada com o oráculo.

```bash
uv run python src/run_trace.py \
    g5-demo.trace \
    --saida candidate.out \
    --esperado g5-demo.expected \
    --mostrar-passos \
    --validar-a-cada 1
```

## Smoke test sem saída por operação

```bash
uv run python src/workload_generator.py gerar \
    --sintetico 10000 \
    --operacoes 50000 \
    --universo 10000 \
    --mistura 45:25:30 \
    --theta 0.99 \
    --ordem-insercao ordenada \
    --semente 5 \
    --saida g5-smoke

uv run python src/run_trace.py \
    g5-smoke.trace \
    --saida candidate.out \
    --esperado g5-smoke.expected \
    --validar-a-cada 1000
```

O resumo `[oráculo] N/N respostas de busca conferem` confirma simultaneamente o conteúdo e a quantidade das respostas.
O subcomando `verificar` fornecido ainda pode ser executado como uma conferência adicional.

```bash
uv run python src/workload_generator.py verificar \
    --esperado g5-smoke.expected \
    --candidato candidate.out
```

## Piloto com o dataset amzn

### Como baixar o SOSD

O diretório `SOSD/` não faz parte do repositório deste projeto porque contém
datasets e código externo que ocupam dezenas de gigabytes. Baixe-o apenas se
for executar o piloto com o dataset real. O diretório é ignorado pelo Git, mas
o caminho esperado pelo projeto permanece `SOSD/data/books_200M_uint32`.

Pré-requisitos para o download completo:

- Linux baseado em Debian/Ubuntu;
- `git`, `wget`, `zstd`, `python3-pip`, `m4`, `cmake`, `clang` e Boost;
- espaço livre suficiente para os datasets escolhidos. O download completo
  pode ocupar dezenas de gigabytes.

Em uma instalação Debian/Ubuntu, instale as dependências e baixe uma cópia
raso do repositório SOSD:

```bash
sudo apt update
sudo apt install -y git wget zstd python3-pip m4 cmake clang libboost-all-dev
python3 -m pip install --user numpy scipy
git clone --depth 1 https://github.com/learnedsystems/SOSD.git
cd SOSD
bash ./scripts/download.sh
cd ..
```

Confirme que o arquivo usado pelo piloto foi baixado:

```bash
test -f SOSD/data/books_200M_uint32
ls -lh SOSD/data/books_200M_uint32
```

Se o script oficial não funcionar, baixe o arquivo equivalente a partir de um
espelho confiável indicado pela documentação do SOSD, confira o hash publicado
nesse espelho e salve o arquivo em `SOSD/data/books_200M_uint32`. O gerador lê
esse formato binário com `--formato sosd` e chaves de 4 bytes. Durante o
desenvolvimento, prefira o dataset sintético ou use `--carga-maxima` para
limitar o número de chaves consumidas.

```bash
uv run python src/workload_generator.py gerar \
    --chaves SOSD/data/books_200M_uint32 \
    --formato sosd \
    --bytes-chave 4 \
    --carga-maxima 20000000 \
    --operacoes 1000000 \
    --universo 10000000 \
    --mistura 45:25:30 \
    --theta 0.99 \
    --ordem-insercao ordenada \
    --semente 5 \
    --saida g5-pilot
```

Registre qualquer uso de `--carga-maxima` no relatório. O gerador pode converter tentativas de inserção em buscas quando
as chaves inseríveis acabam. Por isso, use as contagens efetivas produzidas pelos programas.

## Benchmark

Execute as duas implementações sobre o mesmo rastro.

```bash
uv run python src/benchmark.py \
    g5-smoke.trace \
    --saida results/g5-smoke.csv \
    --implementacao avl \
    --conjunto-dados sintético \
    --repeticao 1

uv run python src/benchmark.py \
    g5-smoke.trace \
    --saida results/g5-smoke.csv \
    --implementacao lista-ordenada \
    --conjunto-dados sintético \
    --repeticao 1 \
    --acrescentar
```

O CSV contém as contagens efetivas, média, p50, p99, tempo total, rotações, tamanho, altura e metadados do ambiente.

## Estudo empírico completo por configuração

O diretório `docs` contém três configurações reproduzíveis:

- [`estudo-empirico-grupo-5-piloto.json`](docs/estudo-empirico-grupo-5-piloto.json) preserva a matriz de 320 execuções já
  usada na análise preliminar;
- [`estudo-empirico-grupo-5-validacao-1m.json`](docs/estudo-empirico-grupo-5-validacao-1m.json) executa uma repetição das
  quatro combinações da escala de 1 milhão;
- [`estudo-empirico-grupo-5-relatorio.json`](docs/estudo-empirico-grupo-5-relatorio.json) contém a matriz definitiva de
  140 execuções.

A matriz definitiva avalia 1.000, 10.000, 100.000 e 1.000.000 de operações com `theta=0.99`. A escala de 100.000 também
avalia `theta` em `0.0`, `0.6`, `0.99` e `1.2`. Todas as combinações usam as duas ordens de inserção, as duas
implementações, a mistura `45:25:30`, a semente `5` e cinco repetições. Valores isolados e listas são aceitos. Dentro de
cada objeto do array `experimentos`, o programa usa `itertools.product` para executar as combinações.

O perfil realiza 140 execuções e 28,22 milhões de invocações medidas. Ele mantém quatro faixas decimais e reduz em 80% o
volume de operações da configuração anterior, adequando o estudo à execução sequencial em um laptop com 8 GB de RAM.

## Sequência de execução para o relatório

Execute os comandos abaixo a partir da raiz do projeto. O experimento piloto não precisa ser repetido.

### 1. Conferir os planos

Estes comandos apenas validam os JSONs e mostram as quantidades de casos. Eles não geram rastros nem resultados.

```bash
uv run python src/run_experiments.py \
    docs/estudo-empirico-grupo-5-validacao-1m.json \
    --somente-planejar

uv run python src/run_experiments.py \
    docs/estudo-empirico-grupo-5-relatorio.json \
    --somente-planejar
```

A saída deve informar, respectivamente, 4 e 140 execuções.

### 2. Validar a escala máxima

Execute uma repetição das duas ordens de inserção nas duas implementações. Antes de continuar, confirme que o processo
terminou sem erro e que o consumo de memória foi aceitável no laptop de 8 GB.

```bash
uv run python src/run_experiments.py \
    docs/estudo-empirico-grupo-5-validacao-1m.json
```

Os quatro resultados são gravados diretamente em `results/estudo-empirico-grupo-5-relatorio.csv` e pertencem à matriz
definitiva.

### 3. Executar ou retomar o estudo completo

```bash
uv run python src/run_experiments.py docs/estudo-empirico-grupo-5-relatorio.json
```

O executor ignora os quatro casos de validação que já possuem `status=sucesso`. Cada novo resultado é sincronizado com o
disco, por isso o mesmo comando também retoma uma execução interrompida. Casos com `status=erro` são tentados novamente.

### 4. Gerar os gráficos

Execute este comando somente depois que as 140 combinações estiverem concluídas:

```bash
uv run python src/plot_results.py \
    results/estudo-empirico-grupo-5-relatorio.csv \
    --saida results/graficos
```

Os arquivos esperados são `results/graficos/speedup-escala-ordem.svg` e
`results/graficos/impacto-theta-remocao.svg`.

Os caminhos `resultados`, `rastros` e `arquivo_chaves` são resolvidos em relação ao arquivo JSON. A opção
`"continuar_apos_erro": true` mantém as demais combinações em execução depois de uma falha e ainda faz a CLI terminar
com código diferente de zero quando alguma tentativa falhar.

## Gráficos do relatório

O script `src/plot_results.py` lê o CSV amplo do estudo e gera os dois gráficos selecionados para o relatório em SVG. O
primeiro apresenta o speedup relativo por escala e ordem com `theta=0.99`; o segundo mostra o impacto de `theta` na
remoção, na maior escala que contém a variação completa de `theta` para as duas ordens e implementações.

Os arquivos gerados são `speedup-escala-ordem.svg` e `impacto-theta-remocao.svg`. O script usa somente execuções com
`status=sucesso`, calcula os speedups a partir dos pares com o mesmo rastro e repetição e apresenta a mediana sem ocultar
os pontos individuais.

## Verificação do projeto

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```
