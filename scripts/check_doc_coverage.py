#!/usr/bin/env python3
"""AST-based quality check for documentation coverage in Python code.

This script is intentionally lightweight: it uses only the standard library
and enforces baseline documentation coverage for modules and public callables.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

TARGET_ROOTS = ("apps", "packages", "tests")


@dataclass
class CoverageReport:
    missing_module_docstrings: list[Path] = field(default_factory=list)
    missing_public_docstrings: list[tuple[Path, str, int]] = field(default_factory=list)
    missing_private_docstrings: list[tuple[Path, str, int]] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return bool(self.missing_module_docstrings or self.missing_public_docstrings)


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root_name in TARGET_ROOTS:
        root = Path(root_name)
        if not root.exists():
            continue
        files.extend(sorted(root.rglob("*.py")))
    return files


def _collect_report() -> CoverageReport:
    report = CoverageReport()

    for path in _iter_python_files():
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            report.missing_public_docstrings.append((path, f"SYNTAX_ERROR: {exc}", 0))
            continue

        if ast.get_docstring(tree) is None:
            report.missing_module_docstrings.append(path)

        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue

            if ast.get_docstring(node) is not None:
                continue

            line = getattr(node, "lineno", 0)
            if node.name.startswith("_"):
                report.missing_private_docstrings.append((path, node.name, line))
            else:
                report.missing_public_docstrings.append((path, node.name, line))

    return report


def _print_report(report: CoverageReport) -> None:
    print("Documentation coverage check")
    print(f"Roots: {', '.join(TARGET_ROOTS)}")
    print()

    if report.missing_module_docstrings:
        print("ERROR: Missing module docstring:")
        for path in report.missing_module_docstrings:
            print(f"  - {path}")
        print()

    if report.missing_public_docstrings:
        print("ERROR: Missing public callable docstring:")
        for path, name, line in report.missing_public_docstrings:
            print(f"  - {path}:{line} -> {name}")
        print()

    if report.missing_private_docstrings:
        print("WARN: Missing private callable docstring (recommended):")
        for path, name, line in report.missing_private_docstrings:
            print(f"  - {path}:{line} -> {name}")
        print()

    if not (
        report.missing_module_docstrings
        or report.missing_public_docstrings
        or report.missing_private_docstrings
    ):
        print("OK: 100% module/public docstring coverage. No private warnings.")


def main() -> int:
    report = _collect_report()
    _print_report(report)
    return 1 if report.has_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
