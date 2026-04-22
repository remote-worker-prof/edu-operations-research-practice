"""CLI scaffold generator for student_math_v2 declarative extension bundles."""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Literal

import yaml

from agent_core.extension_check import BundleValidationReport, validate_bundle

_ALIAS_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_SYMBOL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class ScaffoldSpec:
    alias: str
    title: str
    resource_label_ru: str
    template_family: Literal["allocation", "transportation"] = "allocation"
    entity_singular_ru: str | None = None
    entity_plural_ru: str | None = None
    set_symbol: str = "ITEMS"
    row_entity_singular_ru: str | None = None
    row_entity_plural_ru: str | None = None
    col_entity_singular_ru: str | None = None
    col_entity_plural_ru: str | None = None
    row_set_symbol: str = "ORIGINS"
    col_set_symbol: str = "DESTINATIONS"

    @property
    def is_allocation(self) -> bool:
        return self.template_family == "allocation"

    @property
    def is_transportation(self) -> bool:
        return self.template_family == "transportation"

    @property
    def description(self) -> str:
        if self.is_allocation:
            return (
                f"Учебное расширение для распределения ограниченного ресурса "
                f'"{self.resource_label_ru}" '
                f'между объектами типа "{self.entity_plural_ru}".'
            )
        return (
            f"Учебное расширение для транспортной LP-задачи: как распределить "
            f'"{self.resource_label_ru}" из "{self.row_entity_plural_ru}" '
            f'в "{self.col_entity_plural_ru}" с минимальной стоимостью.'
        )

    @property
    def example_items(self) -> tuple[str, str, str]:
        assert self.entity_singular_ru is not None
        return tuple(f"{self.entity_singular_ru} {index}" for index in range(1, 4))

    @property
    def example_rows(self) -> tuple[str, str]:
        assert self.row_entity_singular_ru is not None
        return (
            f"{self.row_entity_singular_ru} 1",
            f"{self.row_entity_singular_ru} 2",
        )

    @property
    def example_cols(self) -> tuple[str, str]:
        assert self.col_entity_singular_ru is not None
        return (
            f"{self.col_entity_singular_ru} 1",
            f"{self.col_entity_singular_ru} 2",
        )

    @property
    def resource_label_with_unit(self) -> str:
        return self.resource_label_ru


@dataclass(frozen=True, slots=True)
class ScaffoldResult:
    bundle_root: Path
    validation_report: BundleValidationReport
    written_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RenderedBundle:
    files: dict[str, str]


class ScaffoldError(ValueError):
    """Raised when scaffold input or file generation is invalid."""


def build_scaffold_spec(
    *,
    alias: str,
    title: str,
    resource_label_ru: str,
    template_family: Literal["allocation", "transportation"] = "allocation",
    entity_singular_ru: str | None = None,
    entity_plural_ru: str | None = None,
    set_symbol: str = "ITEMS",
    row_entity_singular_ru: str | None = None,
    row_entity_plural_ru: str | None = None,
    col_entity_singular_ru: str | None = None,
    col_entity_plural_ru: str | None = None,
    row_set_symbol: str = "ORIGINS",
    col_set_symbol: str = "DESTINATIONS",
) -> ScaffoldSpec:
    normalized_alias = alias.strip()
    normalized_title = title.strip()
    normalized_resource = resource_label_ru.strip()
    normalized_set_symbol = set_symbol.strip()
    normalized_row_set_symbol = row_set_symbol.strip()
    normalized_col_set_symbol = col_set_symbol.strip()

    if not _ALIAS_RE.fullmatch(normalized_alias):
        raise ScaffoldError(
            "Alias должен соответствовать шаблону ^[a-z][a-z0-9_-]*$ для стабильного bundle name."
        )
    if not normalized_title:
        raise ScaffoldError("Параметр --title не должен быть пустым.")
    if not normalized_resource:
        raise ScaffoldError("Параметр --resource-label-ru не должен быть пустым.")
    if template_family not in {"allocation", "transportation"}:
        raise ScaffoldError("Параметр --template-family должен быть allocation или transportation.")

    if template_family == "allocation":
        normalized_singular = (entity_singular_ru or "").strip()
        normalized_plural = (entity_plural_ru or "").strip()
        if not normalized_singular:
            raise ScaffoldError("Параметр --entity-singular-ru не должен быть пустым.")
        if not normalized_plural:
            raise ScaffoldError("Параметр --entity-plural-ru не должен быть пустым.")
        if not _SYMBOL_RE.fullmatch(normalized_set_symbol):
            raise ScaffoldError(
                "SET_SYMBOL должен быть корректным ORX-идентификатором, например ITEMS или TOPICS."
            )
        return ScaffoldSpec(
            alias=normalized_alias,
            title=normalized_title,
            resource_label_ru=normalized_resource,
            template_family="allocation",
            entity_singular_ru=normalized_singular,
            entity_plural_ru=normalized_plural,
            set_symbol=normalized_set_symbol,
        )

    normalized_row_singular = (row_entity_singular_ru or "").strip()
    normalized_row_plural = (row_entity_plural_ru or "").strip()
    normalized_col_singular = (col_entity_singular_ru or "").strip()
    normalized_col_plural = (col_entity_plural_ru or "").strip()
    if not normalized_row_singular:
        raise ScaffoldError("Параметр --row-entity-singular-ru не должен быть пустым.")
    if not normalized_row_plural:
        raise ScaffoldError("Параметр --row-entity-plural-ru не должен быть пустым.")
    if not normalized_col_singular:
        raise ScaffoldError("Параметр --col-entity-singular-ru не должен быть пустым.")
    if not normalized_col_plural:
        raise ScaffoldError("Параметр --col-entity-plural-ru не должен быть пустым.")
    if not _SYMBOL_RE.fullmatch(normalized_row_set_symbol):
        raise ScaffoldError(
            "ROW_SET_SYMBOL должен быть корректным ORX-идентификатором, например ORIGINS."
        )
    if not _SYMBOL_RE.fullmatch(normalized_col_set_symbol):
        raise ScaffoldError(
            "COL_SET_SYMBOL должен быть корректным ORX-идентификатором, например DESTINATIONS."
        )
    return ScaffoldSpec(
        alias=normalized_alias,
        title=normalized_title,
        resource_label_ru=normalized_resource,
        template_family="transportation",
        row_entity_singular_ru=normalized_row_singular,
        row_entity_plural_ru=normalized_row_plural,
        col_entity_singular_ru=normalized_col_singular,
        col_entity_plural_ru=normalized_col_plural,
        row_set_symbol=normalized_row_set_symbol,
        col_set_symbol=normalized_col_set_symbol,
    )


def render_bundle_files(spec: ScaffoldSpec) -> RenderedBundle:
    if spec.is_allocation:
        files = {
            "extension.yaml": _render_allocation_extension_yaml(spec),
            "model.orx": _render_allocation_model_orx(spec),
            "presets/demo.yaml": _render_allocation_demo_preset(spec),
            "tutorial/extension.annotated.yaml": _render_allocation_annotated_extension_yaml(spec),
            "tutorial/model.annotated.orx": _render_allocation_annotated_model_orx(spec),
            "tutorial/README.ru.md": _render_allocation_tutorial_readme(spec),
        }
    else:
        files = {
            "extension.yaml": _render_transportation_extension_yaml(spec),
            "model.orx": _render_transportation_model_orx(spec),
            "presets/demo.yaml": _render_transportation_demo_preset(spec),
            "tutorial/extension.annotated.yaml": (
                _render_transportation_annotated_extension_yaml(spec)
            ),
            "tutorial/model.annotated.orx": _render_transportation_annotated_model_orx(spec),
            "tutorial/README.ru.md": _render_transportation_tutorial_readme(spec),
        }
    return RenderedBundle(files=files)


def scaffold_bundle(*, workspace_root: Path, spec: ScaffoldSpec) -> ScaffoldResult:
    extensions_root = workspace_root / "extensions"
    bundle_root = extensions_root / spec.alias
    if bundle_root.exists():
        raise ScaffoldError(f"Scaffold не может быть создан: папка `{bundle_root}` уже существует.")

    rendered = render_bundle_files(spec)
    extensions_root.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=f".{spec.alias}-scaffold-", dir=extensions_root))
    try:
        _write_rendered_bundle(temp_root, rendered)
        report = validate_bundle(temp_root)
        temp_root.rename(bundle_root)
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise

    return ScaffoldResult(
        bundle_root=bundle_root,
        validation_report=report,
        written_files=tuple(sorted(rendered.files)),
    )


def _write_rendered_bundle(bundle_root: Path, rendered: RenderedBundle) -> None:
    for relative_path, content in rendered.files.items():
        file_path = bundle_root / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")


def _render_allocation_extension_yaml(spec: ScaffoldSpec) -> str:
    payload = {
        "format": "student_math_v2",
        "extension": {
            "alias": spec.alias,
            "title": spec.title,
            "description": spec.description,
            "version": "0.1.0",
            "default_preset": "demo",
            "labels": {
                "total_available_units": f"Всего ресурса ({spec.resource_label_with_unit})",
                "total_required_units": f"Сколько ресурса нужно ({spec.resource_label_with_unit})",
                "total_allocated_units": (
                    f"Сколько ресурса распределили ({spec.resource_label_with_unit})"
                ),
                "remaining_units": f"Сколько ресурса осталось ({spec.resource_label_with_unit})",
                "achieved_weighted_score": "Суммарная полезность плана",
                "allocation_plan": f"План распределения для {spec.entity_plural_ru}",
                "allocation_plan.item": spec.entity_singular_ru,
                "allocation_plan.required_units": "Требуемый объём",
                "allocation_plan.allocated_units": "Распределённый объём",
                "allocation_plan.gap_units": "Нехватка ресурса",
                "allocation_plan.priority": "Вес приоритета",
                "allocation_plan.coverage_ratio": "Доля покрытия",
                "allocation_plan.coverage_ratio_pct": "Покрытие, %",
            },
        },
        "inputs": [
            {
                "id": "items",
                "label": spec.entity_plural_ru,
                "table": {
                    "set": spec.set_symbol,
                    "key": {
                        "field": "item_names",
                        "label": spec.entity_plural_ru,
                        "help": (
                            f"Перечислите {spec.entity_plural_ru.lower()} в том порядке, "
                            "в котором будете задавать остальные списки."
                        ),
                        "example": spec.example_items[0],
                    },
                    "columns": [
                        {
                            "param": "required_units",
                            "field": "required_units",
                            "label": f"Требуемый объём ({spec.resource_label_with_unit})",
                            "help": (
                                f'Сколько ресурса "{spec.resource_label_ru}" нужно, '
                                "чтобы полностью закрыть каждый объект."
                            ),
                            "type": "number",
                            "min": 0.0001,
                            "example": 30,
                        }
                    ],
                },
            },
            {
                "id": "budget",
                "label": "Бюджет ресурса",
                "params": [
                    {
                        "param": "available_units",
                        "field": "available_units",
                        "label": f"Доступный объём ({spec.resource_label_with_unit})",
                        "help": (
                            f'Сколько ресурса "{spec.resource_label_ru}" есть всего '
                            "для распределения."
                        ),
                        "type": "number",
                        "min": 0.0001,
                        "example": 48,
                    }
                ],
            },
            {
                "id": "priorities",
                "label": "Приоритеты",
                "vectors": [
                    {
                        "param": "priority",
                        "over": spec.set_symbol,
                        "field": "priority",
                        "label": f"Веса приоритетов для {spec.entity_plural_ru}",
                        "help": (
                            f"Чем выше число, тем полезнее дополнительная единица ресурса "
                            f'"{spec.resource_label_ru}" для данного объекта.'
                        ),
                        "type": "number",
                        "min": 0.0001,
                        "example": [0.5, 0.3, 0.2],
                    }
                ],
            },
        ],
        "display": {
            "summary": [
                {"id": "total_available_units", "expr": "available_units"},
                {
                    "id": "total_required_units",
                    "expr": f"sum{{i in {spec.set_symbol}}} required_units[i]",
                },
                {
                    "id": "total_allocated_units",
                    "expr": f"sum{{i in {spec.set_symbol}}} allocated_units[i]",
                },
                {
                    "id": "remaining_units",
                    "expr": (f"available_units - sum{{i in {spec.set_symbol}}} allocated_units[i]"),
                },
                {
                    "id": "achieved_weighted_score",
                    "expr": (f"sum{{i in {spec.set_symbol}}} priority[i] * allocated_units[i]"),
                },
            ],
            "tables": [
                {
                    "id": "allocation_plan",
                    "rows": f"i in {spec.set_symbol}",
                    "columns": [
                        {"id": "item", "expr": "i"},
                        {"id": "required_units", "expr": "required_units[i]"},
                        {"id": "allocated_units", "expr": "allocated_units[i]"},
                        {
                            "id": "gap_units",
                            "expr": "required_units[i] - allocated_units[i]",
                        },
                        {"id": "priority", "expr": "priority[i]"},
                        {
                            "id": "coverage_ratio",
                            "expr": "allocated_units[i] / required_units[i]",
                        },
                        {
                            "id": "coverage_ratio_pct",
                            "expr": "100 * allocated_units[i] / required_units[i]",
                        },
                    ],
                }
            ],
        },
        "presets": {"demo": "presets/demo.yaml"},
    }
    return _yaml_dump(payload)


def _render_allocation_model_orx(spec: ScaffoldSpec) -> str:
    return dedent(
        f"""\
        # Math-first allocation-style LP model generated by the student_math_v2 scaffold.
        # This file contains only the optimization model.

        set {spec.set_symbol};

        param available_units;
        param required_units{{{spec.set_symbol}}};
        param priority{{{spec.set_symbol}}};

        var allocated_units{{i in {spec.set_symbol}}} >= 0 <= required_units[i];

        maximize allocation_score:
            sum{{i in {spec.set_symbol}}} priority[i] * allocated_units[i];

        subject to total_budget:
            sum{{i in {spec.set_symbol}}} allocated_units[i] <= available_units;
        """
    )


def _render_allocation_demo_preset(spec: ScaffoldSpec) -> str:
    payload = {
        "items": {
            "item_names": list(spec.example_items),
            "required_units": [30, 24, 18],
        },
        "budget": {"available_units": 48},
        "priorities": {"priority": [0.5, 0.3, 0.2]},
    }
    return _yaml_dump(payload)


def _render_allocation_annotated_extension_yaml(spec: ScaffoldSpec) -> str:
    items_label = spec.entity_plural_ru
    resource = spec.resource_label_ru
    return dedent(
        f"""\
        # Это учебная, подробно прокомментированная версия extension.yaml.
        # Она исполняемая: валидатор должен уметь загрузить её так же, как и обычный файл.

        format: student_math_v2

        extension:
          alias: {spec.alias}
          title: {spec.title}
          description: >-
            Учебное расширение для распределения ограниченного ресурса "{resource}"
            между объектами типа "{items_label}".
          version: 0.1.0
          default_preset: demo
          labels:
            total_available_units: Всего ресурса ({spec.resource_label_with_unit})
            total_required_units: Сколько ресурса нужно ({spec.resource_label_with_unit})
            total_allocated_units: Сколько ресурса распределили ({spec.resource_label_with_unit})
            remaining_units: Сколько ресурса осталось ({spec.resource_label_with_unit})
            achieved_weighted_score: Суммарная полезность плана
            allocation_plan: План распределения для {items_label}
            allocation_plan.item: {spec.entity_singular_ru}
            allocation_plan.required_units: Требуемый объём
            allocation_plan.allocated_units: Распределённый объём
            allocation_plan.gap_units: Нехватка ресурса
            allocation_plan.priority: Вес приоритета
            allocation_plan.coverage_ratio: Доля покрытия
            allocation_plan.coverage_ratio_pct: Покрытие, %

        # inputs отвечает за то, какие данные вводит студент.
        inputs:
          - id: items
            label: {items_label}
            table:
              # set показывает, какое множество в модели мы наполняем.
              set: {spec.set_symbol}
              key:
                field: item_names
                label: {items_label}
                help: >-
                  Перечислите {items_label.lower()} в том порядке,
                  в котором будете задавать остальные списки.
                example: {spec.example_items[0]}
              columns:
                - param: required_units
                  field: required_units
                  label: Требуемый объём ({spec.resource_label_with_unit})
                  help: >-
                    Сколько ресурса "{resource}" нужно,
                    чтобы полностью закрыть каждый объект.
                  type: number
                  min: 0.0001
                  example: 30

          - id: budget
            label: Бюджет ресурса
            params:
              - param: available_units
                field: available_units
                label: Доступный объём ({spec.resource_label_with_unit})
                help: >-
                  Сколько ресурса "{resource}" есть всего для распределения.
                type: number
                min: 0.0001
                example: 48

          - id: priorities
            label: Приоритеты
            vectors:
              - param: priority
                over: {spec.set_symbol}
                field: priority
                label: Веса приоритетов для {items_label}
                help: >-
                  Чем выше число, тем полезнее дополнительная единица ресурса
                  "{resource}" для данного объекта.
                type: number
                min: 0.0001
                example:
                  - 0.5
                  - 0.3
                  - 0.2

        # display описывает, что показывать после решения.
        display:
          summary:
            - id: total_available_units
              expr: available_units
            - id: total_required_units
              expr: sum{{i in {spec.set_symbol}}} required_units[i]
            - id: total_allocated_units
              expr: sum{{i in {spec.set_symbol}}} allocated_units[i]
            - id: remaining_units
              expr: available_units - sum{{i in {spec.set_symbol}}} allocated_units[i]
            - id: achieved_weighted_score
              expr: sum{{i in {spec.set_symbol}}} priority[i] * allocated_units[i]
          tables:
            - id: allocation_plan
              rows: i in {spec.set_symbol}
              columns:
                - id: item
                  expr: i
                - id: required_units
                  expr: required_units[i]
                - id: allocated_units
                  expr: allocated_units[i]
                - id: gap_units
                  expr: required_units[i] - allocated_units[i]
                - id: priority
                  expr: priority[i]
                - id: coverage_ratio
                  expr: allocated_units[i] / required_units[i]
                - id: coverage_ratio_pct
                  expr: 100 * allocated_units[i] / required_units[i]

        presets:
          demo: presets/demo.yaml
        """
    )


def _render_allocation_annotated_model_orx(spec: ScaffoldSpec) -> str:
    resource = spec.resource_label_ru
    return dedent(
        f"""\
        # Это учебная, подробно прокомментированная версия model.orx.
        # Здесь лежит только математическая постановка задачи.

        set {spec.set_symbol};

        # available_units — сколько ресурса "{resource}" есть всего.
        param available_units;

        # required_units{{{spec.set_symbol}}} — сколько ресурса нужно каждому объекту.
        param required_units{{{spec.set_symbol}}};

        # priority{{{spec.set_symbol}}} — насколько важен каждый объект.
        param priority{{{spec.set_symbol}}};

        # allocated_units[i] — сколько ресурса реально выделить объекту i.
        var allocated_units{{i in {spec.set_symbol}}} >= 0 <= required_units[i];

        maximize allocation_score:
            sum{{i in {spec.set_symbol}}} priority[i] * allocated_units[i];

        subject to total_budget:
            sum{{i in {spec.set_symbol}}} allocated_units[i] <= available_units;
        """
    )


def _render_allocation_tutorial_readme(spec: ScaffoldSpec) -> str:
    return dedent(
        f"""\
        # {spec.title}: tutorial-версия для студентов

        ## Ментальная модель
        - `model.orx` отвечает за математическую постановку задачи.
        - `extension.yaml` отвечает за ввод данных, подписи и показ результата.
        - Python студенту не нужен.

        ## Что вводит студент
        1. Список объектов типа "{spec.entity_plural_ru}".
        2. Сколько ресурса "{spec.resource_label_ru}" нужно каждому объекту.
        3. Общий доступный объём ресурса.
        4. Веса приоритетов.

        ## Что считает модель
        - Есть множество объектов `{spec.set_symbol}`.
        - Есть параметры: потребности, приоритеты и общий бюджет.
        - Есть переменная решения `allocated_units`.
        - Цель модели: максимизировать суммарную полезность.
        - Ограничение модели: нельзя распределить больше ресурса, чем доступно.

        ## Что показывает приложение
        - Итоговые summary-значения.
        - Таблицу `allocation_plan` по каждому объекту.

        ## Как адаптировать этот пример под свой класс задач
        1. Сначала отредактируйте `model.orx`.
        2. Затем приведите `extension.yaml` в соответствие с новой моделью.
        3. После этого синхронизируйте tutorial-файлы.
        4. Проверьте bundle командой:

        ```bash
        make extension-check EXT={spec.alias}
        ```
        """
    )


def _render_transportation_extension_yaml(spec: ScaffoldSpec) -> str:
    payload = {
        "format": "student_math_v2",
        "extension": {
            "alias": spec.alias,
            "title": spec.title,
            "description": spec.description,
            "version": "0.1.0",
            "default_preset": "demo",
            "labels": {
                "total_supply": f"Всего доступно ({spec.resource_label_with_unit})",
                "total_demand": f"Всего требуется ({spec.resource_label_with_unit})",
                "total_shipped": f"Всего перевезено ({spec.resource_label_with_unit})",
                "total_cost": "Итоговая стоимость перевозки",
                "shipment_plan": "План перевозки",
                "shipment_plan.row": spec.row_entity_singular_ru.capitalize(),
            },
        },
        "inputs": [
            {
                "id": "origins",
                "label": spec.row_entity_plural_ru.capitalize(),
                "table": {
                    "set": spec.row_set_symbol,
                    "key": {
                        "field": "origin_names",
                        "label": spec.row_entity_plural_ru.capitalize(),
                        "help": (
                            f"Перечислите {spec.row_entity_plural_ru.lower()} в том порядке, "
                            "в котором строки потом пойдут в матрице тарифов."
                        ),
                        "example": spec.example_rows[0],
                    },
                    "columns": [
                        {
                            "param": "supply",
                            "field": "supply",
                            "label": f"Запас ({spec.resource_label_with_unit})",
                            "help": (
                                f'Сколько ресурса "{spec.resource_label_ru}" доступно '
                                "в каждом пункте отправления."
                            ),
                            "type": "number",
                            "min": 0.0,
                            "example": 20,
                        }
                    ],
                },
            },
            {
                "id": "destinations",
                "label": spec.col_entity_plural_ru.capitalize(),
                "table": {
                    "set": spec.col_set_symbol,
                    "key": {
                        "field": "destination_names",
                        "label": spec.col_entity_plural_ru.capitalize(),
                        "help": (
                            f"Перечислите {spec.col_entity_plural_ru.lower()} в том порядке, "
                            "в котором столбцы потом пойдут в матрице тарифов."
                        ),
                        "example": spec.example_cols[0],
                    },
                    "columns": [
                        {
                            "param": "demand",
                            "field": "demand",
                            "label": f"Потребность ({spec.resource_label_with_unit})",
                            "help": (
                                f'Сколько ресурса "{spec.resource_label_ru}" нужно '
                                "в каждом пункте назначения."
                            ),
                            "type": "number",
                            "min": 0.0,
                            "example": 15,
                        }
                    ],
                },
            },
            {
                "id": "costs",
                "label": "Матрица тарифов",
                "matrix": {
                    "rows_set": spec.row_set_symbol,
                    "cols_set": spec.col_set_symbol,
                    "fields": [
                        {
                            "param": "cost",
                            "field": "cost_matrix",
                            "label": "Стоимость перевозки",
                            "help": (
                                f"Вложенные списки: строки идут по `{spec.row_set_symbol}`, "
                                f"столбцы — по `{spec.col_set_symbol}`."
                            ),
                            "type": "number",
                            "min": 0.0,
                            "example": [[4, 6], [5, 4]],
                        }
                    ],
                },
            },
        ],
        "display": {
            "summary": [
                {"id": "total_supply", "expr": f"sum{{o in {spec.row_set_symbol}}} supply[o]"},
                {"id": "total_demand", "expr": f"sum{{d in {spec.col_set_symbol}}} demand[d]"},
                {
                    "id": "total_shipped",
                    "expr": (
                        f"sum{{o in {spec.row_set_symbol}, d in {spec.col_set_symbol}}} ship[o, d]"
                    ),
                },
                {
                    "id": "total_cost",
                    "expr": (
                        f"sum{{o in {spec.row_set_symbol}, d in {spec.col_set_symbol}}} "
                        "cost[o, d] * ship[o, d]"
                    ),
                },
            ],
            "matrices": [
                {
                    "id": "shipment_plan",
                    "rows": f"o in {spec.row_set_symbol}",
                    "cols": f"d in {spec.col_set_symbol}",
                    "cell": "ship[o, d]",
                }
            ],
        },
        "presets": {"demo": "presets/demo.yaml"},
    }
    return _yaml_dump(payload)


def _render_transportation_model_orx(spec: ScaffoldSpec) -> str:
    return dedent(
        f"""\
        # Math-first transportation LP model generated by the student_math_v2 scaffold.
        # This file contains only the optimization model.

        set {spec.row_set_symbol};
        set {spec.col_set_symbol};

        param supply{{{spec.row_set_symbol}}};
        param demand{{{spec.col_set_symbol}}};
        param cost{{{spec.row_set_symbol}, {spec.col_set_symbol}}};

        var ship{{o in {spec.row_set_symbol}, d in {spec.col_set_symbol}}} >= 0;

        minimize total_cost:
            sum{{o in {spec.row_set_symbol}, d in {spec.col_set_symbol}}} cost[o, d] * ship[o, d];

        subject to supply_cap{{o in {spec.row_set_symbol}}}:
            sum{{d in {spec.col_set_symbol}}} ship[o, d] <= supply[o];

        subject to demand_fill{{d in {spec.col_set_symbol}}}:
            sum{{o in {spec.row_set_symbol}}} ship[o, d] = demand[d];
        """
    )


def _render_transportation_demo_preset(spec: ScaffoldSpec) -> str:
    payload = {
        "origins": {
            "origin_names": list(spec.example_rows),
            "supply": [20, 25],
        },
        "destinations": {
            "destination_names": list(spec.example_cols),
            "demand": [15, 30],
        },
        "costs": {
            "cost_matrix": [[4, 6], [5, 4]],
        },
    }
    return _yaml_dump(payload)


def _render_transportation_annotated_extension_yaml(spec: ScaffoldSpec) -> str:
    resource = spec.resource_label_ru
    return dedent(
        f"""\
        # Это учебная, подробно прокомментированная версия extension.yaml
        # для транспортной LP-задачи.

        format: student_math_v2

        extension:
          alias: {spec.alias}
          title: {spec.title}
          description: >-
            Учебное расширение для транспортной LP-задачи:
            как распределить "{resource}" из "{spec.row_entity_plural_ru}"
            в "{spec.col_entity_plural_ru}" с минимальной стоимостью.
          version: 0.1.0
          default_preset: demo
          labels:
            total_supply: Всего доступно ({spec.resource_label_with_unit})
            total_demand: Всего требуется ({spec.resource_label_with_unit})
            total_shipped: Всего перевезено ({spec.resource_label_with_unit})
            total_cost: Итоговая стоимость перевозки
            shipment_plan: План перевозки
            shipment_plan.row: {spec.row_entity_singular_ru.capitalize()}

        inputs:
          # Сначала студент задаёт множество пунктов отправления и их запасы.
          - id: origins
            label: {spec.row_entity_plural_ru.capitalize()}
            table:
              set: {spec.row_set_symbol}
              key:
                field: origin_names
                label: {spec.row_entity_plural_ru.capitalize()}
                help: >-
                  Перечислите {spec.row_entity_plural_ru.lower()} в том порядке,
                  в котором строки потом пойдут в матрице тарифов.
                example: {spec.example_rows[0]}
              columns:
                - param: supply
                  field: supply
                  label: Запас ({spec.resource_label_with_unit})
                  help: >-
                    Сколько ресурса "{resource}" доступно в каждом пункте отправления.
                  type: number
                  min: 0.0
                  example: 20

          # Потом задаются пункты назначения и их потребности.
          - id: destinations
            label: {spec.col_entity_plural_ru.capitalize()}
            table:
              set: {spec.col_set_symbol}
              key:
                field: destination_names
                label: {spec.col_entity_plural_ru.capitalize()}
                help: >-
                  Перечислите {spec.col_entity_plural_ru.lower()} в том порядке,
                  в котором столбцы потом пойдут в матрице тарифов.
                example: {spec.example_cols[0]}
              columns:
                - param: demand
                  field: demand
                  label: Потребность ({spec.resource_label_with_unit})
                  help: >-
                    Сколько ресурса "{resource}" нужно в каждом пункте назначения.
                  type: number
                  min: 0.0
                  example: 15

          # И только после этого студент задаёт матрицу тарифов.
          - id: costs
            label: Матрица тарифов
            matrix:
              rows_set: {spec.row_set_symbol}
              cols_set: {spec.col_set_symbol}
              fields:
                - param: cost
                  field: cost_matrix
                  label: Стоимость перевозки
                  help: >-
                    Вложенные списки: строки идут по `{spec.row_set_symbol}`,
                    столбцы — по `{spec.col_set_symbol}`.
                  type: number
                  min: 0.0
                  example:
                    - [4, 6]
                    - [5, 4]

        display:
          summary:
            - id: total_supply
              expr: sum{{o in {spec.row_set_symbol}}} supply[o]
            - id: total_demand
              expr: sum{{d in {spec.col_set_symbol}}} demand[d]
            - id: total_shipped
              expr: sum{{o in {spec.row_set_symbol}, d in {spec.col_set_symbol}}} ship[o, d]
            - id: total_cost
              expr: >-
                sum{{o in {spec.row_set_symbol}, d in {spec.col_set_symbol}}}
                cost[o, d] * ship[o, d]
          matrices:
            - id: shipment_plan
              rows: o in {spec.row_set_symbol}
              cols: d in {spec.col_set_symbol}
              cell: ship[o, d]

        presets:
          demo: presets/demo.yaml
        """
    )


def _render_transportation_annotated_model_orx(spec: ScaffoldSpec) -> str:
    resource = spec.resource_label_ru
    return dedent(
        f"""\
        # Это учебная, подробно прокомментированная версия model.orx
        # для транспортной LP-задачи.

        set {spec.row_set_symbol};
        set {spec.col_set_symbol};

        # supply[o] — сколько ресурса "{resource}" есть в пункте отправления o.
        param supply{{{spec.row_set_symbol}}};

        # demand[d] — сколько ресурса "{resource}" нужно в пункте назначения d.
        param demand{{{spec.col_set_symbol}}};

        # cost[o, d] — стоимость перевозки одной единицы из o в d.
        param cost{{{spec.row_set_symbol}, {spec.col_set_symbol}}};

        # ship[o, d] — сколько реально отправить из o в d.
        var ship{{o in {spec.row_set_symbol}, d in {spec.col_set_symbol}}} >= 0;

        # Цель: минимизировать суммарную стоимость перевозки.
        minimize total_cost:
            sum{{o in {spec.row_set_symbol}, d in {spec.col_set_symbol}}} cost[o, d] * ship[o, d];

        # Из каждого пункта нельзя отправить больше запаса.
        subject to supply_cap{{o in {spec.row_set_symbol}}}:
            sum{{d in {spec.col_set_symbol}}} ship[o, d] <= supply[o];

        # Каждый пункт назначения должен получить свой спрос полностью.
        subject to demand_fill{{d in {spec.col_set_symbol}}}:
            sum{{o in {spec.row_set_symbol}}} ship[o, d] = demand[d];
        """
    )


def _render_transportation_tutorial_readme(spec: ScaffoldSpec) -> str:
    return dedent(
        f"""\
        # {spec.title}: tutorial-версия для студентов

        ## Ментальная модель
        - `model.orx` отвечает за математическую постановку транспортной задачи.
        - `extension.yaml` отвечает за ввод множеств, векторов и матрицы тарифов.
        - Python студенту не нужен.

        ## Что вводит студент
        1. Список {spec.row_entity_plural_ru.lower()} и их запасы.
        2. Список {spec.col_entity_plural_ru.lower()} и их потребности.
        3. Матрицу тарифов между ними.

        ## Что считает модель
        - Есть два множества: `{spec.row_set_symbol}` и `{spec.col_set_symbol}`.
        - Есть 1-D параметры `supply` и `demand`.
        - Есть 2-D параметр `cost`.
        - Есть 2-D переменная решения `ship[o, d]`.
        - Цель модели: минимизировать стоимость перевозки.

        ## Что показывает приложение
        - Summary-значения по запасу, спросу, объёму и стоимости.
        - Матрицу `shipment_plan`, где видно, сколько отправлять по каждой паре.

        ## Как читать matrix-step
        Матрица в `inputs.matrix` всегда понимается так:
        - строки идут в порядке множества `{spec.row_set_symbol}`;
        - столбцы идут в порядке множества `{spec.col_set_symbol}`;
        - значение в ячейке `[i][j]` относится к паре (строка i, столбец j).

        ## Как проверять bundle
        ```bash
        make extension-check EXT={spec.alias}
        ```
        """
    )


def _yaml_dump(payload: object) -> str:
    return yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
        width=88,
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m agent_core.extension_scaffold",
        description="Generate one student_math_v2 declarative extension scaffold.",
    )
    parser.add_argument("alias", help="New extension alias, for example tasks_allocator")
    parser.add_argument("--title", required=True, help="User-facing extension title")
    parser.add_argument(
        "--template-family",
        choices=("allocation", "transportation"),
        default="allocation",
        help="Template family to generate: allocation or transportation.",
    )
    parser.add_argument("--entity-singular-ru", help="Russian singular name of one modeled object")
    parser.add_argument("--entity-plural-ru", help="Russian plural name of the modeled objects")
    parser.add_argument(
        "--resource-label-ru",
        required=True,
        help="Russian label for the allocated or transported resource",
    )
    parser.add_argument("--set-symbol", default="ITEMS", help="Optional ORX set symbol")
    parser.add_argument("--row-entity-singular-ru", help="Russian singular row-side object name")
    parser.add_argument("--row-entity-plural-ru", help="Russian plural row-side object name")
    parser.add_argument("--col-entity-singular-ru", help="Russian singular column-side object name")
    parser.add_argument("--col-entity-plural-ru", help="Russian plural column-side object name")
    parser.add_argument("--row-set-symbol", default="ORIGINS", help="ORX row-set symbol")
    parser.add_argument("--col-set-symbol", default="DESTINATIONS", help="ORX col-set symbol")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        spec = build_scaffold_spec(
            alias=args.alias,
            title=args.title,
            resource_label_ru=args.resource_label_ru,
            template_family=args.template_family,
            entity_singular_ru=args.entity_singular_ru,
            entity_plural_ru=args.entity_plural_ru,
            set_symbol=args.set_symbol,
            row_entity_singular_ru=args.row_entity_singular_ru,
            row_entity_plural_ru=args.row_entity_plural_ru,
            col_entity_singular_ru=args.col_entity_singular_ru,
            col_entity_plural_ru=args.col_entity_plural_ru,
            row_set_symbol=args.row_set_symbol,
            col_set_symbol=args.col_set_symbol,
        )
        result = scaffold_bundle(workspace_root=Path.cwd(), spec=spec)
    except Exception as exc:
        print(f"extension-scaffold failed: {exc}")
        return 1

    print(
        f"extension-scaffold ok: `{spec.alias}` "
        f"({spec.template_family}) created at {result.bundle_root}"
    )
    print("Created files:")
    for relative_path in result.written_files:
        print(f"- {relative_path}")
    print("Next:")
    print(f"  make extension-check EXT={spec.alias}")
    print("  make dev")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
