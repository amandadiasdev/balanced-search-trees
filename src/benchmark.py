"""Mede as operações da AVL aumentada e da lista ordenada sobre um rastro."""

import csv
import platform
from array import array
from pathlib import Path
from time import perf_counter_ns

import numpy as np

from augmented_avl import AugmentedAVLTree
from helper_functions import PortugueseArgumentParser, bisect_left, bisect_right
from run_trace import iter_trace

FIELD_NAMES = [
    # Identificando inequivocamente a repetição, a implementação e a origem dos dados.
    "run_id",
    "implementation",
    "dataset",
    "max_load",
    # Preservando os parâmetros da carga para que o resultado possa ser reproduzido.
    "universe",
    "ops_requested",
    # Registrando contagens efetivas, que podem diferir da mistura solicitada ao gerador.
    "insert",
    "delete",
    "search",
    "mix",
    "theta",
    "insert_order",
    "seed",
    # Descrevendo a operação resumida e suas estatísticas de latência.
    "operation",
    "count",
    "mean_ns",
    "p50_ns",
    "p99_ns",
    "wall_time_ns",
    # Guardando propriedades finais da estrutura para interpretar custo e balanceamento.
    "rotations",
    "final_size",
    "final_height",
    # Capturando o ambiente de execução, que influencia medições temporais.
    "python",
    "python_implementation",
    "python_compiler",
    "platform",
    "machine",
    "repetition",
]


class SortedListSet:
    """Maintain unique integer keys in a sorted Python list."""

    def __init__(self) -> None:
        """Create an empty sorted-list baseline."""
        self.values: list[int] = []
        self.rotation_count = 0

    def __len__(self) -> int:
        """Return the number of stored keys."""
        return len(self.values)

    def insert(self, key: int) -> bool:
        """Insert a unique key in sorted order.

        Args:
            key: Integer key to insert.

        Returns:
            True when inserted, otherwise False.
        """
        # Localizando a primeira posição em que key pode aparecer sem violar a
        # ordenação. A busca é logarítmica, embora a inserção física seja linear.
        index = bisect_left(self.values, key)
        # A lista mantém uma única ocorrência de cada chave, reproduzindo o
        # mesmo contrato de conjunto adotado pela AVL.
        if index < len(self.values) and self.values[index] == key:
            # A borda esquerda aponta para a chave existente quando há duplicata.
            return False
        # list.insert desloca os elementos posteriores e mantém a lista ordenada.
        self.values.insert(index, key)
        return True

    def delete(self, key: int) -> bool:
        """Remove a key when present.

        Args:
            key: Integer key to remove.

        Returns:
            True when removed, otherwise False.
        """
        # A mesma borda usada na inserção é a única posição em que key poderia existir.
        index = bisect_left(self.values, key)
        if index == len(self.values) or self.values[index] != key:
            # Chegar ao fim ou encontrar outro valor prova que a chave está ausente.
            return False
        # Remover por índice evita uma segunda busca pelo valor.
        self.values.pop(index)
        return True

    def search(self, key: int) -> bool:
        """Report whether a key is present.

        Args:
            key: Integer key to locate.

        Returns:
            True when present, otherwise False.
        """
        # A ordenação transforma presença em uma única comparação após a bisseção.
        index = bisect_left(self.values, key)
        return index < len(self.values) and self.values[index] == key

    def rank(self, key: int) -> int:
        """Count keys strictly smaller than a key.

        Args:
            key: Integer boundary.

        Returns:
            Number of smaller stored keys.
        """
        # A posição de inserção à esquerda coincide exatamente com a quantidade
        # de elementos estritamente menores que key.
        return bisect_left(self.values, key)

    def select(self, index: int) -> int:
        """Return the key at a zero-based position.

        Args:
            index: Zero-based sorted position.

        Returns:
            Key at the requested position.

        Raises:
            IndexError: If the index is outside the baseline.
        """
        if index < 0 or index >= len(self.values):
            # Rejeitando índices negativos para manter o mesmo contrato da AVL,
            # em vez de aceitar a indexação reversa nativa das listas Python.
            raise IndexError(f"index {index} is outside a baseline of size {len(self.values)}")
        # Como a lista já está ordenada, a posição física é também a ordem estatística.
        return self.values[index]

    def range_agg(self, lower: int, upper: int) -> int | None:
        """Return the maximum key in an inclusive interval.

        Args:
            lower: Inclusive lower bound.
            upper: Inclusive upper bound.

        Returns:
            Greatest key in the interval, or None when empty.

        Raises:
            ValueError: If the lower bound is greater than the upper bound.
        """
        if lower > upper:
            raise ValueError(f"o limite inferior {lower} é maior que o limite superior {upper}")
        # bisect_right devolve a posição após todos os valores iguais a upper.
        # Subtrair um produz o maior índice cujo valor pode pertencer ao intervalo.
        index = bisect_right(self.values, upper) - 1
        # Ainda é preciso confirmar o limite inferior. Sem essa checagem, o
        # predecessor de upper poderia estar completamente abaixo de lower.
        return self.values[index] if index >= 0 and self.values[index] >= lower else None


def read_trace_metadata(trace_path: Path) -> dict[str, str]:
    """Read key-value metadata from the trace header.

    Args:
        trace_path: Trace whose first comment contains generator parameters.

    Returns:
        Header values keyed by parameter name.
    """
    # O cabeçalho fica no início do trace. Ler como fluxo evita carregar a carga
    # inteira somente para recuperar seus parâmetros experimentais.
    with trace_path.open(encoding="utf-8") as trace_file:
        for raw_line in trace_file:
            # Removendo espaços e a quebra de linha antes de classificar o conteúdo.
            line = raw_line.strip()
            if not line:
                # Linhas vazias anteriores ao cabeçalho não encerram a procura.
                continue
            if not line.startswith("#"):
                # A primeira operação indica que não existe cabeçalho reconhecível.
                return {}
            # Cada campo possui a forma nome=valor. split com limite um preserva
            # eventuais sinais de igualdade que pertençam ao próprio valor.
            return dict(field.split("=", 1) for field in line[1:].split() if "=" in field)
    # Um arquivo vazio não oferece metadados.
    return {}


def summarize_latencies(values: array[int]) -> tuple[int, int, int]:
    """Calculate mean, p50, and p99 from compact latency storage.

    Args:
        values: Unsigned integer latencies in nanoseconds.

    Returns:
        Rounded mean, p50, and p99 latency values.
    """
    if not values:
        # Manter zeros permite produzir as três linhas do CSV mesmo quando uma
        # operação não apareceu em uma carga pequena.
        return 0, 0, 0
    # frombuffer cria uma visão NumPy sobre o array compacto sem copiar todas as amostras.
    samples = np.frombuffer(values, dtype=np.uint64)
    # method="nearest" seleciona uma observação real para cada percentil. O
    # arredondamento final mantém o esquema CSV integral em nanossegundos.
    return (
        round(float(samples.mean())),
        round(float(np.percentile(samples, 50, method="nearest"))),
        round(float(np.percentile(samples, 99, method="nearest"))),
    )


def benchmark_trace(
    trace_path: Path,
    implementation: str,
    dataset: str,
    max_load: int,
    repetition: int,
) -> list[dict[str, str | int]]:
    """Measure one implementation while streaming a trace.

    Args:
        trace_path: Workload trace to execute.
        implementation: Either avl or sorted-list.
        dataset: Human-readable dataset identifier.
        max_load: Dataset load limit used to create the trace.
        repetition: Repetition number for the run.

    Returns:
        One CSV-ready row for each operation type.

    Raises:
        ValueError: If the implementation name is unknown.
    """
    # As duas estruturas expõem o mesmo conjunto de operações. Selecioná-las
    # aqui mantém o restante do laço de medição idêntico e comparável.
    if implementation == "avl":
        structure: AugmentedAVLTree | SortedListSet = AugmentedAVLTree()
    elif implementation == "sorted-list":
        structure = SortedListSet()
    else:
        # Falhar antes da medição evita gerar um CSV aparentemente válido para
        # uma implementação inexistente.
        raise ValueError(f"implementação desconhecida {implementation!r}")

    # array("Q") armazena inteiros sem sinal de 64 bits com custo menor que uma
    # lista de objetos Python. Cada operação recebe sua própria série temporal.
    latencies = {operation: array("Q") for operation in ("I", "D", "S")}
    # Medindo cada operação isoladamente. A leitura e o parsing do trace ficam
    # fora desse intervalo, mas entram no wall_time do experimento completo.
    wall_start = perf_counter_ns()
    for operation, key in iter_trace(trace_path):
        # O cronômetro começa depois que a linha já foi lida e convertida. Assim,
        # a amostra mede a estrutura, não o parsing do trace.
        operation_start = perf_counter_ns()
        if operation == "I":
            structure.insert(key)
        elif operation == "D":
            structure.delete(key)
        else:
            structure.search(key)
        # A diferença é anexada somente à série da operação executada.
        latencies[operation].append(perf_counter_ns() - operation_start)
    # wall_time inclui o percurso completo do trace e complementa as amostras individuais.
    wall_time = perf_counter_ns() - wall_start
    if isinstance(structure, AugmentedAVLTree):
        # A baseline não possui invariantes estruturais. Para a AVL, validamos a
        # árvore após a região medida para não contaminar as latências.
        structure.assert_valid()

    # Recuperando os parâmetros somente depois da medição pelo mesmo motivo:
    # I/O de metadados não deve integrar o tempo das operações.
    metadata = read_trace_metadata(trace_path)
    # Registrando as contagens efetivas porque o gerador pode adaptar a mistura
    # quando não há mais chaves válidas para determinada operação.
    counts = {operation: len(values) for operation, values in latencies.items()}
    # A altura só existe na AVL. Zero representa tanto a baseline quanto uma AVL vazia.
    final_height = structure.root.height if isinstance(structure, AugmentedAVLTree) and structure.root else 0
    # common reúne os campos que se repetirão nas três linhas de operação,
    # evitando divergências acidentais entre insert, delete e search.
    common: dict[str, str | int] = {
        "run_id": f"{trace_path.stem}-{implementation}-r{repetition}",
        "implementation": implementation,
        "dataset": dataset,
        "max_load": max_load,
        "universe": metadata.get("universe", ""),
        "ops_requested": metadata.get("ops", ""),
        "insert": counts["I"],
        "delete": counts["D"],
        "search": counts["S"],
        "mix": metadata.get("mix", ""),
        "theta": metadata.get("theta", ""),
        "insert_order": metadata.get("insert_order", ""),
        "seed": metadata.get("seed", ""),
        "wall_time_ns": wall_time,
        "rotations": structure.rotation_count,
        "final_size": len(structure),
        "final_height": final_height,
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "python_compiler": platform.python_compiler(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "repetition": repetition,
    }
    # Cada código produz uma linha independente porque suas distribuições de
    # latência possuem características diferentes.
    rows = []
    for code, name in (("I", "insert"), ("D", "delete"), ("S", "search")):
        # Resumindo somente as amostras associadas ao código atual.
        mean, p50, p99 = summarize_latencies(latencies[code])
        # O operador de união cria uma nova linha sem modificar o dicionário
        # comum que será reutilizado nas próximas operações.
        rows.append(common | {"operation": name, "count": counts[code], "mean_ns": mean, "p50_ns": p50, "p99_ns": p99})
    return rows


def write_results(output_path: Path, rows: list[dict[str, str | int]], append: bool) -> None:
    """Write benchmark rows with a stable CSV schema.

    Args:
        output_path: Destination CSV path.
        rows: CSV-ready benchmark rows.
        append: Append to an existing result file when True.
    """
    # Esta função permanece no módulo de benchmark porque conhece FIELD_NAMES,
    # a política de append dos resultados experimentais e o formato CSV. Movê-la
    # para helper_functions transferiria conhecimento do domínio para um módulo
    # geral ou exigiria uma interface maior apenas para receber esse contexto.
    # A criação recursiva permite apontar o resultado para um diretório ainda inexistente.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Um cabeçalho é obrigatório ao substituir o arquivo e ao iniciar um append
    # sobre arquivo ausente ou vazio. Em append real, repeti-lo quebraria o CSV.
    write_header = not append or not output_path.exists() or output_path.stat().st_size == 0
    # newline="" delega ao módulo csv o controle correto das quebras de linha.
    with output_path.open("a" if append else "w", newline="", encoding="utf-8") as output_file:
        # FIELD_NAMES fixa simultaneamente a ordem e o conjunto de colunas aceitas.
        writer = csv.DictWriter(output_file, fieldnames=FIELD_NAMES)
        if write_header:
            writer.writeheader()
        # Todas as linhas já foram normalizadas por benchmark_trace segundo o esquema.
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    """Parse command-line arguments and run one benchmark repetition.

    Args:
        argv: Optional argument list for tests and embedding.

    Returns:
        Process exit code.
    """
    parser = PortugueseArgumentParser(description=__doc__)
    parser.add_argument("trace", metavar="RASTRO", type=Path, help="arquivo .trace de entrada")
    parser.add_argument(
        "--saida", dest="output", metavar="CSV", type=Path, required=True, help="arquivo CSV de destino"
    )
    parser.add_argument(
        "--implementacao",
        dest="implementation",
        choices=["avl", "lista-ordenada"],
        default="avl",
        help="estrutura que será medida",
    )
    parser.add_argument(
        "--conjunto-dados",
        dest="dataset",
        metavar="NOME",
        default="desconhecido",
        help="identificador do conjunto registrado no CSV",
    )
    parser.add_argument(
        "--carga-maxima",
        dest="max_load",
        metavar="N",
        type=int,
        default=0,
        help="limite de carga usado ao gerar o rastro",
    )
    parser.add_argument(
        "--repeticao",
        dest="repetition",
        metavar="N",
        type=int,
        default=1,
        help="número da repetição, contado a partir de um",
    )
    parser.add_argument(
        "--acrescentar",
        dest="append",
        action="store_true",
        help="acrescenta linhas em vez de substituir o CSV",
    )
    args = parser.parse_args(argv)
    # Impedindo que a abertura do CSV destrua o próprio trace de entrada.
    if args.trace.resolve() == args.output.resolve():
        parser.error("rastro e saída devem ser arquivos diferentes")
    # Limites negativos não representam uma quantidade válida de chaves carregadas.
    if args.max_load < 0:
        parser.error("carga-máxima deve ser não negativa")
    # As repetições são numeradas a partir de um para aparecerem claramente no run_id.
    if args.repetition < 1:
        parser.error("repetição deve ser pelo menos 1")
    try:
        # Separando medição e persistência para não incluir escrita CSV nas latências.
        implementation = "sorted-list" if args.implementation == "lista-ordenada" else "avl"
        rows = benchmark_trace(args.trace, implementation, args.dataset, args.max_load, args.repetition)
        write_results(args.output, rows, args.append)
    except (OSError, ValueError) as error:
        # parser.error mantém uma mensagem uniforme e retorna o código de erro de CLI.
        parser.error(str(error))
    print(f"[sucesso] {len(rows)} linhas de operações gravadas em {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
