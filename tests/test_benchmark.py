"""Integration tests for the benchmark command-line interface."""

import csv
import subprocess
import sys
from pathlib import Path

from benchmark import SortedListSet


def test_cli_writes_operation_metrics_for_both_implementations(tmp_path: Path) -> None:
    """Benchmark AVL and sorted-list implementations with the same trace."""
    trace_path = tmp_path / "sample.trace"
    trace_path.write_text(
        "# universe=20 reserve=2 mix=45:25:30 theta=0.99 seed=5 insert_order=sorted ops=6\n"
        "I 10\nI 20\nS 10\nD 10\nS 10\nS 20\n",
        encoding="utf-8",
    )

    for cli_implementation, recorded_implementation in (("avl", "avl"), ("lista-ordenada", "sorted-list")):
        output_path = tmp_path / f"{recorded_implementation}.csv"
        completed = subprocess.run(
            [
                sys.executable,
                "src/benchmark.py",
                str(trace_path),
                "--saida",
                str(output_path),
                "--implementacao",
                cli_implementation,
                "--conjunto-dados",
                "sintético",
                "--repeticao",
                "2",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        with output_path.open(newline="", encoding="utf-8") as result_file:
            rows = list(csv.DictReader(result_file))

        assert [row["operation"] for row in rows] == ["insert", "delete", "search"]
        assert [int(row["count"]) for row in rows] == [2, 1, 3]
        assert {row["implementation"] for row in rows} == {recorded_implementation}
        assert {row["dataset"] for row in rows} == {"sintético"}
        assert {row["universe"] for row in rows} == {"20"}
        assert {row["ops_requested"] for row in rows} == {"6"}
        assert {row["mix"] for row in rows} == {"45:25:30"}
        assert {row["theta"] for row in rows} == {"0.99"}
        assert {row["insert_order"] for row in rows} == {"sorted"}
        assert {row["seed"] for row in rows} == {"5"}
        assert {row["repetition"] for row in rows} == {"2"}
        assert {row["final_size"] for row in rows} == {"1"}
        assert all(int(row["mean_ns"]) >= 0 for row in rows)
        assert all(int(row["p50_ns"]) >= 0 for row in rows)
        assert all(int(row["p99_ns"]) >= 0 for row in rows)
        assert "[sucesso] 3 linhas de operações gravadas em" in completed.stdout


def test_cli_records_zero_metrics_for_an_operation_without_samples(tmp_path: Path) -> None:
    """Keep the CSV schema complete when a small trace omits an operation."""
    trace_path = tmp_path / "insert-only.trace"
    output_path = tmp_path / "results.csv"
    trace_path.write_text("# universe=1 ops=1\nI 10\n", encoding="utf-8")

    subprocess.run(
        [sys.executable, "src/benchmark.py", str(trace_path), "--saida", str(output_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    with output_path.open(newline="", encoding="utf-8") as result_file:
        rows = list(csv.DictReader(result_file))

    assert [(row["operation"], row["count"]) for row in rows] == [
        ("insert", "1"),
        ("delete", "0"),
        ("search", "0"),
    ]
    assert [(row["mean_ns"], row["p50_ns"], row["p99_ns"]) for row in rows[1:]] == [
        ("0", "0", "0"),
        ("0", "0", "0"),
    ]


def test_sorted_list_baseline_matches_the_tree_query_contract() -> None:
    """Expose the same observable set and query semantics as the AVL."""
    baseline = SortedListSet()

    assert [baseline.insert(key) for key in (30, 10, 20, 20)] == [True, True, True, False]
    assert baseline.search(20) is True
    assert baseline.search(99) is False
    assert baseline.rank(25) == 2
    assert [baseline.select(index) for index in range(len(baseline))] == [10, 20, 30]
    assert baseline.range_agg(15, 30) == 30
    assert baseline.range_agg(31, 40) is None
    assert baseline.delete(20) is True
    assert baseline.delete(20) is False


def test_cli_rejects_overwriting_the_input_trace(tmp_path: Path) -> None:
    """Protect benchmark input from being replaced by its result CSV."""
    trace_path = tmp_path / "sample.trace"
    original = "I 10\n"
    trace_path.write_text(original, encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "src/benchmark.py", str(trace_path), "--saida", str(trace_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "devem ser arquivos diferentes" in completed.stderr
    assert trace_path.read_text(encoding="utf-8") == original
