"""CLI scaffold generator for student_v1 declarative extension bundles."""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

import yaml

from agent_core.extension_check import BundleValidationReport, validate_bundle

_ALIAS_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_SYMBOL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class ScaffoldSpec:
    alias: str
    title: str
    entity_singular_ru: str
    entity_plural_ru: str
    resource_label_ru: str
    set_symbol: str = "ITEMS"

    @property
    def description(self) -> str:
        return (
            f"Учебное расширение для распределения ограниченного ресурса "
            f'"{self.resource_label_ru}" '
            f'между объектами типа "{self.entity_plural_ru}".'
        )

    @property
    def example_items(self) -> tuple[str, str, str]:
        return tuple(f"{self.entity_singular_ru} {index}" for index in range(1, 4))

    @property
    def resource_label_with_unit(self) -> str:
        return f"{self.resource_label_ru}"


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
    entity_singular_ru: str,
    entity_plural_ru: str,
    resource_label_ru: str,
    set_symbol: str = "ITEMS",
) -> ScaffoldSpec:
    normalized_alias = alias.strip()
    normalized_title = title.strip()
    normalized_singular = entity_singular_ru.strip()
    normalized_plural = entity_plural_ru.strip()
    normalized_resource = resource_label_ru.strip()
    normalized_set_symbol = set_symbol.strip()

    if not _ALIAS_RE.fullmatch(normalized_alias):
        raise ScaffoldError(
            "Alias должен соответствовать шаблону ^[a-z][a-z0-9_-]*$ для стабильного bundle name."
        )
    if not normalized_title:
        raise ScaffoldError("Параметр --title не должен быть пустым.")
    if not normalized_singular:
        raise ScaffoldError("Параметр --entity-singular-ru не должен быть пустым.")
    if not normalized_plural:
        raise ScaffoldError("Параметр --entity-plural-ru не должен быть пустым.")
    if not normalized_resource:
        raise ScaffoldError("Параметр --resource-label-ru не должен быть пустым.")
    if not _SYMBOL_RE.fullmatch(normalized_set_symbol):
        raise ScaffoldError(
            "SET_SYMBOL должен быть корректным ORX-идентификатором, например ITEMS или TOPICS."
        )
    return ScaffoldSpec(
        alias=normalized_alias,
        title=normalized_title,
        entity_singular_ru=normalized_singular,
        entity_plural_ru=normalized_plural,
        resource_label_ru=normalized_resource,
        set_symbol=normalized_set_symbol,
    )


def render_bundle_files(spec: ScaffoldSpec) -> RenderedBundle:
    files = {
        "extension.yaml": _render_extension_yaml(spec),
        "model.orx": _render_model_orx(spec),
        "presets/demo.yaml": _render_demo_preset(spec),
        "tutorial/extension.annotated.yaml": _render_annotated_extension_yaml(spec),
        "tutorial/model.annotated.orx": _render_annotated_model_orx(spec),
        "tutorial/README.ru.md": _render_tutorial_readme(spec),
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


def _render_extension_yaml(spec: ScaffoldSpec) -> str:
    payload = {
        "format": "student_v1",
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
        "wizard": [
            {
                "id": "items",
                "label": spec.entity_plural_ru,
                "table": {
                    "id": "item_rows",
                    "set": spec.set_symbol,
                    "key": {
                        "id": "item_names",
                        "label": spec.entity_plural_ru,
                        "help": (
                            f"Перечислите {spec.entity_plural_ru.lower()} в том порядке, "
                            "в котором будете задавать остальные списки."
                        ),
                        "example": spec.example_items[0],
                    },
                    "columns": [
                        {
                            "id": "required_units",
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
                "fields": [
                    {
                        "id": "available_units",
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
                "fields": [
                    {
                        "id": "priority",
                        "label": f"Веса приоритетов для {spec.entity_plural_ru}",
                        "help": (
                            f"Чем выше число, тем полезнее дополнительная единица ресурса "
                            f'"{spec.resource_label_ru}" для данного объекта.'
                        ),
                        "type": "list[number]",
                        "min": 0.0001,
                        "example": [0.5, 0.3, 0.2],
                    }
                ],
            },
        ],
        "results": {
            "show": [
                "total_available_units",
                "total_required_units",
                "total_allocated_units",
                "remaining_units",
                "achieved_weighted_score",
                "allocation_plan",
            ]
        },
        "presets": {"demo": "presets/demo.yaml"},
        "text": {
            "fallback_explain_template": (
                "Модель распределила {total_allocated_units} из {total_available_units} "
                f'единиц ресурса "{spec.resource_label_ru}". '
                "Смотрите таблицу распределения, чтобы понять, где ресурс покрывает "
                "потребность полностью, а где остается дефицит."
            ),
            "llm_explain_prompt_template": (
                f"Объясни студенту по исследованию операций результат allocation-модели "
                f'для объектов типа "{spec.entity_plural_ru}" и ресурса '
                f'"{spec.resource_label_ru}". Result payload: {{result}}'
            ),
        },
    }
    return _yaml_dump(payload)


def _render_model_orx(spec: ScaffoldSpec) -> str:
    return dedent(
        f"""\
        # Compact allocation-style LP model generated by the student_v1 scaffold.

        set {spec.set_symbol}

        param available_units
        param required_units[{spec.set_symbol}]
        param priority[{spec.set_symbol}]

        var allocated_units[{spec.set_symbol}] in 0..required_units[{spec.set_symbol}]

        maximize allocation_score:
            sum(i in {spec.set_symbol}, priority[i] * allocated_units[i])

        st total_budget:
            sum(i in {spec.set_symbol}, allocated_units[i]) <= available_units

        report total_available_units = available_units
        report total_required_units = sum(i in {spec.set_symbol}, required_units[i])
        report total_allocated_units = sum(i in {spec.set_symbol}, allocated_units[i])
        report remaining_units = available_units - sum(i in {spec.set_symbol}, allocated_units[i])
        report achieved_weighted_score =
            sum(i in {spec.set_symbol}, priority[i] * allocated_units[i])

        report allocation_plan by i in {spec.set_symbol}:
            item = i
            required_units = required_units[i]
            allocated_units = allocated_units[i]
            gap_units = required_units[i] - allocated_units[i]
            priority = priority[i]
            coverage_ratio = allocated_units[i] / required_units[i]
            coverage_ratio_pct = 100 * allocated_units[i] / required_units[i]
        """
    )


def _render_demo_preset(spec: ScaffoldSpec) -> str:
    payload = {
        "items": {
            "item_names": list(spec.example_items),
            "required_units": [30, 24, 18],
        },
        "budget": {"available_units": 48},
        "priorities": {"priority": [0.5, 0.3, 0.2]},
    }
    return _yaml_dump(payload)


def _render_annotated_extension_yaml(spec: ScaffoldSpec) -> str:
    items_label = spec.entity_plural_ru
    resource = spec.resource_label_ru
    return dedent(
        f"""\
        # Это учебная, подробно прокомментированная версия файла extension.yaml.
        # Она исполняемая: валидатор должен уметь загрузить ее так же, как и обычный файл.
        # Разница только в том, что здесь мы объясняем почти каждую строку простым русским языком.

        format: student_v1

        extension:
          # alias — это короткое техническое имя расширения.
          # Его видит система, когда ищет extension по папке.
          alias: {spec.alias}

          # title — человеко-понятное название, которое увидит студент в интерфейсе.
          title: {spec.title}

          # description — короткое описание смысла модели.
          description: >-
            Учебное расширение для распределения ограниченного ресурса "{resource}"
            между объектами типа "{items_label}".

          # version — просто версия bundle.
          version: 0.1.0

          # default_preset — какой готовый пример подгружать по команде `load preset demo`.
          default_preset: demo

          # labels — подписи для итоговых report-значений и колонок таблиц.
          # Слева — техническое имя отчета из model.orx, справа — то, что увидит студент.
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

        # wizard — это сценарий ввода данных.
        # Здесь мы говорим движку: какие шаги проходит студент и какие данные вводит на каждом шаге.
        wizard:
          # Шаг 1. Вводим список объектов и сколько ресурса нужно на каждый объект.
          - id: items
            label: {items_label}
            table:
              # id — внутреннее имя таблицы. Пока оно нужно только как метка внутри DSL.
              id: item_rows

              # set — множество объектов в математической модели.
              set: {spec.set_symbol}

              key:
                # key.id — имя поля, в котором лежат элементы множества.
                id: item_names
                label: {items_label}
                help: >-
                  Перечислите {items_label.lower()} в том порядке,
                  в котором будете задавать остальные списки.
                example: {spec.example_items[0]}

              columns:
                # required_units автоматически привяжется к
                # param required_units[{spec.set_symbol}] в model.orx.
                - id: required_units
                  label: Требуемый объём ({spec.resource_label_with_unit})
                  help: >-
                    Сколько ресурса "{resource}" нужно,
                    чтобы полностью закрыть каждый объект.
                  type: number
                  min: 0.0001
                  example: 30

          # Шаг 2. Сколько ресурса вообще можно распределить.
          - id: budget
            label: Бюджет ресурса
            fields:
              - id: available_units
                label: Доступный объём ({spec.resource_label_with_unit})
                help: >-
                  Сколько ресурса "{resource}" есть всего
                  для распределения.
                type: number
                min: 0.0001
                example: 48

          # Шаг 3. Насколько важен каждый объект.
          - id: priorities
            label: Приоритеты
            fields:
              - id: priority
                label: Веса приоритетов для {items_label}
                help: >-
                  Чем выше число, тем полезнее дополнительная
                  единица ресурса "{resource}" для данного объекта.
                type: list[number]
                min: 0.0001
                example:
                  - 0.5
                  - 0.3
                  - 0.2

        # results.show — просто порядок показа report-ов из model.orx.
        # Никакой дополнительной верстки студенту описывать не нужно.
        results:
          show:
            - total_available_units
            - total_required_units
            - total_allocated_units
            - remaining_units
            - achieved_weighted_score
            - allocation_plan

        # presets — готовые демонстрационные входные данные.
        presets:
          demo: presets/demo.yaml

        # text — шаблоны пояснений, которые показывает система после решения.
        text:
          fallback_explain_template: >-
            Модель распределила {{total_allocated_units}} из {{total_available_units}}
            единиц ресурса "{resource}". Смотрите таблицу распределения, чтобы понять,
            где ресурс покрывает потребность полностью, а где остается дефицит.
          llm_explain_prompt_template: >-
            Объясни студенту по исследованию операций результат allocation-модели
            для объектов типа "{items_label}" и ресурса "{resource}".
            Result payload: {{result}}
        """
    )


def _render_annotated_model_orx(spec: ScaffoldSpec) -> str:
    set_symbol = spec.set_symbol
    resource = spec.resource_label_ru
    return dedent(
        f"""\
        # Это учебная, подробно прокомментированная версия model.orx.
        # Здесь мы показываем модель почти построчно и объясняем, что означает каждая конструкция.

        # 1) Объявляем множество {set_symbol}.
        # В нем будут лежать названия объектов, между которыми распределяется ресурс.
        set {set_symbol}

        # 2) Объявляем входные параметры.
        # available_units — общий доступный объём ресурса "{resource}".
        param available_units

        # required_units[{set_symbol}] — сколько ресурса нужно для полного покрытия каждого объекта.
        param required_units[{set_symbol}]

        # priority[{set_symbol}] — вес важности каждого объекта.
        param priority[{set_symbol}]

        # 3) Объявляем переменную решения.
        # allocated_units[{set_symbol}] — сколько ресурса реально выделить каждому объекту.
        # Запись `in 0..required_units[{set_symbol}]` означает, что выделить можно
        # не меньше 0 и не больше полной потребности объекта.
        var allocated_units[{set_symbol}] in 0..required_units[{set_symbol}]

        # 4) Целевая функция.
        # Мы хотим максимизировать суммарную полезность распределения.
        maximize allocation_score:
            sum(i in {set_symbol}, priority[i] * allocated_units[i])

        # 5) Ограничение по общему бюджету ресурса.
        st total_budget:
            sum(i in {set_symbol}, allocated_units[i]) <= available_units

        # 6) Скалярные отчеты для красивого вывода в интерфейсе.
        report total_available_units = available_units
        report total_required_units = sum(i in {set_symbol}, required_units[i])
        report total_allocated_units = sum(i in {set_symbol}, allocated_units[i])
        report remaining_units = available_units - sum(i in {set_symbol}, allocated_units[i])
        report achieved_weighted_score = sum(i in {set_symbol}, priority[i] * allocated_units[i])

        # 7) Табличный отчет.
        # Он показывает решение по каждому объекту отдельно.
        report allocation_plan by i in {set_symbol}:
            item = i
            required_units = required_units[i]
            allocated_units = allocated_units[i]
            gap_units = required_units[i] - allocated_units[i]
            priority = priority[i]
            coverage_ratio = allocated_units[i] / required_units[i]
            coverage_ratio_pct = 100 * allocated_units[i] / required_units[i]
        """
    )


def _render_tutorial_readme(spec: ScaffoldSpec) -> str:
    return dedent(
        f"""\
        # {spec.title}: tutorial-версия для студентов

        ## Ментальная модель
        - `extension.yaml` отвечает за то,
          **что вводит пользователь** и **что показывает приложение**.
        - `model.orx` отвечает за то, **что именно считает математическая модель**.
        - Python студенту не нужен:
          движок уже умеет читать DSL, собирать LP и решать задачу.

        ## Что вводит студент
        1. На шаге `items` вводится список объектов типа "{spec.entity_plural_ru}".
        2. На том же шаге задается,
           сколько ресурса "{spec.resource_label_ru}" нужно на каждый объект.
        3. На шаге `budget` вводится общий запас ресурса.
        4. На шаге `priorities` вводятся веса важности объектов.

        ## Что считает модель
        - Есть множество объектов `{spec.set_symbol}`.
        - Есть известные заранее параметры:
          доступный ресурс, потребность и веса приоритетов.
        - Есть переменная решения `allocated_units`,
          которая показывает, сколько ресурса реально выделить.
        - Цель модели: распределить ресурс так, чтобы суммарная полезность была максимальной.
        - Ограничение модели: нельзя распределить больше ресурса, чем доступно.

        ## Что показывает приложение
        - Несколько числовых итогов:
          сколько ресурса доступно, сколько распределили и сколько осталось.
        - Таблицу `allocation_plan`, где по каждому объекту видно:
          - сколько ресурса было нужно;
          - сколько ресурса реально выделили;
          - какой дефицит остался;
          - какой процент потребности удалось покрыть.

        ## Как адаптировать этот пример под свой класс задач
        1. Сначала отредактируйте рабочие файлы `extension.yaml` и `model.orx`.
        2. Затем обновите файлы из папки `tutorial/`,
           чтобы комментарии и объяснения соответствовали рабочей версии.
        3. При необходимости переименуйте `{spec.set_symbol}`
           и математические символы в `model.orx`.
        4. Сохраните общий принцип:
           - YAML описывает ввод и вывод.
           - ORX описывает математику.
        5. Проверьте bundle командой:

        ```bash
        make extension-check EXT={spec.alias}
        ```

        ## На что смотреть в первую очередь
        - Если вы не понимаете `extension.yaml`,
          начинайте сверху вниз и читайте комментарии над каждым блоком.
        - Если вы не понимаете `model.orx`,
          читайте его в порядке:
          `set` -> `param` -> `var` -> `maximize` -> `st` -> `report`.
        - Если кажется, что DSL сложный, смотрите на него как на три вопроса:
          - что у меня является объектами задачи;
          - какие числа я знаю заранее;
          - какие числа нужно подобрать оптимально.
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
        description="Generate one student_v1 declarative extension scaffold.",
    )
    parser.add_argument("alias", help="New extension alias, for example tasks_allocator")
    parser.add_argument("--title", required=True, help="User-facing extension title")
    parser.add_argument(
        "--entity-singular-ru",
        required=True,
        help="Russian singular name of one modeled object",
    )
    parser.add_argument(
        "--entity-plural-ru",
        required=True,
        help="Russian plural name of the modeled objects",
    )
    parser.add_argument(
        "--resource-label-ru",
        required=True,
        help="Russian label for the resource being allocated",
    )
    parser.add_argument(
        "--set-symbol",
        default="ITEMS",
        help="Optional ORX set symbol, default: ITEMS",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        spec = build_scaffold_spec(
            alias=args.alias,
            title=args.title,
            entity_singular_ru=args.entity_singular_ru,
            entity_plural_ru=args.entity_plural_ru,
            resource_label_ru=args.resource_label_ru,
            set_symbol=args.set_symbol,
        )
        result = scaffold_bundle(workspace_root=Path.cwd(), spec=spec)
    except Exception as exc:
        print(f"extension-scaffold failed: {exc}")
        return 1

    print(f"extension-scaffold ok: `{spec.alias}` created at {result.bundle_root}")
    print("Created files:")
    for relative_path in result.written_files:
        print(f"- {relative_path}")
    print("Next:")
    print(f"  make extension-check EXT={spec.alias}")
    print("  make dev")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
