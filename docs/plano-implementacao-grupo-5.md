# Plano de implementação do grupo 5

## 1. Objetivo e critérios de sucesso

O grupo 5 deve implementar, validar, medir e explicar uma árvore binária de busca balanceada aumentada. A solução recomendada é uma **árvore AVL aumentada** em Python 3.12. Cada nó manterá referências para os filhos e para o pai, além dos metadados necessários para balanceamento e consultas aumentadas.

O trabalho estará tecnicamente pronto quando todos estes critérios forem atendidos:

1. `insert`, `delete`, `search`, `rank`, `select` e `range_agg` obedecerem aos contratos definidos neste plano.
2. A propriedade de busca, o balanceamento AVL, os ponteiros `parent` e os metadados permanecerem corretos após toda mutação.
3. O driver consumir um `.trace` como fluxo, sem carregar o arquivo inteiro, e produzir uma linha somente para cada operação `S`.
4. A saída do driver coincidir com o `.expected` e tiver exatamente a mesma quantidade de linhas.
5. Testes próprios cobrirem `rank`, `select`, `range_agg` e os invariantes, pois o oráculo fornecido verifica diretamente apenas as buscas.
6. O benchmark registrar dados reais, parâmetros, ambiente, média, p50, p99, rotações e contagens efetivas de operações.
7. O grupo conseguir explicar cada invariante, rotação, decisão de projeto e diferença entre teoria e medição.

## 2. Evidências e escopo fixo

### 2.1 Configuração obrigatória do grupo 5

| Dimensão        | Valor          | Consequência para a implementação e o estudo                                              |
| --------------- | -------------- | ----------------------------------------------------------------------------------------- |
| Dataset         | `amzn`         | Usar `books_200M_uint32`, com chaves de 4 bytes.                                          |
| Distribuição    | `theta = 0.99` | Poucas chaves concentram muitos acessos. Tratar efeitos de cache como hipótese até medir. |
| Mistura nominal | `45:25:30`     | Inserções, remoções e buscas exercitam mutação e consulta continuamente.                  |
| Agregado        | máximo         | `range_agg(a, b)` retorna a maior chave no intervalo fechado `[a, b]`.                    |
| Ordem           | `ordenada`     | É o caso patológico para uma BST sem balanceamento e força a AVL a demonstrar seu valor.  |
| Semente         | `5`            | Usar `--semente 5` em todas as comparações oficiais.                                      |

### 2.2 Entregáveis que o plano precisa sustentar

- Código-fonte completo e instruções reproduzíveis.
- Relatório empírico com gráficos produzidos pelas medições reais.
- Justificativa da AVL, dos invariantes e da corretude das rotações.
- Apresentação oral de aproximadamente dez minutos.
- Dump organizado dos prompts e chats utilizados.

### 2.3 Constatações sobre o repositório atual

- A implementação da árvore ainda não existe.
- O gerador fornecido chama-se `workload_generator.py` no repositório, embora o PDF e exemplos didáticos usem o nome `gen_workload.py`.
- O script depende de NumPy para ler os dados SOSD e gerar a distribuição.
- O subcomando `verificar` compara linhas com `zip`. Portanto, ele não detecta sozinho todas as situações em que um arquivo possui linhas adicionais ou ausentes.
- O trace contém apenas `I`, `D` e `S`. O oráculo não exercita diretamente `rank`, `select` e `range_agg`.

Decisão operacional: os novos comandos e documentos usarão o nome real `workload_generator.py`. Não renomearemos nem duplicaremos o arquivo fornecido.

## 3. Decisões de projeto

### 3.1 Escolher AVL

A AVL é a opção recomendada porque mantém um limite de altura forte, tem comportamento determinístico e permite explicar cada caso de rotação com poucos conceitos. Uma treap exigiria uma segunda fonte de aleatoriedade. Uma árvore rubro-negra acrescentaria casos de correção de cores sem oferecer uma vantagem necessária para este trabalho em Python.

A carga `ordenada` torna essa escolha especialmente clara. Uma BST ingênua tende a altura linear. A AVL mantém altura logarítmica por meio de rotações locais.

### 3.2 Usar duas classes, sem hierarquia artificial

```text
Node
  key
  left
  right
  parent
  height
  size
  subtree_max

AugmentedAVLTree
  root
  rotation_count
  insert / delete / search
  rank / select / range_agg
  assert_valid
```

`Node` será uma `dataclass` com `slots=True` e `eq=False`. Os slots reduzem memória por nó, o que importa em larga escala. A igualdade por identidade evita comparações recursivas acidentais. O campo `parent` ficará fora da representação textual para impedir ciclos no `repr`.

`AugmentedAVLTree` será dona da raiz e do contador de rotações. Não criaremos classe abstrata, fábrica, estratégia de balanceamento ou agregado genérico. Há uma única estrutura e um único agregado atribuídos ao grupo.

### 3.3 Usar `parent` como parte do invariante

O atributo solicitado será usado para subir iterativamente até a raiz após inserções e remoções. Ele não será apenas um campo informativo.

As regras obrigatórias são:

- `tree.root.parent is None`.
- Se `node.left` existe, então `node.left.parent is node`.
- Se `node.right` existe, então `node.right.parent is node`.
- Nenhum nó pode aparecer duas vezes nem formar ciclo.
- Toda rotação deve atualizar filhos, pais e a raiz antes de recalcular metadados.

O método interno `replace_subtree(old_root, new_root)` concentrará o caso delicado de substituir uma subárvore no pai ou na raiz. Essa pequena abstração elimina duplicação e reduz o risco de esquecer um ponteiro `parent`.

### 3.4 Centralizar todos os metadados em `Node.refresh()`

Somente um método recalculará os três resumos derivados:

```text
height = 1 + max(height(left), height(right))
size = 1 + size(left) + size(right)
subtree_max = max(key, subtree_max(left), subtree_max(right))
```

Uma rotação atualizará primeiro o nó que desceu e depois o nó que subiu. Essa ordem é obrigatória porque o segundo resumo depende do primeiro.

### 3.5 Preferir operações iterativas

`search`, `insert`, `delete`, `rank`, `select` e o rebalanceamento serão iterativos. O ponteiro `parent` torna a subida explícita e evita manter pilhas auxiliares. A recursão ficará restrita ao validador de testes, no qual a altura AVL é logarítmica e a formulação recursiva é mais auditável.

### 3.6 Explorar a propriedade específica do máximo

Para o grupo 5, o valor agregado é a própria chave. Assim, o máximo de `[a, b]` é a maior chave menor ou igual a `b`, desde que ela também seja maior ou igual a `a`.

`range_agg` fará uma busca de predecessor em um único caminho. O método poderá encerrar cedo quando `subtree_max < a`. Isso produz custo `O(log n)` em uma AVL, mais forte que o limite geral `O(log n + k)` descrito para agregações arbitrárias.

Mesmo com essa simplificação, `subtree_max` continuará obrigatório, será recalculado em todas as rotações e será verificado por testes. O relatório deve explicar com transparência que o caso "máximo da própria chave" permite uma consulta mais simples. Não adicionaremos `subtree_min`, limites duplicados ou uma infraestrutura genérica de monóides.

## 4. Contratos públicos

| Operação          | Entrada    | Saída             | Casos de borda                                                                    |
| ----------------- | ---------- | ----------------- | --------------------------------------------------------------------------------- |
| `insert(k)`       | `int`      | `True` se inseriu | Chave repetida retorna `False` e não altera a árvore.                             |
| `delete(k)`       | `int`      | `True` se removeu | Chave ausente retorna `False` e não altera a árvore.                              |
| `search(k)`       | `int`      | `bool`            | Árvore vazia retorna `False`.                                                     |
| `rank(k)`         | `int`      | `int`             | Conta somente chaves estritamente menores que `k`, mesmo quando `k` está ausente. |
| `select(i)`       | `int`      | `int`             | Índice baseado em zero. Índice fora de `[0, len(tree))` levanta `IndexError`.     |
| `range_agg(a, b)` | dois `int` | `int` ou `None`   | Intervalo fechado. `a > b` levanta `ValueError`. Intervalo vazio retorna `None`.  |
| `len(tree)`       | nenhum     | `int`             | Retorna zero para árvore vazia.                                                   |
| `assert_valid()`  | nenhum     | `None`            | Levanta `AssertionError` com diagnóstico no primeiro invariante violado.          |

Os contratos evitam sentinelas numéricos. `None` representa ausência em `range_agg`, pois zero é uma chave válida em `uint32`.

## 5. Algoritmos e ordem de implementação

### 5.1 Nó e atualização local

Implementar primeiro `Node` e `refresh()`.

Critérios de avanço:

- Uma folha começa com `height = 1`, `size = 1` e `subtree_max = key`.
- Um nó recalcula os três campos corretamente a partir dos filhos.
- O pai de cada filho usado no teste aponta de volta para o nó.

### 5.2 Busca e consultas básicas

Implementar `search` e `len` antes das mutações completas. A busca percorre um único caminho e não altera estado.

Critérios de avanço:

- Busca em árvore vazia retorna `False`.
- Busca encontra raiz, folha e nó interno.
- Busca de chave ausente termina em `None`.

### 5.3 Rotações com ponteiros parentais

Implementar `replace_subtree`, rotação à esquerda e rotação à direita. Cada rotação deve seguir esta ordem:

1. Guardar o pivô, a subárvore transferida e o antigo pai.
2. Ligar o pivô ao antigo pai ou torná-lo raiz.
3. Mover a subárvore intermediária e atualizar seu `parent`, quando existir.
4. Ligar o nó que desceu ao pivô e atualizar seu `parent`.
5. Executar `refresh()` no nó que desceu.
6. Executar `refresh()` no pivô.
7. Incrementar `rotation_count`.
8. Retornar a nova raiz local.

Testar separadamente rotações simples e, por composição, os casos LR e RL.

Critérios de avanço:

- O percurso em ordem não muda depois da rotação.
- A raiz local e a raiz global têm pais corretos.
- Nenhuma subárvore transferida perde o vínculo com o novo pai.
- Altura, tamanho e máximo ficam corretos nos nós afetados.

### 5.4 Inserção e subida até a raiz

A inserção localizará iterativamente o ponto vazio. O novo nó receberá `parent` no momento da ligação. Em seguida, o algoritmo subirá pelos ancestrais, chamando `refresh()` e rebalanceando cada nó.

Depois de uma rotação, a subida continuará a partir do pai da nova raiz local. Isso evita revisitar nós ou encerrar cedo demais.

Critérios de avanço:

- Sequências LL, RR, LR e RL produzem árvores válidas.
- A sequência `10, 20, 30, 40, 50, 25` mantém altura AVL.
- Inserção `ordenada` de pelo menos 10 mil chaves não causa `RecursionError`.
- Duplicatas não aumentam `size` nem alteram `parent`.

### 5.5 Remoção

A remoção tratará três casos:

1. Folha, substituindo o nó por `None`.
2. Um filho, substituindo o nó pelo filho.
3. Dois filhos, copiando a chave do sucessor e removendo o sucessor, que possui no máximo um filho.

Antes da substituição física, guardar o pai a partir do qual o rebalanceamento começará. Depois da ligação, limpar as referências do nó removido para tornar erros de reutilização visíveis em testes.

Critérios de avanço:

- Remoção de folha, nó com um filho, nó com dois filhos e raiz preserva todos os invariantes.
- O filho promovido recebe o pai correto.
- A nova raiz sempre recebe `parent = None`.
- Remoção ausente é uma operação nula.
- Remoções que provocam rotações simples e duplas passam no validador.

### 5.6 `rank` e `select`

`rank(k)` acumulará `size(left) + 1` sempre que avançar à direita. `select(i)` comparará o índice restante com `size(left)` e descartará uma subárvore inteira a cada passo.

Critérios de avanço:

- Para `[10, 20, 30, 40]`, `rank(30) == 2`.
- `rank` funciona para valores abaixo do mínimo, entre chaves e acima do máximo.
- Para a mesma árvore, `select(0) == 10` e `select(3) == 40`.
- Todo `select(i)` válido satisfaz `rank(select(i)) == i`.

### 5.7 `range_agg`

Percorrer a árvore procurando a maior chave `<= b`. Quando uma chave candidata estiver no intervalo, guardá-la e tentar uma chave maior na direita. Se a chave atual for maior que `b`, seguir à esquerda. Se for menor que `a`, seguir à direita. Se o máximo da subárvore for menor que `a`, encerrar sem resultado.

Critérios de avanço:

- As duas pontas do intervalo são inclusivas.
- Intervalo abaixo do mínimo, acima do máximo ou entre duas chaves retorna `None` quando apropriado.
- `range_agg(k, k)` retorna `k` somente quando a chave existe.
- Resultados coincidem com `max(value for value in reference if a <= value <= b)` em testes diferenciais.

### 5.8 Validador estrutural

`assert_valid()` fará uma travessia independente e verificará:

1. Ausência de ciclos e nós repetidos por identidade.
2. Limites estritos da BST.
3. Coerência de todos os `parent`.
4. `root.parent is None`.
5. Altura calculada.
6. Fator AVL entre `-1` e `1`.
7. Tamanho calculado.
8. Máximo calculado.
9. `len(tree)` igual ao tamanho calculado da raiz.

Esse método será usado em testes e smoke tests, nunca dentro da região cronometrada do benchmark.

## 6. Organização mínima dos arquivos

```text
balanced_search_tree/
├── src/
│   ├── augmented_avl.py
│   ├── run_trace.py
│   ├── benchmark.py
│   ├── helper_functions.py
│   └── workload_generator.py
├── pyproject.toml
├── tests/
│   ├── test_augmented_avl.py
│   ├── test_benchmark.py
│   ├── test_run_trace.py
│   └── test_workload_generator.py
├── results/                        # gerado, não versionar cargas grandes
└── docs/
    ├── project-instructions.pdf
    ├── plano-implementacao-grupo-5.md
    └── plano-implementacao-grupo-5.html
```

Responsabilidades:

- `src/augmented_avl.py` contém somente `Node` e `AugmentedAVLTree`.
- `src/run_trace.py` contém o CLI de corretude e a escrita de `candidate.out`.
- `src/benchmark.py` reutiliza a mesma árvore, mede operações e grava CSV. A referência pequena fica neste arquivo.
- `src/helper_functions.py` contém as bisseções didáticas e o parser compartilhado em PT-BR.
- `test_augmented_avl.py` concentra testes determinísticos e diferenciais.
- `pyproject.toml` define Python `>=3.12`, NumPy, pytest, Ruff e mypy com linha máxima de 120 caracteres.

Não criaremos pacote, subpacotes ou interfaces abstratas antes de surgir duplicação real.

## 7. Driver do trace e integração com o oráculo

### 7.1 Contrato do driver

O CLI proposto receberá:

```text
python src/run_trace.py INPUT.trace --saida candidate.out --validar-a-cada 0
```

Fluxo:

1. Abrir entrada e saída com gerenciadores de contexto.
2. Ignorar comentários iniciados por `#` e linhas vazias.
3. Separar operação e chave.
4. Converter a chave para `int`.
5. Executar `insert`, `delete` ou `search`.
6. Escrever somente `<key> FOUND` ou `<key> NOT_FOUND` para `S`.
7. Contar linhas por operação e rejeitar códigos desconhecidos com número de linha.
8. Opcionalmente executar `assert_valid()` a cada N mutações durante depuração.

O driver será streaming. Ele não guardará o trace nem a saída em listas.

### 7.2 Smoke test reproduzível

```bash
python src/workload_generator.py gerar \
    --sintetico 10000 \
    --operacoes 50000 \
    --universo 10000 \
    --mistura 45:25:30 \
    --theta 0.99 \
    --ordem-insercao ordenada \
    --semente 5 \
    --saida g5-smoke

python src/run_trace.py g5-smoke.trace --saida candidate.out

python src/workload_generator.py verificar \
    --esperado g5-smoke.expected \
    --candidato candidate.out
```

Depois de `verificar`, comparar também a contagem de linhas de `candidate.out` e `g5-smoke.expected`. Essa checagem compensa a limitação do `zip` no verificador atual.

### 7.3 Piloto com dados reais

```bash
python src/workload_generator.py gerar \
    --chaves data/books_200M_uint32 \
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

O relatório deve declarar o uso de `--carga-maxima`. Um piloto limitado não pode ser descrito como execução do conjunto completo.

## 8. Estratégia de testes

O desenvolvimento seguirá fatias verticais pequenas. Cada comportamento recebe um teste público, a implementação mínima e uma nova execução dos testes antes do próximo comportamento.

### 8.1 Testes determinísticos

- Estado inicial e metadados de uma folha.
- `search` em árvore vazia, presente e ausente.
- Quatro padrões de rotação em inserção.
- Ponteiros `parent` após cada rotação.
- Inserção repetida.
- Remoção ausente.
- Remoção de folha, um filho, dois filhos e raiz.
- Casos de rebalanceamento causados por remoção.
- `rank` com chave presente e ausente.
- `select` válido e inválido.
- `range_agg` com fronteiras, vazio e intervalo invertido.

### 8.2 Teste diferencial

Usar `random.Random(5)` para gerar uma sequência determinística de inserções e remoções. Manter um `set[int]` como referência. Após cada mutação:

1. Chamar `assert_valid()`.
2. Comparar `len(tree)` com o conjunto.
3. Comparar o percurso ordenado usado apenas no teste com `sorted(reference)`.
4. Comparar buscas amostradas.
5. Comparar `rank`, `select` e intervalos amostrados com a lista ordenada.

Esse teste não simula a AVL. Ele compara resultados observáveis por uma representação independente.

### 8.3 Teste de integração

Gerar um rastro sintético pequeno com semente 5, executar `run_trace.py`, rodar `verificar` e conferir a contagem de linhas. O teste deve usar os programas reais, sem simulações do gerador ou da árvore.

### 8.4 Verificações estáticas

Executar:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

## 9. Benchmark e coleta de dados

### 9.1 Separar corretude de medição

Primeiro validar a saída. Depois medir a mesma implementação sem `assert_valid()` na região cronometrada. Erros de corretude invalidam uma execução de desempenho.

### 9.2 Medir a operação, não o arquivo

Usar `time.perf_counter_ns()` imediatamente antes e depois de cada chamada da árvore. Parsing, leitura do arquivo e escrita da saída ficarão fora do tempo por operação. O tempo total de parede será registrado separadamente para mostrar o custo completo do pipeline.

As latências serão armazenadas por tipo em `array('Q')`, da biblioteca padrão. Isso usa 8 bytes por amostra e evita o custo de milhões de objetos `int` em listas. Se a execução final exceder a memória disponível, o plano de medição deverá declarar e usar uma amostra determinística para percentis, mantendo contagens e tempos totais exatos.

### 9.3 Registro CSV

Cada linha de resultado conterá pelo menos:

| Campo                                  | Conteúdo                                    |
| -------------------------------------- | ------------------------------------------- |
| `run_id`                               | Identificador estável da execução.          |
| `implementation`                       | `avl` ou `sorted_list`.                     |
| `dataset`                              | Sintético ou caminho/identificador do amzn. |
| `max_load`                             | Zero ou limite realmente usado.             |
| `universe` e `ops_requested`           | Parâmetros solicitados.                     |
| `insert`, `delete`, `search`           | Contagens efetivamente observadas.          |
| `theta`, `mix`, `insert_order`, `seed` | Configuração completa.                      |
| `operation`                            | Tipo medido.                                |
| `mean_ns`, `p50_ns`, `p99_ns`          | Resumo de latência.                         |
| `wall_time_ns`                         | Tempo total da execução.                    |
| `rotations`                            | Rotações simples executadas.                |
| `final_size` e `final_height`          | Estado final da árvore.                     |
| `python`, implementação e compilador   | Runtime Python usado na medição.            |
| `platform`, `machine`                  | Sistema e arquitetura da máquina.           |
| `repetition`                           | Número da repetição.                        |

O comando unitário `benchmark.py` mantém esse formato estreito, com uma linha para cada tipo de operação. O executor do
estudo, `run_experiments.py`, achata as três operações em uma única linha por execução. Seus campos usam os prefixos
`insert_`, `delete_` e `search_`, além de `status` e `error`. Isso torna cada linha um checkpoint completo e permite
retomar o estudo pelo `run_id` sem juntar três registros parciais.

### 9.4 Configuração e retomada do estudo

O arquivo `docs/estudo-empirico-grupo-5-piloto.json` preserva a matriz preliminar de 320 casos. O arquivo
`docs/estudo-empirico-grupo-5-relatorio.json` reúne os 140 casos definitivos. Cada objeto do array `experimentos` aceita
um escalar ou uma lista para cada parâmetro. O executor normaliza escalares como listas de um item e aplica
`itertools.product` dentro do objeto. Objetos separados mantêm `operacoes = universo` em cada escala, sem criar
combinações cruzadas sem significado entre esses dois parâmetros.

A configuração definitiva usa 1.000, 10.000, 100.000 e 1.000.000 de operações com `theta = 0,99`. A escala de 100.000
também contém a variação completa de `theta`. Assim, a mesma linha de `theta = 0,99` participa dos estudos de escala e
sensibilidade, sem duplicar casos. O arquivo `docs/estudo-empirico-grupo-5-validacao-1m.json` contém os quatro casos da
primeira repetição da escala máxima. Ele usa o mesmo CSV e diretório de rastros do estudo definitivo, de modo que uma
execução posterior da matriz completa retome o trabalho já validado.

Cada execução possui um `run_id` determinístico. Depois do benchmark, a linha é acrescentada ao CSV e sincronizada com
o disco. Uma retomada ignora somente identificadores que já tenham uma linha com `status=sucesso`. Falhas permanecem no
histórico com a mensagem em `error` e podem ser tentadas novamente após a correção da causa.

### 9.5 Baseline mínima

Implementar `SortedListSet` dentro de `benchmark.py` usando `list` e `bisect` da biblioteca padrão. Ela manterá chaves únicas e oferecerá a mesma superfície observável necessária ao benchmark.

- `search` e `rank` usam `bisect_left`.
- `select` usa índice direto.
- `insert` e `delete` deslocam elementos e expõem custo linear.
- `range_agg` usa a posição de `bisect_right(b) - 1` e verifica `a`.

Não criaremos uma segunda hierarquia de classes. O benchmark dependerá apenas dos mesmos nomes de métodos.

### 9.6 Matriz experimental

| Estudo           | Valores controlados                       | Variável                                                          | Saída principal                   |
| ---------------- | ----------------------------------------- | ----------------------------------------------------------------- | --------------------------------- |
| Escala           | Grupo 5 completo                          | `universe` em `10³`, `10⁴`, `10⁵`, `10⁶` ou quatro ordens viáveis | média, p50, p99 por operação      |
| Enviesamento     | amzn, `45:25:30`, `ordenada`, semente 5   | `theta` em `0.0`, `0.6`, `0.99`, `1.2`                            | latência, cauda e rotações        |
| Ordem            | amzn, `45:25:30`, `theta=0.99`, semente 5 | `ordenada` e `embaralhada`                                        | altura, rotações e latência       |
| Baseline         | Mesmos traces                             | AVL e lista ordenada                                              | ponto de cruzamento               |
| Teoria e prática | Mesma máquina e metodologia               | tamanho                                                           | curva medida contra `log n` e `n` |

Para o estudo de escala, começar com `ops = universe`. Isso mantém o número de inserções abaixo das chaves inseríveis na maior parte das execuções e reduz a distorção da mistura nominal.

O comando de referência com 50 milhões de operações e universo de 10 milhões pode esgotar as 9 milhões de chaves inseríveis. O gerador converte tentativas posteriores de inserção em buscas. Por isso, o relatório deverá usar as contagens efetivas do trace, não assumir que a proporção final permaneceu exatamente `45:25:30`.

### 9.7 Repetições e ambiente

- Fazer uma execução piloto não medida para validar caminhos, espaço e duração.
- Fazer pelo menos cinco repetições medidas quando o custo permitir.
- Criar uma árvore nova em cada repetição.
- Manter coleta de lixo, versão do Python e configuração do sistema constantes.
- Evitar outras cargas relevantes na máquina.
- Registrar decisões de warm-up e qualquer amostragem de percentis.
- Não interpretar variações pequenas sem dispersão ou repetição suficiente.

## 10. Fases de execução

### Fase 0. Preparar o projeto

Entregas:

- `pyproject.toml` com Python 3.12, NumPy, pytest e Ruff.
- `.gitignore` para ambiente virtual, caches, traces grandes, candidates e `results/` gerados.
- Comando sintético do grupo 5 validado.

Saída verificável: o gerador produz `.trace` e `.expected` com seed 5.

### Fase 1. Construir o núcleo estrutural

Entregas:

- `Node` com `parent` e metadados.
- `AugmentedAVLTree` com busca, rotações e inserção.
- Validador estrutural.
- Testes LL, RR, LR, RL e sequência `ordenada`.

Saída verificável: todos os testes de inserção passam e `assert_valid()` aceita cada estado.

### Fase 2. Completar mutações e consultas

Entregas:

- Remoção completa.
- `rank`, `select` e `range_agg`.
- Testes determinísticos e diferenciais.

Saída verificável: sequência aleatória determinística coincide com `set` e lista ordenada.

### Fase 3. Integrar o trace

Entregas:

- `run_trace.py` streaming.
- Diagnóstico de linha inválida.
- Candidate compatível com o oráculo.
- Checagem explícita da contagem de respostas.

Saída verificável: smoke test retorna `[OK]` e os dois arquivos de resposta têm o mesmo número de linhas.

### Fase 4. Instrumentar o benchmark

Entregas:

- `benchmark.py` com CSV e metadados de ambiente.
- `SortedListSet` com `bisect`.
- Latências por operação, tempo total, rotações, tamanho e altura.

Saída verificável: um benchmark pequeno gera CSV completo e reproduzível sem alterar resultados de busca.

### Fase 5. Executar a matriz experimental

Ordem recomendada:

1. Escala sintética para encontrar limites e erros de instrumentação.
2. Piloto amzn com `--carga-maxima` declarado.
3. Escala oficial viável na máquina.
4. Variação de `theta`.
5. Comparação `ordenada` e `embaralhada`.
6. Comparação com baseline.
7. Repetições necessárias para estabilizar conclusões.

Saída verificável: CSVs brutos, logs de comando e metadados suficientes para regenerar todos os gráficos.

### Fase 6. Produzir relatório e defesa

Entregas:

- Gráficos derivados somente dos CSVs versionados ou arquivados.
- Interpretação começando pela observação, seguida da explicação teórica.
- Justificativa da AVL e das alternativas descartadas.
- Argumento informal de corretude para rotações e metadados.
- Roteiro de defesa e respostas às perguntas prováveis.
- Dump organizado de prompts, com identificação do apoio utilizado.

Saída verificável: cada número do relatório aponta para uma execução reproduzível.

## 11. Argumento de corretude que o grupo deverá dominar

### Ordenação

Inserção e busca escolhem esquerda ou direita pela comparação. A remoção com dois filhos usa o sucessor, que é a menor chave da subárvore direita. As rotações preservam a ordem em percurso simétrico porque apenas reorganizam relações entre subárvores cujos intervalos de chaves já são compatíveis.

### Balanceamento

Após uma mutação, somente os ancestrais do ponto alterado podem ter altura diferente. O ponteiro `parent` permite visitar exatamente esse caminho. Em cada ancestral, a AVL recalcula a altura e aplica uma rotação simples ou dupla quando o fator sai de `[-1, 1]`.

### Metadados

`refresh()` calcula cada resumo somente a partir da chave e de filhos já atualizados. Após uma rotação, o nó que desce é atualizado primeiro. Em seguida, o pivô usa o resumo correto desse filho. A subida até a raiz repete esse argumento local em todos os ancestrais afetados.

### Ponteiros parentais

Cada mudança de filho atualiza a referência inversa no mesmo bloco lógico. `replace_subtree` cobre a ligação com o antigo pai ou com a raiz. As rotações cobrem a subárvore transferida e o nó que desce. Portanto, cada aresta descendente tem a aresta ascendente correspondente.

### Consultas aumentadas

`rank` e `select` usam `size` para descartar subárvores inteiras. `range_agg` usa a ordem da BST para manter a melhor chave até `b` e usa `subtree_max` para rejeitar uma subárvore que não alcança `a`. Como a altura AVL é logarítmica, essas consultas visitam um caminho logarítmico.

## 12. Riscos e controles

| Risco                                                            | Controle                                                                                       |
| ---------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Esquecer `parent` em rotação ou remoção                          | `replace_subtree`, ordem explícita de ligação e `assert_valid()` após cada mutação nos testes. |
| Atualizar metadados na ordem errada                              | `refresh()` único e teste de todas as rotações.                                                |
| Oráculo aprovar arquivos truncados                               | Comparar contagens de linhas além de executar `verificar`.                                     |
| Considerar `rank`, `select` e `range_agg` corretos sem evidência | Testes diferenciais independentes do trace.                                                    |
| Medir parsing em vez da árvore                                   | Cronometrar somente a chamada da operação.                                                     |
| Estourar memória com latências                                   | `array('Q')` e amostragem determinística documentada apenas quando necessária.                 |
| Mistura efetiva divergir de `45:25:30`                           | Contar operações reais e relatar esgotamento de chaves inseríveis.                             |
| Confundir piloto com conjunto completo                           | Registrar `max_load`, arquivo e universo em cada linha do CSV.                                 |
| Otimizar antes de medir                                          | Implementar primeiro a versão simples, perfilar e alterar somente gargalos demonstrados.       |
| Código curto ficar difícil de explicar                           | Preferir nomes explícitos, métodos pequenos e uma única responsabilidade por arquivo.          |

## 13. Checklist de conclusão

### Implementação

- [ ] `Node` usa `slots`, identidade e atributo `parent`.
- [ ] A raiz tem pai nulo e todo filho aponta para seu pai.
- [ ] `refresh()` é o único lugar que calcula altura, tamanho e máximo.
- [ ] Inserção e remoção sobem pelos pais e mantêm a AVL.
- [ ] As seis operações públicas obedecem aos contratos.
- [ ] O validador detecta ordem, ciclos, pais, altura, balanço, tamanho e máximo.

### Verificação

- [ ] Testes de quatro rotações passam.
- [ ] Testes de todos os casos de remoção passam.
- [ ] Testes diferenciais passam com seed 5.
- [ ] Trace sintético passa no oráculo.
- [ ] Candidate e expected têm a mesma quantidade de linhas.
- [ ] Ruff e pytest passam.

### Experimentos

- [ ] Quatro ordens de grandeza foram medidas ou o limite da máquina foi documentado.
- [ ] Os quatro valores de `theta` foram comparados.
- [ ] As ordens `ordenada` e `embaralhada` foram comparadas.
- [ ] AVL e lista ordenada foram comparadas com o mesmo trace.
- [ ] Média, p50 e p99 foram registrados por operação.
- [ ] Máquina, Python, parâmetros, repetições e warm-up foram registrados.
- [ ] Contagens efetivas de I, D e S foram registradas.

### Entrega e defesa

- [ ] Todo gráfico deriva de dados reais preservados.
- [ ] A justificativa explica AVL, `parent`, metadados e rotações.
- [ ] O grupo consegue explicar por que `range_agg` é especialmente simples para máximo de chaves.
- [ ] O grupo consegue explicar por que a ordem `ordenada` prejudica a referência.
- [ ] O grupo consegue explicar qualquer crescimento do p99 com evidência, sem afirmar hipóteses como fatos.
- [ ] Comandos de reprodução e dump de prompts estão organizados.

## 14. Primeira sequência executável

1. Criar `pyproject.toml` e o teste de uma folha.
2. Implementar `Node`, `refresh()` e `assert_valid()` mínimo.
3. Implementar rotações com `parent` e testar LL, RR, LR e RL.
4. Implementar inserção iterativa e testar a sequência `ordenada`.
5. Implementar remoção e seus quatro casos estruturais.
6. Implementar `search`, `rank`, `select` e `range_agg`.
7. Executar o teste diferencial com seed 5.
8. Gerar o smoke trace, executar o driver e conferir o oráculo e as contagens.
9. Instrumentar o benchmark somente depois da corretude.
10. Executar piloto, estimar recursos e então fixar a matriz final compatível com a máquina do grupo.
