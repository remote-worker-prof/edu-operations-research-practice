"""Golden tests for the math-first ORX v2 teaching examples."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from agent_core.declarative_orx import (
    BoundModelInput,
    compile_orx_model,
    solve_compiled_model,
)
from agent_core.declarative_orx_v2 import parse_orx_model_v2

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLES_ROOT = _REPO_ROOT / "docs" / "examples" / "student_math_v2"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _bound_input_from_yaml(model, payload: dict) -> BoundModelInput:
    sets = {name: tuple(values) for name, values in payload["sets"].items()}
    params: dict[str, object] = {}
    raw_params = payload["params"]
    for declaration in model.required_input_params:
        raw_value = raw_params[declaration.name]
        if not declaration.index_sets:
            params[declaration.name] = float(raw_value)
            continue
        if len(declaration.index_sets) == 1:
            set_name = declaration.index_sets[0]
            params[declaration.name] = {
                key: float(raw_value[key])
                for key in sets[set_name]
            }
            continue

        index_sets = declaration.index_sets
        keyed_values: dict[tuple[str, ...], float] = {}
        if len(index_sets) == 2:
            left_keys = sets[index_sets[0]]
            right_keys = sets[index_sets[1]]
            for left in left_keys:
                for right in right_keys:
                    keyed_values[(left, right)] = float(raw_value[left][right])
            params[declaration.name] = keyed_values
            continue
        raise AssertionError(f"Unsupported teaching example arity: {declaration.index_sets}")
    return BoundModelInput(sets=sets, params=params)


def test_math_first_examples_parse_solve_and_match_annotated_variants() -> None:
    cases = {
        "diet_blending": 86.0 / 11.0,
        "production_planning": 52.0,
        "transportation": 190.0,
    }

    for example_name, expected_objective in cases.items():
        compact_path = _EXAMPLES_ROOT / example_name / "model.orx"
        annotated_path = _EXAMPLES_ROOT / example_name / "tutorial" / "model.annotated.orx"
        data_path = _EXAMPLES_ROOT / example_name / "demo_data.yaml"

        compact_model = compile_orx_model(
            parse_orx_model_v2(compact_path.read_text(encoding="utf-8"))
        )
        annotated_model = compile_orx_model(
            parse_orx_model_v2(annotated_path.read_text(encoding="utf-8"))
        )
        assert compact_model == annotated_model

        bound_input = _bound_input_from_yaml(compact_model, _load_yaml(data_path))
        result = solve_compiled_model(compact_model, bound_input)
        assert result.objective_value == pytest.approx(expected_objective)
