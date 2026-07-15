"""Executa uma matriz de experimentos definida em um único arquivo JSON."""

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from itertools import product
from pathlib import Path
from typing import Any

from benchmark import benchmark_trace
from helper_functions import PortugueseArgumentParser
from run_trace import run_trace

PARAMETER_DEFAULTS: dict[str, Any] = {
    "conjunto_dados": "sintetico",
    "formato": "automatico",
    "bytes_chave": 8,
    "carga_maxima": 0,
    "operacoes": 1_000_000,
    "universo": 0,
    "mistura": "50:20:30",
    "theta": 0.99,
    "reserva": 0.10,
    "acertos": 0.70,
    "remocoes_ausentes": 0.05,
    "buscas_em_removidas": 0.50,
    "ordem_insercao": "embaralhada",
    "semente": 42,
    "implementacao": "avl",
    "repeticao": 1,
}

RESULT_FIELDS = [
    "run_id",
    "status",
    "error",
    "experiment",
    "trace_id",
    "implementation",
    "dataset",
    "key_file",
    "synthetic",
    "format",
    "key_bytes",
    "max_load",
    "operations_requested",
    "universe_requested",
    "mix",
    "theta",
    "reserve",
    "hit_rate",
    "missing_delete_rate",
    "removed_search_rate",
    "insert_order",
    "seed",
    "repetition",
    "insert_count",
    "insert_mean_ns",
    "insert_p50_ns",
    "insert_p99_ns",
    "delete_count",
    "delete_mean_ns",
    "delete_p50_ns",
    "delete_p99_ns",
    "search_count",
    "search_mean_ns",
    "search_p50_ns",
    "search_p99_ns",
    "wall_time_ns",
    "rotations",
    "final_size",
    "final_height",
    "python",
    "python_implementation",
    "python_compiler",
    "platform",
    "machine",
]

FORMAT_CODES = {"automatico": "auto", "sosd": "sosd", "texto": "text"}
ORDER_CODES = {"embaralhada": "shuffle", "ordenada": "sorted", "popularidade": "popularity"}
IMPLEMENTATION_CODES = {"avl": "avl", "lista-ordenada": "sorted-list"}


def as_values(value: Any) -> list[Any]:
    """Normalize one configuration value to a non-empty list.

    Args:
        value: Scalar or list read from JSON.

    Returns:
        The original list or a one-item list containing the scalar.

    Raises:
        ValueError: If the supplied list is empty.
    """
    values = value if isinstance(value, list) else [value]
    if not values:
        raise ValueError("listas de parâmetros não podem ser vazias")
    return values


def load_configuration(config_path: Path) -> dict[str, Any]:
    """Read and validate the top-level JSON structure.

    Args:
        config_path: Configuration file to read.

    Returns:
        Parsed JSON mapping.

    Raises:
        ValueError: If no experiment blocks are declared.
    """
    with config_path.open(encoding="utf-8") as config_file:
        configuration = json.load(config_file)
    if not isinstance(configuration, dict):
        raise ValueError("a raiz da configuração JSON deve ser um objeto")
    unknown_sections = sorted(set(configuration) - {"estudo", "experimentos"})
    if unknown_sections:
        raise ValueError(f"seção desconhecida {unknown_sections[0]!r}")
    study = configuration.get("estudo", {})
    if not isinstance(study, dict):
        raise ValueError("estudo deve ser um objeto JSON")
    unknown_study_parameters = sorted(set(study) - {"resultados", "rastros", "continuar_apos_erro"})
    if unknown_study_parameters:
        raise ValueError(f"estudo: parâmetro desconhecido {unknown_study_parameters[0]!r}")
    for path_parameter in ("resultados", "rastros"):
        if path_parameter in study and not isinstance(study[path_parameter], str):
            raise ValueError(f"estudo: {path_parameter} deve ser um caminho textual")
    if "continuar_apos_erro" in study and not isinstance(study["continuar_apos_erro"], bool):
        raise ValueError("estudo: continuar_apos_erro deve ser verdadeiro ou falso")
    experiments = configuration.get("experimentos")
    if not isinstance(experiments, list) or not experiments:
        raise ValueError("a configuração deve conter pelo menos um item no array experimentos")
    return configuration


def validate_case(case: dict[str, Any]) -> None:
    """Validate one fully expanded execution case.

    Args:
        case: Complete execution mapping.

    Raises:
        ValueError: If a value cannot be executed safely by the project CLIs.
    """
    name = str(case["nome"])
    for parameter, choices in (
        ("formato", FORMAT_CODES),
        ("ordem_insercao", ORDER_CODES),
        ("implementacao", IMPLEMENTATION_CODES),
    ):
        if not isinstance(case[parameter], str) or case[parameter] not in choices:
            raise ValueError(f"experimento {name!r}: valor inválido para {parameter}: {case[parameter]!r}")

    for parameter, minimum in (
        ("bytes_chave", 4),
        ("carga_maxima", 0),
        ("operacoes", 1),
        ("universo", 0),
        ("semente", 0),
        ("repeticao", 1),
    ):
        value = case[parameter]
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise ValueError(f"experimento {name!r}: {parameter} deve ser inteiro maior ou igual a {minimum}")
    if case["bytes_chave"] not in {4, 8}:
        raise ValueError(f"experimento {name!r}: bytes_chave deve ser 4 ou 8")
    if "sintetico" in case and (
        not isinstance(case["sintetico"], int) or isinstance(case["sintetico"], bool) or case["sintetico"] < 1
    ):
        raise ValueError(f"experimento {name!r}: sintetico deve ser inteiro positivo")
    if "arquivo_chaves" in case and not isinstance(case["arquivo_chaves"], str):
        raise ValueError(f"experimento {name!r}: arquivo_chaves deve ser um caminho textual")
    if not isinstance(case["conjunto_dados"], str) or not case["conjunto_dados"].strip():
        raise ValueError(f"experimento {name!r}: conjunto_dados deve ser textual e não vazio")

    for parameter in ("reserva", "acertos", "remocoes_ausentes", "buscas_em_removidas"):
        value = case[parameter]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
            raise ValueError(f"experimento {name!r}: {parameter} deve estar entre 0 e 1")
    theta = case["theta"]
    if not isinstance(theta, (int, float)) or isinstance(theta, bool) or theta < 0:
        raise ValueError(f"experimento {name!r}: theta deve ser não negativo")
    try:
        mix = [float(part) for part in str(case["mistura"]).split(":")]
    except ValueError as error:
        raise ValueError(f"experimento {name!r}: mistura deve seguir I:D:S") from error
    if len(mix) != 3 or any(weight < 0 for weight in mix) or sum(mix) <= 0:
        raise ValueError(f"experimento {name!r}: mistura deve conter três pesos não negativos e soma positiva")


def expand_cases(configuration: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield the Cartesian product of every experiment parameter.

    Each object in the ``experimentos`` array is expanded independently. Scalar values
    behave as one-item lists, while lists contribute every value to the
    Cartesian product.

    Args:
        configuration: Parsed study configuration.

    Yields:
        One complete execution mapping per parameter combination.

    Raises:
        ValueError: If an experiment has no name or declares an invalid source.
    """
    for experiment in configuration["experimentos"]:
        if not isinstance(experiment, dict):
            raise ValueError("cada item de experimentos deve ser um objeto JSON")
        name = experiment.get("nome")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("cada experimento deve possuir um nome")
        allowed_parameters = {"nome", "sintetico", "arquivo_chaves", *PARAMETER_DEFAULTS}
        unknown_parameters = sorted(set(experiment) - allowed_parameters)
        if unknown_parameters:
            raise ValueError(f"experimento {name!r}: parâmetro desconhecido {unknown_parameters[0]!r}")
        source_parameters = [parameter for parameter in ("sintetico", "arquivo_chaves") if parameter in experiment]
        if len(source_parameters) != 1:
            raise ValueError(f"experimento {name!r}: informe exatamente um entre sintetico e arquivo_chaves")

        parameter_names = [source_parameters[0], *PARAMETER_DEFAULTS]
        parameter_values = [
            as_values(experiment.get(parameter, PARAMETER_DEFAULTS.get(parameter))) for parameter in parameter_names
        ]
        for combination in product(*parameter_values):
            case = {"nome": name, **dict(zip(parameter_names, combination, strict=True))}
            validate_case(case)
            yield case


def stable_identifier(values: dict[str, Any]) -> str:
    """Return a deterministic short identifier for configuration values.

    Args:
        values: Values whose identity must remain stable between processes.

    Returns:
        First sixteen hexadecimal digits of a SHA-256 digest.
    """
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def trace_values(case: dict[str, Any]) -> dict[str, Any]:
    """Return only parameters that influence trace generation.

    Args:
        case: Complete execution case.

    Returns:
        Case without implementation and repetition.
    """
    return {key: value for key, value in case.items() if key not in {"implementacao", "repeticao"}}


def resolve_path(base_directory: Path, configured_path: str) -> Path:
    """Resolve a configured path relative to its JSON file.

    Args:
        base_directory: Directory containing the configuration file.
        configured_path: Absolute or relative path from JSON.

    Returns:
        Absolute normalized path.
    """
    path = Path(configured_path)
    return path.resolve() if path.is_absolute() else (base_directory / path).resolve()


def generate_trace(case: dict[str, Any], base_directory: Path, traces_directory: Path) -> tuple[str, Path, Path]:
    """Generate and validate one trace, reusing an existing complete trace.

    Args:
        case: Complete execution case.
        base_directory: Directory containing the configuration file.
        traces_directory: Directory used for reusable trace artifacts.

    Returns:
        Trace identifier, trace path, and oracle path.

    Raises:
        ValueError: If the generated trace disagrees with its oracle.
    """
    values = trace_values(case)
    trace_id = stable_identifier(values)
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(case["nome"])).strip("-") or "experimento"
    prefix = traces_directory / f"{safe_name}-{trace_id}"
    trace_path = prefix.with_suffix(".trace")
    expected_path = prefix.with_suffix(".expected")
    complete_path = prefix.with_suffix(".complete")
    if complete_path.exists() and trace_path.exists() and expected_path.exists():
        return trace_id, trace_path, expected_path

    traces_directory.mkdir(parents=True, exist_ok=True)
    key_file = case.get("arquivo_chaves")
    key_path = resolve_path(base_directory, str(key_file)) if key_file is not None else None
    generator_path = Path(__file__).with_name("workload_generator.py")
    source_arguments = ["--sintetico", str(case["sintetico"])] if "sintetico" in case else ["--chaves", str(key_path)]
    command = [
        sys.executable,
        str(generator_path),
        "gerar",
        *source_arguments,
        "--formato",
        str(case["formato"]),
        "--bytes-chave",
        str(case["bytes_chave"]),
        "--carga-maxima",
        str(case["carga_maxima"]),
        "--saida",
        str(prefix),
        "--operacoes",
        str(case["operacoes"]),
        "--universo",
        str(case["universo"]),
        "--mistura",
        str(case["mistura"]),
        "--theta",
        str(case["theta"]),
        "--reserva",
        str(case["reserva"]),
        "--acertos",
        str(case["acertos"]),
        "--remocoes-ausentes",
        str(case["remocoes_ausentes"]),
        "--buscas-em-removidas",
        str(case["buscas_em_removidas"]),
        "--ordem-insercao",
        str(case["ordem_insercao"]),
        "--semente",
        str(case["semente"]),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode:
        diagnostics = [line for line in completed.stderr.splitlines() if line.strip()]
        raise ValueError(diagnostics[-1] if diagnostics else f"o gerador terminou com código {completed.returncode}")

    candidate_path = prefix.with_suffix(".candidate")
    validation = run_trace(trace_path, candidate_path, expected_path=expected_path)
    candidate_path.unlink(missing_ok=True)
    if validation["oracle_mismatches"]:
        raise ValueError(f"rastro {trace_id}: a AVL divergiu do oráculo")
    complete_path.write_text(json.dumps(values, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    return trace_id, trace_path, expected_path


def base_result(case: dict[str, Any], trace_id: str, base_directory: Path) -> dict[str, Any]:
    """Build the configuration columns shared by success and failure rows.

    Args:
        case: Complete execution case.
        trace_id: Identifier of the trace used by the case.
        base_directory: Directory containing the configuration file.

    Returns:
        Result row with configuration fields and empty measurements.
    """
    implementation = IMPLEMENTATION_CODES.get(str(case["implementacao"]), str(case["implementacao"]))
    key_file = case.get("arquivo_chaves")
    return {
        **dict.fromkeys(RESULT_FIELDS, ""),
        "run_id": stable_identifier(case),
        "status": "erro",
        "experiment": case["nome"],
        "trace_id": trace_id,
        "implementation": implementation,
        "dataset": case["conjunto_dados"],
        "key_file": str(resolve_path(base_directory, str(key_file))) if key_file is not None else "",
        "synthetic": case.get("sintetico", ""),
        "format": case["formato"],
        "key_bytes": case["bytes_chave"],
        "max_load": case["carga_maxima"],
        "operations_requested": case["operacoes"],
        "universe_requested": case["universo"],
        "mix": case["mistura"],
        "theta": case["theta"],
        "reserve": case["reserva"],
        "hit_rate": case["acertos"],
        "missing_delete_rate": case["remocoes_ausentes"],
        "removed_search_rate": case["buscas_em_removidas"],
        "insert_order": ORDER_CODES.get(str(case["ordem_insercao"]), case["ordem_insercao"]),
        "seed": case["semente"],
        "repetition": case["repeticao"],
    }


def benchmark_case(case: dict[str, Any], trace_id: str, trace_path: Path, base_directory: Path) -> dict[str, Any]:
    """Execute one benchmark case and flatten its operation metrics.

    Args:
        case: Complete execution case.
        trace_id: Identifier of the trace being measured.
        trace_path: Workload trace to stream.
        base_directory: Directory containing the configuration file.

    Returns:
        One wide CSV row representing the complete execution.
    """
    row = base_result(case, trace_id, base_directory)
    metrics = benchmark_trace(
        trace_path,
        str(row["implementation"]),
        str(row["dataset"]),
        int(case["carga_maxima"]),
        int(case["repeticao"]),
    )
    by_operation = {str(operation["operation"]): operation for operation in metrics}
    for operation in ("insert", "delete", "search"):
        operation_metrics = by_operation[operation]
        row[f"{operation}_count"] = operation_metrics["count"]
        row[f"{operation}_mean_ns"] = operation_metrics["mean_ns"]
        row[f"{operation}_p50_ns"] = operation_metrics["p50_ns"]
        row[f"{operation}_p99_ns"] = operation_metrics["p99_ns"]
    common = metrics[0]
    for field in (
        "wall_time_ns",
        "rotations",
        "final_size",
        "final_height",
        "python",
        "python_implementation",
        "python_compiler",
        "platform",
        "machine",
    ):
        row[field] = common[field]
    row["status"] = "sucesso"
    return row


def append_result(results_path: Path, row: dict[str, Any]) -> None:
    """Append and durably flush one execution row.

    Args:
        results_path: CSV file shared by the complete study.
        row: Execution result matching ``RESULT_FIELDS``.

    Raises:
        ValueError: If an existing CSV uses a different schema.
    """
    results_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not results_path.exists() or results_path.stat().st_size == 0
    if not write_header:
        with results_path.open(newline="", encoding="utf-8") as existing_file:
            if next(csv.reader(existing_file), None) != RESULT_FIELDS:
                raise ValueError(f"o CSV existente {results_path} possui esquema incompatível")
    with results_path.open("a", newline="", encoding="utf-8") as results_file:
        writer = csv.DictWriter(results_file, fieldnames=RESULT_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
        results_file.flush()
        os.fsync(results_file.fileno())


def successful_run_ids(results_path: Path) -> set[str]:
    """Read identifiers that already have a successful persisted result.

    Args:
        results_path: Study CSV that may contain previous attempts.

    Returns:
        Identifiers whose latest or earlier row records success.

    Raises:
        ValueError: If the existing CSV schema is incompatible.
    """
    if not results_path.exists() or results_path.stat().st_size == 0:
        return set()
    with results_path.open(newline="", encoding="utf-8") as results_file:
        reader = csv.DictReader(results_file)
        if reader.fieldnames != RESULT_FIELDS:
            raise ValueError(f"o CSV existente {results_path} possui esquema incompatível")
        return {row["run_id"] for row in reader if row["status"] == "sucesso"}


def execute_study(
    configuration: dict[str, Any], config_path: Path, cases: list[dict[str, Any]]
) -> tuple[int, int, int]:
    """Execute every case and checkpoint each outcome.

    Args:
        configuration: Parsed study configuration.
        config_path: Path used to resolve relative artifacts.
        cases: Expanded Cartesian product.

    Returns:
        Number of successful, failed, and skipped executions.
    """
    study = configuration.get("estudo", {})
    if not isinstance(study, dict):
        raise ValueError("estudo deve ser um objeto JSON")
    base_directory = config_path.resolve().parent
    results_path = resolve_path(base_directory, str(study.get("resultados", "results/estudo.csv")))
    traces_directory = resolve_path(base_directory, str(study.get("rastros", "results/traces")))
    continue_after_error = bool(study.get("continuar_apos_erro", False))
    completed = successful_run_ids(results_path)
    successful = failed = skipped = 0
    total_executions = len(cases)
    progress_width = len(str(total_executions))

    for execution_number, case in enumerate(cases, start=1):
        progress = f"[Execução {execution_number:0{progress_width}d}/{total_executions}]"
        run_id = stable_identifier(case)
        if run_id in completed:
            skipped += 1
            continue
        trace_id = stable_identifier(trace_values(case))
        try:
            trace_id, trace_path, _ = generate_trace(case, base_directory, traces_directory)
            row = benchmark_case(case, trace_id, trace_path, base_directory)
            append_result(results_path, row)
            completed.add(run_id)
            successful += 1
            print(f"{progress} [sucesso] execução {row['run_id']} persistida")
        except Exception as error:
            row = base_result(case, trace_id, base_directory)
            row["error"] = str(error)
            append_result(results_path, row)
            failed += 1
            print(f"{progress} [erro] execução {row['run_id']}: {error}")
            if not continue_after_error:
                break
    if skipped:
        print(f"[retomada] {skipped} execuções já concluídas")
    return successful, failed, skipped


def main(argv: list[str] | None = None) -> int:
    """Load a study configuration and execute or inspect its matrix.

    Args:
        argv: Optional command-line arguments for tests and embedding.

    Returns:
        Process exit code.
    """
    parser = PortugueseArgumentParser(description=__doc__)
    parser.add_argument("configuracao", metavar="CONFIGURAÇÃO", type=Path, help="arquivo JSON do estudo")
    parser.add_argument(
        "--somente-planejar",
        action="store_true",
        help="mostra a quantidade de execuções sem gerar arquivos",
    )
    args = parser.parse_args(argv)
    try:
        configuration = load_configuration(args.configuracao)
        cases = list(expand_cases(configuration))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))

    print(f"[plano] {len(cases)} execuções")
    if args.somente_planejar:
        return 0
    try:
        successful, failed, skipped = execute_study(configuration, args.configuracao, cases)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"[concluído] {successful} execuções novas; {failed} falhas; {skipped} ignoradas")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
