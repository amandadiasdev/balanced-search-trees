"""Integration tests for the trace runner command-line interface."""

import subprocess
import sys
from pathlib import Path


def test_cli_processes_trace_and_writes_only_search_answers(tmp_path: Path) -> None:
    """Execute stateful operations and emit one candidate line per search."""
    trace_path = tmp_path / "sample.trace"
    output_path = tmp_path / "candidate.out"
    trace_path.write_text(
        "# sample\nI 10\nI 4\nS 10\nD 10\nS 10\nS 99\nD 99\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "src/run_trace.py",
            str(trace_path),
            "--saida",
            str(output_path),
            "--validar-a-cada",
            "1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert output_path.read_text(encoding="utf-8").splitlines() == [
        "10 FOUND",
        "10 NOT_FOUND",
        "99 NOT_FOUND",
    ]
    assert "inserções=2" in completed.stdout
    assert "remoções=2" in completed.stdout
    assert "buscas=3" in completed.stdout
    assert "tamanho_final=1" in completed.stdout


def test_cli_explains_each_operation_and_compares_searches_with_oracle(tmp_path: Path) -> None:
    """Show a didactic execution whose search answers match the oracle."""
    trace_path = tmp_path / "sample.trace"
    expected_path = tmp_path / "sample.expected"
    output_path = tmp_path / "candidate.out"
    trace_path.write_text("I 10\nS 10\nD 10\nS 10\n", encoding="utf-8")
    expected_path.write_text("10 FOUND\n10 NOT_FOUND\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "src/run_trace.py",
            str(trace_path),
            "--saida",
            str(output_path),
            "--esperado",
            str(expected_path),
            "--mostrar-passos",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    table_rows = [
        [cell.strip() for cell in line.split("│")[1:-1]]
        for line in completed.stdout.splitlines()
        if line.startswith("│")
    ]
    assert ["Arquivo", "Caminho"] in table_rows
    assert ["Rastro", str(trace_path.resolve())] in table_rows
    assert ["Candidato", str(output_path.resolve())] in table_rows
    assert ["Oráculo", str(expected_path.resolve())] in table_rows
    assert ["Linha", "Operação", "Ação", "Obtido", "Esperado", "Conferência"] in table_rows
    assert ["1", "I 10", "inserida", "-", "sem saída", "-"] in table_rows
    assert ["2", "S 10", "busca", "10 FOUND", "10 FOUND", "OK"] in table_rows
    assert ["3", "D 10", "removida", "-", "sem saída", "-"] in table_rows
    assert ["4", "S 10", "busca", "10 NOT_FOUND", "10 NOT_FOUND", "OK"] in table_rows
    assert "[oráculo] 2/2 respostas de busca conferem" in completed.stdout


def test_cli_returns_failure_when_an_answer_disagrees_with_oracle(tmp_path: Path) -> None:
    """Make an oracle disagreement visible and return a failing exit status."""
    trace_path = tmp_path / "sample.trace"
    expected_path = tmp_path / "sample.expected"
    output_path = tmp_path / "candidate.out"
    trace_path.write_text("S 10\n", encoding="utf-8")
    expected_path.write_text("10 FOUND\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "src/run_trace.py",
            str(trace_path),
            "--saida",
            str(output_path),
            "--esperado",
            str(expected_path),
            "--mostrar-passos",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    table_rows = [
        [cell.strip() for cell in line.split("│")[1:-1]]
        for line in completed.stdout.splitlines()
        if line.startswith("│")
    ]
    assert completed.returncode == 1
    assert ["1", "S 10", "busca", "10 NOT_FOUND", "10 FOUND", "DIVERGÊNCIA"] in table_rows
    assert "[erro] inserções=0 remoções=0 buscas=1 tamanho_final=0" in completed.stdout
    assert "[oráculo] 0/1 respostas de busca conferem" in completed.stdout


def test_cli_rejects_unknown_operation_with_line_number(tmp_path: Path) -> None:
    """Report a malformed operation at its physical trace line."""
    trace_path = tmp_path / "invalid.trace"
    output_path = tmp_path / "candidate.out"
    trace_path.write_text("# sample\nX 10\n", encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "src/run_trace.py", str(trace_path), "--saida", str(output_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "linha 2" in completed.stderr
    assert "operação desconhecida 'X'" in completed.stderr


def test_cli_rejects_using_the_trace_as_its_own_output(tmp_path: Path) -> None:
    """Protect the input trace from accidental truncation."""
    trace_path = tmp_path / "sample.trace"
    original = "I 10\nS 10\n"
    trace_path.write_text(original, encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "src/run_trace.py", str(trace_path), "--saida", str(trace_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "devem ser arquivos diferentes" in completed.stderr
    assert trace_path.read_text(encoding="utf-8") == original
