"""Integration tests for the empirical-results plotting command-line interface."""

import csv
import subprocess
import sys
from pathlib import Path


def test_cli_generates_the_two_report_figures(tmp_path: Path) -> None:
    """Read successful paired results and generate both SVG figures."""
    csv_path = tmp_path / "results.csv"
    fieldnames = [
        "status",
        "trace_id",
        "implementation",
        "operations_requested",
        "theta",
        "insert_order",
        "repetition",
        "insert_mean_ns",
        "insert_p99_ns",
        "delete_mean_ns",
        "wall_time_ns",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as results_file:
        writer = csv.DictWriter(results_file, fieldnames=fieldnames)
        writer.writeheader()
        theta_by_operations = {100: (0.0, 0.6, 0.99, 1.2), 1_000_000: (0.99,)}
        for operations, theta_values in theta_by_operations.items():
            for theta in theta_values:
                for order in ("sorted", "shuffle"):
                    trace_id = f"{operations}-{theta}-{order}"
                    for implementation, multiplier in (("avl", 1.0), ("sorted-list", 1.5)):
                        writer.writerow(
                            {
                                "status": "sucesso",
                                "trace_id": trace_id,
                                "implementation": implementation,
                                "operations_requested": operations,
                                "theta": theta,
                                "insert_order": order,
                                "repetition": 1,
                                "insert_mean_ns": 1_000 * multiplier,
                                "insert_p99_ns": 2_000 * multiplier,
                                "delete_mean_ns": 800 * multiplier,
                                "wall_time_ns": operations * 1_500 * multiplier,
                            }
                        )

    output_directory = tmp_path / "figures"
    completed = subprocess.run(
        [sys.executable, "src/plot_results.py", str(csv_path), "--saida", str(output_directory)],
        check=True,
        capture_output=True,
        text=True,
    )

    expected_files = {
        "speedup-escala-ordem.svg",
        "impacto-theta-remocao.svg",
    }
    assert {path.name for path in output_directory.iterdir()} == expected_files
    assert all("<svg" in (output_directory / filename).read_text(encoding="utf-8") for filename in expected_files)
    speedup_svg = (output_directory / "speedup-escala-ordem.svg").read_text(encoding="utf-8")
    assert "1 mi" in speedup_svg
    theta_svg = (output_directory / "impacto-theta-remocao.svg").read_text(encoding="utf-8")
    assert "Impacto de θ na remoção — 100 operações" in theta_svg
    assert completed.stdout.count("[sucesso] gráfico") == 2
