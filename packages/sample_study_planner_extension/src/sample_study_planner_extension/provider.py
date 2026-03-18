"""Study-planner sample extension provider and deterministic runtime."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from extension_api import (
    ExtensionManifest,
    ExtensionResultSection,
    FieldSpec,
    KVBlock,
    KVItem,
    StageSpec,
    SummaryBlock,
    TableBlock,
)

_MANIFEST = ExtensionManifest(
    alias="study_planner",
    title="Study Planner",
    description=(
        "Учебное расширение для планирования учебной нагрузки без привязки к OR solver-ам."
    ),
    version="0.1.0",
    default_preset="demo",
    stage_graph=[
        StageSpec(
            stage_id="courses",
            label="Курсы",
            aliases=["course", "courses", "курс", "курсы"],
            examples=[
                'json courses {"names":["Math","ML","Databases"],"hours_required":[30,24,18]}'
            ],
            field_specs=[
                FieldSpec(
                    field_path="names",
                    label="Названия курсов",
                    description="Список курсов, которые студент хочет изучать.",
                    examples=['["Math","ML","Databases"]'],
                ),
                FieldSpec(
                    field_path="hours_required",
                    label="Требуемые часы",
                    description="Сколько часов нужно на каждый курс.",
                    value_type="list[number]",
                    examples=["[30,24,18]"],
                ),
            ],
        ),
        StageSpec(
            stage_id="time_budget",
            label="Бюджет времени",
            aliases=["time_budget", "time", "budget", "время", "бюджет"],
            examples=['json time_budget {"weekly_hours":12,"weeks":4}'],
            field_specs=[
                FieldSpec(
                    field_path="weekly_hours",
                    label="Часов в неделю",
                    description="Сколько часов в неделю студент может реально выделить.",
                    value_type="number",
                    examples=["12"],
                ),
                FieldSpec(
                    field_path="weeks",
                    label="Количество недель",
                    description="На сколько недель строится учебный план.",
                    value_type="number",
                    examples=["4"],
                ),
            ],
        ),
        StageSpec(
            stage_id="priorities",
            label="Приоритеты",
            depends_on=["courses"],
            aliases=["priorities", "priority", "веса", "приоритеты"],
            examples=['json priorities {"weights":[0.5,0.3,0.2]}'],
            field_specs=[
                FieldSpec(
                    field_path="weights",
                    label="Веса приоритетов",
                    description=(
                        "Относительная важность каждого курса в том же порядке, что и names."
                    ),
                    value_type="list[number]",
                    examples=["[0.5,0.3,0.2]"],
                ),
            ],
        ),
    ],
    stage_aliases={
        "courses": ["course", "courses", "курс", "курсы"],
        "time_budget": ["time_budget", "time", "budget", "время", "бюджет"],
        "priorities": ["priority", "priorities", "приоритет", "приоритеты", "веса"],
    },
    examples=[
        "start",
        "load preset demo",
        'json courses {"names":["Math","ML","Databases"],"hours_required":[30,24,18]}',
        'json time_budget {"weekly_hours":12,"weeks":4}',
        'json priorities {"weights":[0.5,0.3,0.2]}',
        "run",
    ],
    ui_metadata={"kind": "study_planner"},
)

_PRESETS: dict[str, dict[str, dict[str, Any]]] = {
    "demo": {
        "courses": {
            "names": ["Math", "ML", "Databases"],
            "hours_required": [30, 24, 18],
        },
        "time_budget": {
            "weekly_hours": 12,
            "weeks": 4,
        },
        "priorities": {
            "weights": [0.5, 0.3, 0.2],
        },
    }
}


def _coerce_number_list(value: object) -> list[float] | None:
    """Normalizes a list-like value into floats when possible."""
    if not isinstance(value, list) or not value:
        return None
    normalized: list[float] = []
    for item in value:
        if not isinstance(item, (int, float)):
            return None
        normalized.append(float(item))
    return normalized


def _coerce_string_list(value: object) -> list[str] | None:
    """Normalizes a list-like value into a non-empty list of strings."""
    if not isinstance(value, list) or not value:
        return None
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return None
        normalized.append(item.strip())
    return normalized


@dataclass(frozen=True)
class _StudyPlanRow:
    """One deterministic recommendation row for the sample extension."""

    course: str
    required_hours: float
    recommended_hours: float
    gap_hours: float
    weight: float


class StudyPlannerRuntime:
    """Deterministic runtime that allocates study hours by normalized weights."""

    manifest = _MANIFEST

    def validate_draft(self, draft: dict[str, object]) -> dict[str, list[str]]:
        """Validates stage payloads and returns stage-local errors."""
        errors = {stage_id: [] for stage_id in self.manifest.topological_stage_ids()}

        courses = draft.get("courses")
        courses_payload = courses if isinstance(courses, dict) else {}
        course_names = _coerce_string_list(courses_payload.get("names"))
        hours_required = _coerce_number_list(courses_payload.get("hours_required"))
        if course_names is None:
            errors["courses"].append("Поле courses.names должно быть непустым списком строк.")
        if hours_required is None:
            errors["courses"].append(
                "Поле courses.hours_required должно быть непустым списком чисел."
            )
        elif any(value <= 0 for value in hours_required):
            errors["courses"].append("Все значения courses.hours_required должны быть > 0.")
        if (
            course_names is not None
            and hours_required is not None
            and len(course_names) != len(hours_required)
        ):
            errors["courses"].append(
                "courses.names и courses.hours_required должны иметь одинаковую длину."
            )

        time_budget = draft.get("time_budget")
        time_budget_payload = time_budget if isinstance(time_budget, dict) else {}
        weekly_hours = time_budget_payload.get("weekly_hours")
        weeks = time_budget_payload.get("weeks")
        if not isinstance(weekly_hours, (int, float)) or weekly_hours <= 0:
            errors["time_budget"].append("time_budget.weekly_hours должно быть числом > 0.")
        if not isinstance(weeks, (int, float)) or weeks <= 0:
            errors["time_budget"].append("time_budget.weeks должно быть числом > 0.")

        priorities = draft.get("priorities")
        priorities_payload = priorities if isinstance(priorities, dict) else {}
        weights = _coerce_number_list(priorities_payload.get("weights"))
        if course_names is None:
            errors["priorities"].append("Сначала заполните stage courses, затем priorities.")
        if weights is None:
            errors["priorities"].append(
                "Поле priorities.weights должно быть непустым списком чисел."
            )
        else:
            if any(value <= 0 for value in weights):
                errors["priorities"].append("Все значения priorities.weights должны быть > 0.")
            if sum(weights) <= 0:
                errors["priorities"].append("Сумма priorities.weights должна быть > 0.")
            if course_names is not None and len(weights) != len(course_names):
                errors["priorities"].append(
                    "Длина priorities.weights должна совпадать с числом курсов."
                )

        return errors

    def build_runtime_input(self, draft: dict[str, object]) -> dict[str, object]:
        """Builds a normalized deterministic input from the generic stage draft."""
        courses = draft["courses"]
        time_budget = draft["time_budget"]
        priorities = draft["priorities"]
        assert isinstance(courses, dict)
        assert isinstance(time_budget, dict)
        assert isinstance(priorities, dict)
        return {
            "courses": _coerce_string_list(courses["names"]),
            "hours_required": _coerce_number_list(courses["hours_required"]),
            "weekly_hours": float(time_budget["weekly_hours"]),
            "weeks": float(time_budget["weeks"]),
            "weights": _coerce_number_list(priorities["weights"]),
        }

    def run(self, runtime_input: object) -> dict[str, object]:
        """Computes a deterministic recommended study plan."""
        if not isinstance(runtime_input, dict):  # pragma: no cover - defensive contract guard
            raise TypeError("StudyPlannerRuntime expects dict runtime_input")

        course_names = runtime_input["courses"]
        hours_required = runtime_input["hours_required"]
        weights = runtime_input["weights"]
        weekly_hours = float(runtime_input["weekly_hours"])
        weeks = float(runtime_input["weeks"])

        assert isinstance(course_names, list)
        assert isinstance(hours_required, list)
        assert isinstance(weights, list)

        total_available_hours = weekly_hours * weeks
        total_required_hours = float(sum(hours_required))
        weight_sum = float(sum(weights))

        rows: list[dict[str, float | str]] = []
        total_recommended_hours = 0.0
        for name, required, weight in zip(course_names, hours_required, weights, strict=True):
            proportional_hours = total_available_hours * float(weight) / weight_sum
            recommended_hours = min(float(required), proportional_hours)
            gap_hours = max(float(required) - recommended_hours, 0.0)
            total_recommended_hours += recommended_hours
            rows.append(
                {
                    "course": str(name),
                    "required_hours": float(required),
                    "recommended_hours": round(recommended_hours, 2),
                    "gap_hours": round(gap_hours, 2),
                    "weight": float(weight),
                }
            )

        return {
            "total_available_hours": round(total_available_hours, 2),
            "total_required_hours": round(total_required_hours, 2),
            "total_recommended_hours": round(total_recommended_hours, 2),
            "fully_covered_courses": sum(1 for row in rows if float(row["gap_hours"]) == 0.0),
            "course_plan": rows,
        }

    def fallback_explain(self, result: object) -> str:
        """Returns a deterministic human explanation for the study plan."""
        if not isinstance(result, dict):  # pragma: no cover - defensive contract guard
            return "Получен детерминированный план распределения учебного времени."
        return (
            "План построен детерминированно: общий бюджет времени распределён по курсам "
            "пропорционально приоритетам, но каждая рекомендация ограничена сверху "
            "реальной потребностью курса."
        )

    def build_llm_explain_prompt(self, result: object) -> str:
        """Builds a plain prompt string if an explanation model is needed later."""
        return (
            "Explain this deterministic study plan for a student. Focus on available hours, "
            "priority weights, capped recommendations, and the remaining gaps.\n"
            f"Result: {result!r}"
        )

    def build_result_sections(self, result: object) -> list[ExtensionResultSection]:
        """Builds generic data-driven UI sections for the result panel."""
        if not isinstance(result, dict):  # pragma: no cover - defensive contract guard
            return []

        rows = result.get("course_plan", [])
        table_rows = [
            [
                row["course"],
                row["required_hours"],
                row["recommended_hours"],
                row["gap_hours"],
            ]
            for row in rows
            if isinstance(row, dict)
        ]

        return [
            ExtensionResultSection(
                section_id="study-plan-summary",
                title="Итог плана",
                blocks=[
                    SummaryBlock(
                        text=(
                            "Study Planner распределил доступные часы по курсам пропорционально "
                            "приоритетам и показал, где остаётся учебный дефицит."
                        )
                    )
                ],
            ),
            ExtensionResultSection(
                section_id="study-plan-budget",
                title="Сводка бюджета",
                blocks=[
                    KVBlock(
                        items=[
                            KVItem(key="Доступно часов", value=result["total_available_hours"]),
                            KVItem(key="Нужно часов", value=result["total_required_hours"]),
                            KVItem(
                                key="Рекомендовано часов",
                                value=result["total_recommended_hours"],
                            ),
                            KVItem(
                                key="Полностью закрыто курсов",
                                value=result["fully_covered_courses"],
                            ),
                        ]
                    )
                ],
            ),
            ExtensionResultSection(
                section_id="study-plan-table",
                title="Рекомендации по курсам",
                blocks=[
                    TableBlock(
                        columns=["Курс", "Нужно", "Рекомендовано", "Нехватка"],
                        rows=table_rows,
                    )
                ],
            ),
        ]

    def build_teaching_hints(self, draft: dict[str, object]) -> list[dict[str, object]]:
        """Returns lightweight field hints for future UI integrations."""
        del draft
        return [
            {
                "field": "courses.hours_required",
                "meaning": "Полная трудоёмкость каждого курса.",
                "units": "часы",
                "example": "[30,24,18]",
            },
            {
                "field": "priorities.weights",
                "meaning": "Относительная важность курсов.",
                "units": "безразмерные веса",
                "example": "[0.5,0.3,0.2]",
            },
        ]

    def build_nl_semantics(self) -> dict[str, object]:
        """Returns extension-local NLP hints reserved for future work."""
        return {"supported": False}


class StudyPlannerExtensionProvider:
    """Installable provider exported through the extension entry-point group."""

    def get_manifest(self) -> ExtensionManifest:
        return _MANIFEST

    def create_runtime(self) -> StudyPlannerRuntime:
        return StudyPlannerRuntime()

    def load_preset(self, preset_ref: str) -> dict[str, dict[str, Any]]:
        """Returns one built-in deterministic preset for the sample extension."""
        try:
            payload = _PRESETS[preset_ref]
        except KeyError as exc:
            raise ValueError(f"Unsupported study_planner preset: {preset_ref}") from exc
        return deepcopy(payload)
