"""Unit tests for the student_v1 scaffold generator."""

from __future__ import annotations

import pytest
import yaml
from agent_core.declarative_extensions import load_declarative_provider
from agent_core.extension_check import validate_bundle
from agent_core.extension_scaffold import (
    build_scaffold_spec,
    main,
    render_bundle_files,
    scaffold_bundle,
)

_DOCS_ARGS = [
    "consultation_planner",
    "--title",
    "Планировщик консультаций",
    "--entity-singular-ru",
    "консультация",
    "--entity-plural-ru",
    "консультации",
    "--resource-label-ru",
    "часы преподавателя",
    "--set-symbol",
    "CONSULTATIONS",
]


def _spec():
    return build_scaffold_spec(
        alias="consultation_planner",
        title="Планировщик консультаций",
        entity_singular_ru="консультация",
        entity_plural_ru="консультации",
        resource_label_ru="часы преподавателя",
        set_symbol="CONSULTATIONS",
    )


def test_render_bundle_files_produces_expected_student_v1_tree() -> None:
    """The renderer should generate the full compact+tutorial bundle from one spec."""
    rendered = render_bundle_files(_spec())

    assert set(rendered.files) == {
        "extension.yaml",
        "model.orx",
        "presets/demo.yaml",
        "tutorial/extension.annotated.yaml",
        "tutorial/model.annotated.orx",
        "tutorial/README.ru.md",
    }

    compact_config = yaml.safe_load(rendered.files["extension.yaml"])
    assert compact_config["format"] == "student_v1"
    assert compact_config["extension"]["alias"] == "consultation_planner"
    assert compact_config["wizard"][0]["table"]["set"] == "CONSULTATIONS"
    assert compact_config["results"]["show"][-1] == "allocation_plan"
    assert "aliases:" not in rendered.files["extension.yaml"]
    assert "set CONSULTATIONS" in rendered.files["model.orx"]
    assert "report allocation_plan by i in CONSULTATIONS:" in rendered.files["model.orx"]


def test_scaffold_bundle_writes_valid_bundle_and_solves_demo(tmp_path) -> None:
    """A generated scaffold should validate and solve its demo preset immediately."""
    result = scaffold_bundle(workspace_root=tmp_path, spec=_spec())

    assert result.bundle_root == tmp_path / "extensions" / "consultation_planner"
    assert result.validation_report.manifest_alias == "consultation_planner"
    assert result.validation_report.validated_presets == 1
    assert result.validation_report.tutorial_validated == 1

    provider = load_declarative_provider(result.bundle_root)
    runtime = provider.create_runtime()
    preset = provider.load_preset("demo")

    assert runtime.validate_draft(preset) == {
        "items": [],
        "budget": [],
        "priorities": [],
    }

    solution = runtime.run(runtime.build_runtime_input(preset))
    assert solution["total_available_units"] == pytest.approx(48.0)
    assert solution["remaining_units"] == pytest.approx(0.0)
    assert solution["achieved_weighted_score"] == pytest.approx(20.4)
    assert solution["allocation_plan"][0]["item"] == "консультация 1"


def test_scaffold_cli_main_generates_bundle_from_docs_example(
    tmp_path, monkeypatch, capsys
) -> None:
    """The documented CLI example should create a bundle that validates cleanly."""
    monkeypatch.chdir(tmp_path)

    exit_code = main(_DOCS_ARGS)
    stdout = capsys.readouterr().out

    assert exit_code == 0
    bundle_root = tmp_path / "extensions" / "consultation_planner"
    assert validate_bundle(bundle_root).manifest_alias == "consultation_planner"
    assert "make extension-check EXT=consultation_planner" in stdout
    assert "make dev" in stdout


def test_scaffold_cli_main_refuses_existing_bundle_directory(tmp_path, monkeypatch, capsys) -> None:
    """The CLI should fail safely instead of overwriting an existing extension folder."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "extensions" / "consultation_planner").mkdir(parents=True)

    exit_code = main(_DOCS_ARGS)
    stdout = capsys.readouterr().out

    assert exit_code == 1
    assert "уже существует" in stdout
