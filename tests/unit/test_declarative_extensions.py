"""Unit tests for declarative YAML + ORX extensions."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest
from agent_core.declarative_extensions import load_declarative_bundle, load_declarative_provider
from agent_core.declarative_orx import DeclarativeModelError, compile_orx_model, parse_orx_model
from agent_core.extensions import tolerant_discovery_report

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_declarative_study_planner_bundle_loads_and_solves_demo_preset() -> None:
    """The file-based study_planner bundle should validate and solve its demo preset."""
    provider = load_declarative_provider(_REPO_ROOT / "extensions" / "study_planner")
    runtime = provider.create_runtime()
    preset = provider.load_preset("demo")

    assert runtime.validate_draft(preset) == {
        "courses": [],
        "time_budget": [],
        "priorities": [],
    }

    result = runtime.run(runtime.build_runtime_input(preset))
    assert result["total_available_hours"] == 48.0
    assert result["achieved_weighted_score"] == 20.4
    assert result["course_plan"][0]["course"] == "Math"
    assert result["course_plan"][0]["allocated_hours"] == 30.0
    assert provider.get_manifest().ui_metadata["dsl_format"] == "student_v1"


def test_tolerant_discovery_report_discovers_file_bundles() -> None:
    """Startup discovery should include declarative bundles alongside the built-in extension."""
    report = tolerant_discovery_report(entry_points=[], bundle_root=_REPO_ROOT / "extensions")

    assert report.registry.aliases() == ["default_or", "study_planner"]
    assert report.warnings == []


def test_orx_rejects_unknown_symbols() -> None:
    """Static model validation should fail fast on undeclared symbols."""
    source = """
param capacity
var x >= 0
maximize objective: x
st capacity_limit: x <= demand
report total = x
"""
    with pytest.raises(DeclarativeModelError, match="нигде не объявлено"):
        compile_orx_model(parse_orx_model(source))


def test_orx_rejects_nonlinear_products_of_variables() -> None:
    """LP v1 must reject nonlinear decision-variable products."""
    source = """
var x >= 0
var y >= 0
maximize objective: x * y
st budget: x + y <= 10
report total = x + y
"""
    with pytest.raises(DeclarativeModelError, match="нелинейное произведение"):
        compile_orx_model(parse_orx_model(source))


def test_orx_accepts_comments_range_bounds_and_block_reports() -> None:
    """Student-friendly ORX sugar should compile into the same LP IR."""
    source = """
# Строка-комментарий должна игнорироваться парсером.
set ITEMS

param limit
param weight[ITEMS]

var x[ITEMS] in 0..weight[ITEMS]  # Хвостовой комментарий тоже допустим.

maximize objective:
    sum(i in ITEMS, x[i])

st total:
    sum(i in ITEMS, x[i]) <= limit

report total = sum(i in ITEMS, x[i])
report plan by i in ITEMS:
    item = i
    assigned = x[i]
"""
    compiled = compile_orx_model(parse_orx_model(source))

    assert compiled.var_names == frozenset({"x"})
    assert compiled.vars[0].lower is not None
    assert compiled.vars[0].upper is not None
    assert compiled.table_reports[0].name == "plan"
    assert compiled.table_reports[0].fields[0].name == "item"


def test_study_planner_tutorial_bundle_matches_compact_bundle() -> None:
    """Annotated tutorial files must stay semantically equivalent to compact runtime files."""
    compact = load_declarative_bundle(_REPO_ROOT / "extensions" / "study_planner")
    annotated = load_declarative_bundle(
        _REPO_ROOT / "extensions" / "study_planner",
        config_filename="tutorial/extension.annotated.yaml",
        model_filename="tutorial/model.annotated.orx",
    )

    assert compact.manifest.model_dump(mode="json") == annotated.manifest.model_dump(mode="json")
    assert compact.config.model_dump(mode="json") == annotated.config.model_dump(mode="json")
    assert asdict(compact.model) == asdict(annotated.model)
