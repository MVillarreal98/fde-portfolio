"""Packaging: `pip install .` must bring every runtime import (v1.0.0 forgot tabulate)."""

from __future__ import annotations

import ast
import re
import sys

import pytest

from reconciliation.anomalies import RULE_COLUMNS

from conftest import PROJECT

tomllib = pytest.importorskip("tomllib")  # stdlib from Python 3.11
META = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
SRC = PROJECT / "src" / "reconciliation"


def _name(requirement: str) -> str:
    return re.split(r"[<>=!~;\[ ]", requirement, maxsplit=1)[0].strip().lower()


def test_every_third_party_import_is_a_declared_dependency() -> None:
    imported: set[str] = set()
    for path in SRC.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
    third_party = {m for m in imported if m not in sys.stdlib_module_names}
    declared = {_name(d) for d in META["project"]["dependencies"]}
    # DataFrame.to_markdown imports tabulate lazily, so no import statement shows it.
    assert third_party | {"tabulate"} <= declared


def test_requirements_txt_mirrors_pyproject() -> None:
    lines = (PROJECT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    pinned = [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
    assert pinned == META["project"]["dependencies"]


def test_dev_extra_has_test_tooling() -> None:
    dev = {_name(d) for d in META["project"]["optional-dependencies"]["dev"]}
    assert {"pytest", "pytest-cov", "ruff"} <= dev


def test_sql_files_ship_with_the_package() -> None:
    assert META["tool"]["setuptools"]["package-data"]["reconciliation"] == ["sql/*.sql"]
    for name in ["matched", *RULE_COLUMNS]:
        assert (SRC / "sql" / f"{name}.sql").is_file(), name
