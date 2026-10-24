"""Packaging checks: dependencies declared, entry point wired, sample data complete."""

from __future__ import annotations

import ast
import sys

import tomllib

from aging_sql.engine import OUTPUT_FILES

from conftest import PROJECT_ROOT, SAMPLE_OUTPUT_DIR

PYPROJECT = PROJECT_ROOT / "pyproject.toml"
SRC_DIR = PROJECT_ROOT / "src"


def test_runtime_dependencies_cover_every_import() -> None:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    declared = {reformat_dependency(dep) for dep in config["project"]["dependencies"]}
    third_party_imports: set[str] = set()
    for source_file in SRC_DIR.glob("**/*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                third_party_imports |= {
                    alias.name.split(".")[0]
                    for alias in node.names
                    if alias.name.split(".")[0] not in sys.stdlib_module_names
                }
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                root = node.module.split(".")[0]
                if root not in sys.stdlib_module_names and root != "aging_sql":
                    third_party_imports.add(root)
    assert third_party_imports == declared


def reformat_dependency(dependency: str) -> str:
    return dependency.split(">")[0].split("=")[0].strip()


def test_console_script_points_at_the_cli() -> None:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    scripts = config["project"]["scripts"]
    assert scripts == {"collections-aging": "aging_sql.cli:main"}


def test_sql_files_are_packaged_data() -> None:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert "aging_sql" in config["tool"]["setuptools"]["package-data"]


def test_sample_output_matches_the_declared_outputs() -> None:
    assert {path.name for path in SAMPLE_OUTPUT_DIR.iterdir()} == set(OUTPUT_FILES)
