"""Integration tests for the workload generator command-line interface."""

import subprocess
import sys
from pathlib import Path


def test_cli_generates_and_verifies_files_with_portuguese_parameters(tmp_path: Path) -> None:
    """Generate a small workload and verify a matching candidate in PT-BR."""
    output_prefix = tmp_path / "carga"

    generated = subprocess.run(
        [
            sys.executable,
            "src/workload_generator.py",
            "gerar",
            "--sintetico",
            "100",
            "--operacoes",
            "30",
            "--universo",
            "100",
            "--mistura",
            "45:25:30",
            "--theta",
            "0.99",
            "--ordem-insercao",
            "ordenada",
            "--semente",
            "5",
            "--saida",
            str(output_prefix),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    expected_path = output_prefix.with_suffix(".expected")
    candidate_path = tmp_path / "candidato.out"
    candidate_path.write_text(expected_path.read_text(encoding="utf-8"), encoding="utf-8")
    verified = subprocess.run(
        [
            sys.executable,
            "src/workload_generator.py",
            "verificar",
            "--esperado",
            str(expected_path),
            "--candidato",
            str(candidate_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "[sucesso]" in generated.stderr
    assert "inserções=" in generated.stderr
    assert "remoções=" in generated.stderr
    assert "buscas=" in generated.stderr
    assert "[SUCESSO]" in verified.stdout
    assert "nenhuma divergência" in verified.stdout
