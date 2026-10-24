"""CLI: exit codes, help text, error handling and the demo launcher."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from reconciliation import __version__
from reconciliation.cli import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, build_parser, main

from conftest import DATA, PROJECT, write_case

CLEAN = ("T1,A,OXXO,1.00,MXN,captured,2025-03-01 09:00\n", "S1,T1,1.00,MXN,2025-03-02,1\n")
MISMATCH = ("T1,A,OXXO,1.00,MXN,captured,2025-03-01 09:00\n", "S1,T1,2.00,MXN,2025-03-02,1\n")
REJECTED_ONLY = (
    "T1,A,OXXO,1.00,MXN,captured,2025-03-01 09:00\n",
    "S1,T1,1.00,MXN,2025-03-02,1\nS2,,3.00,MXN,2025-03-02,1\n",
)


def args_for(tmp_path: Path, case: tuple[str, str], *extra: str) -> list[str]:
    ops, billing = write_case(tmp_path / "in", *case)
    return ["--ops", str(ops), "--billing", str(billing), "--out", str(tmp_path / "out"), *extra]


@pytest.mark.parametrize("engine", ["pandas", "sql"])
def test_exit_0_when_sources_reconcile(tmp_path: Path, engine: str) -> None:
    assert main(args_for(tmp_path, CLEAN, "--engine", engine, "--fail-on-findings")) == EXIT_OK


def test_rule_options_reach_the_engine(tmp_path: Path) -> None:
    # 1.00 vs 2.00 is within a 1.00 tolerance.
    args = args_for(
        tmp_path,
        MISMATCH,
        "--tolerance",
        "1",
        "--duplicate-window-minutes",
        "30",
        "--fail-on-findings",
    )
    assert main(args) == EXIT_OK
    report = (tmp_path / "out" / "reconciliation_report.md").read_text(encoding="utf-8")
    assert "tolerance 1 · duplicate-charge window 30 min" in report


def test_findings_exit_0_without_flag(tmp_path: Path) -> None:
    assert main(args_for(tmp_path, MISMATCH)) == EXIT_OK


@pytest.mark.parametrize("engine", ["pandas", "sql"])
def test_findings_exit_2_with_flag(tmp_path: Path, engine: str) -> None:
    code = main(args_for(tmp_path, MISMATCH, "--engine", engine, "--fail-on-findings"))
    assert code == EXIT_FINDINGS


def test_rejected_rows_alone_exit_2_with_flag(tmp_path: Path) -> None:
    assert main(args_for(tmp_path, REJECTED_ONLY, "--fail-on-findings")) == EXIT_FINDINGS


def test_missing_input_exits_1_without_traceback(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "--ops",
            str(tmp_path / "nope.csv"),
            "--billing",
            str(tmp_path / "nope2.csv"),
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert code == EXIT_ERROR
    assert "FileNotFoundError" in caplog.text
    assert "Traceback" not in capsys.readouterr().err


def test_schema_error_exits_1(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    args = args_for(tmp_path, CLEAN)
    Path(args[1]).write_text("transaction_id\nT1\n", encoding="utf-8")
    assert main(args) == EXIT_ERROR
    assert "Missing expected columns" in caplog.text


@pytest.mark.parametrize(
    "bad",
    [
        ["--tolerance", "-1"],
        ["--tolerance", "abc"],
        ["--tolerance", "0.001"],
        ["--duplicate-window-minutes", "-5"],
        ["--duplicate-window-minutes", "ten"],
        ["--engine", "spark"],
    ],
)
def test_invalid_options_exit_1(
    tmp_path: Path, bad: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(args_for(tmp_path, CLEAN, *bad))
    assert exc.value.code == EXIT_ERROR
    assert "error:" in capsys.readouterr().err


def test_required_inputs(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == EXIT_ERROR
    assert "--ops" in capsys.readouterr().err


def test_help_describes_every_option(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "exit codes" in out
    for action in build_parser()._actions:
        assert action.help, action.option_strings


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--version"])
    assert __version__ in capsys.readouterr().out


def test_relative_output_goes_to_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(
        [
            "--ops",
            str(DATA / "ops_transactions.csv"),
            "--billing",
            str(DATA / "billing_statements.csv"),
        ]
    )
    assert code == EXIT_OK
    assert (tmp_path / "output" / "reconciliation_report.md").exists()


def test_findings_are_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    main(args_for(tmp_path, MISMATCH))
    assert "amount_mismatch: 1 findings" in caplog.text
    assert "Executive report:" in caplog.text


def test_demo_launcher_runs_from_any_directory(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(
        [
            sys.executable,
            str(PROJECT / "run_reconciliation.py"),
            "--out",
            str(tmp_path / "demo"),
            "--fail-on-findings",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == EXIT_FINDINGS, proc.stderr
    assert (tmp_path / "demo" / "rejected_rows.csv").exists()
    assert "Traceback" not in proc.stderr
