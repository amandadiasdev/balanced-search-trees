"""Integration tests for the empirical-study command-line interface."""

import csv
import json
import subprocess
import sys
from pathlib import Path


def write_configuration(
    config_path: Path,
    experiment: dict[str, object],
    study: dict[str, object] | None = None,
) -> None:
    """Write one JSON study configuration used through the public CLI.

    Args:
        config_path: Destination JSON file.
        experiment: Experiment block under test.
        study: Optional study-level settings.
    """
    config_path.write_text(
        json.dumps({"estudo": study or {}, "experimentos": [experiment]}),
        encoding="utf-8",
    )


def test_cli_plans_the_cartesian_product_from_one_json_file(tmp_path: Path) -> None:
    """Expand every parameter list without executing the benchmark."""
    config_path = tmp_path / "study.json"
    write_configuration(
        config_path,
        {
            "nome": "produto-cartesiano",
            "sintetico": 30,
            "operacoes": [10, 20],
            "universo": 20,
            "mistura": "45:25:30",
            "theta": [0.0, 0.99],
            "ordem_insercao": ["ordenada", "embaralhada"],
            "semente": 5,
            "implementacao": ["avl", "lista-ordenada"],
            "repeticao": [1, 2],
        },
        {"resultados": "results.csv", "rastros": "traces"},
    )

    completed = subprocess.run(
        [sys.executable, "src/run_experiments.py", str(config_path), "--somente-planejar"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "[plano] 32 execuções" in completed.stdout
    assert not (tmp_path / "results.csv").exists()
    assert not (tmp_path / "traces").exists()


def test_cli_persists_one_csv_row_after_each_real_execution(tmp_path: Path) -> None:
    """Benchmark every implementation and persist a wide row immediately."""
    config_path = tmp_path / "study.json"
    write_configuration(
        config_path,
        {
            "nome": "persistencia",
            "sintetico": 40,
            "conjunto_dados": "sintetico",
            "operacoes": 30,
            "universo": 30,
            "mistura": "45:25:30",
            "theta": 0.99,
            "ordem_insercao": "ordenada",
            "semente": 5,
            "implementacao": ["avl", "lista-ordenada"],
            "repeticao": 1,
        },
        {"resultados": "results/study.csv", "rastros": "results/traces"},
    )

    completed = subprocess.run(
        [sys.executable, "src/run_experiments.py", str(config_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    results_path = tmp_path / "results" / "study.csv"
    with results_path.open(newline="", encoding="utf-8") as results_file:
        rows = list(csv.DictReader(results_file))

    assert "[concluído] 2 execuções novas" in completed.stdout
    assert len(rows) == 2
    assert {row["status"] for row in rows} == {"sucesso"}
    assert {row["implementation"] for row in rows} == {"avl", "sorted-list"}
    assert len({row["run_id"] for row in rows}) == 2
    assert len({row["trace_id"] for row in rows}) == 1
    assert all(int(row["insert_count"]) > 0 for row in rows)
    assert all(int(row["search_p99_ns"]) >= 0 for row in rows)
    assert all(row["python_implementation"] for row in rows)
    assert all(row["python_compiler"] for row in rows)
    assert (tmp_path / "results" / "traces").is_dir()


def test_cli_aligns_execution_progress_with_the_total_width(tmp_path: Path) -> None:
    """Prefix each persisted execution with zero-padded progress."""
    config_path = tmp_path / "study.json"
    write_configuration(
        config_path,
        {
            "nome": "progresso",
            "sintetico": 40,
            "operacoes": 30,
            "universo": 30,
            "mistura": "45:25:30",
            "theta": 0.99,
            "ordem_insercao": "ordenada",
            "semente": 5,
            "implementacao": "avl",
            "repeticao": list(range(1, 13)),
        },
        {"resultados": "study.csv", "rastros": "traces"},
    )

    completed = subprocess.run(
        [sys.executable, "src/run_experiments.py", str(config_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    progress_lines = [line for line in completed.stdout.splitlines() if line.startswith("[Execução")]

    assert progress_lines[0].startswith("[Execução 01/12] [sucesso]")
    assert progress_lines[-1].startswith("[Execução 12/12] [sucesso]")


def test_cli_resumes_without_repeating_successful_executions(tmp_path: Path) -> None:
    """Skip successful run identifiers while preserving the existing CSV."""
    config_path = tmp_path / "study.json"
    write_configuration(
        config_path,
        {
            "nome": "retomada",
            "sintetico": 40,
            "operacoes": 20,
            "universo": 30,
            "mistura": "45:25:30",
            "theta": 0.99,
            "ordem_insercao": "ordenada",
            "semente": 5,
            "implementacao": "avl",
            "repeticao": [1, 2],
        },
        {"resultados": "study.csv", "rastros": "traces"},
    )

    command = [sys.executable, "src/run_experiments.py", str(config_path)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    resumed = subprocess.run(command, check=True, capture_output=True, text=True)

    with (tmp_path / "study.csv").open(newline="", encoding="utf-8") as results_file:
        rows = list(csv.DictReader(results_file))

    assert len(rows) == 2
    assert "[retomada] 2 execuções já concluídas" in resumed.stdout
    assert "[concluído] 0 execuções novas; 0 falhas; 2 ignoradas" in resumed.stdout


def test_cli_checkpoints_a_failure_and_retries_it_after_the_cause_is_fixed(tmp_path: Path) -> None:
    """Persist an error attempt without treating its run identifier as complete."""
    config_path = tmp_path / "study.json"
    write_configuration(
        config_path,
        {
            "nome": "nova-tentativa",
            "arquivo_chaves": "keys.txt",
            "formato": "texto",
            "operacoes": 20,
            "universo": 30,
            "mistura": "45:25:30",
            "theta": 0.99,
            "ordem_insercao": "ordenada",
            "semente": 5,
            "implementacao": "avl",
            "repeticao": 1,
        },
        {"resultados": "study.csv", "rastros": "traces"},
    )
    command = [sys.executable, "src/run_experiments.py", str(config_path)]

    failed = subprocess.run(command, check=False, capture_output=True, text=True)
    (tmp_path / "keys.txt").write_text("\n".join(str(key) for key in range(1, 41)), encoding="utf-8")
    recovered = subprocess.run(command, check=True, capture_output=True, text=True)

    with (tmp_path / "study.csv").open(newline="", encoding="utf-8") as results_file:
        rows = list(csv.DictReader(results_file))

    assert failed.returncode == 1
    assert recovered.returncode == 0
    assert [row["status"] for row in rows] == ["erro", "sucesso"]
    assert rows[0]["run_id"] == rows[1]["run_id"]
    assert "keys.txt not found" in rows[0]["error"]


def test_cli_rejects_unknown_configuration_parameters(tmp_path: Path) -> None:
    """Fail fast when a misspelled parameter would otherwise be ignored."""
    config_path = tmp_path / "study.json"
    write_configuration(
        config_path,
        {"nome": "erro-de-digitacao", "sintetico": 40, "operacoez": 20},
    )

    completed = subprocess.run(
        [sys.executable, "src/run_experiments.py", str(config_path), "--somente-planejar"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "parâmetro desconhecido 'operacoez'" in completed.stderr


def test_cli_continues_after_a_middle_failure_when_configured(tmp_path: Path) -> None:
    """Keep later combinations running while retaining the failed checkpoint."""
    (tmp_path / "keys.txt").write_text("\n".join(str(key) for key in range(1, 41)), encoding="utf-8")
    config_path = tmp_path / "study.json"
    write_configuration(
        config_path,
        {
            "nome": "continuacao",
            "arquivo_chaves": ["missing.txt", "keys.txt"],
            "formato": "texto",
            "operacoes": 20,
            "universo": 30,
            "mistura": "45:25:30",
            "theta": 0.99,
            "ordem_insercao": "ordenada",
            "semente": 5,
            "implementacao": "avl",
            "repeticao": 1,
        },
        {"resultados": "study.csv", "rastros": "traces", "continuar_apos_erro": True},
    )

    completed = subprocess.run(
        [sys.executable, "src/run_experiments.py", str(config_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    with (tmp_path / "study.csv").open(newline="", encoding="utf-8") as results_file:
        rows = list(csv.DictReader(results_file))

    assert completed.returncode == 1
    assert [row["status"] for row in rows] == ["erro", "sucesso"]
    assert "[concluído] 1 execuções novas; 1 falhas; 0 ignoradas" in completed.stdout
