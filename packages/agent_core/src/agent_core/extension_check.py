"""CLI validation entrypoint for declarative extensions."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

from agent_core.declarative_extensions import (
    DeclarativeBundle,
    DeclarativeBundleError,
    load_declarative_bundle,
    load_declarative_provider,
)


@dataclass(frozen=True, slots=True)
class BundleValidationReport:
    manifest_alias: str
    validated_presets: int
    tutorial_validated: int
    bundle_root: Path


def _bundle_root_from_arg(raw: str) -> Path:
    candidate = Path(raw)
    if candidate.exists():
        return candidate
    return Path.cwd() / "extensions" / raw


def _validate_provider_presets(provider) -> tuple[int, dict[str, object], dict[str, object]]:
    manifest = provider.get_manifest()
    runtime = provider.create_runtime()
    validated_presets = 0
    preset_results: dict[str, object] = {}
    preset_sections: dict[str, object] = {}
    for preset_ref in sorted(provider._bundle.config.presets):
        preset = provider.load_preset(preset_ref)
        errors = runtime.validate_draft(preset)
        if any(messages for messages in errors.values()):
            raise DeclarativeBundleError(
                f"Preset `{preset_ref}` is invalid for `{manifest.alias}`: {errors}"
            )
        runtime_input = runtime.build_runtime_input(preset)
        result = runtime.run(runtime_input)
        preset_results[preset_ref] = result
        preset_sections[preset_ref] = [
            section.model_dump(mode="json") for section in runtime.build_result_sections(result)
        ]
        validated_presets += 1
    return validated_presets, preset_results, preset_sections


def _normalize_bundle(bundle: DeclarativeBundle) -> dict[str, object]:
    return {
        "manifest": bundle.manifest.model_dump(mode="json"),
        "config": bundle.config.model_dump(mode="json"),
        "model": asdict(bundle.model),
    }


def _validate_tutorial_bundle(
    *,
    bundle_root: Path,
    compact_bundle: DeclarativeBundle,
    compact_results: dict[str, object],
    compact_sections: dict[str, object],
) -> int:
    dsl_format = compact_bundle.manifest.ui_metadata.get("dsl_format")
    tutorial_dir = bundle_root / "tutorial"
    tutorial_config = "tutorial/extension.annotated.yaml"
    tutorial_model = "tutorial/model.annotated.orx"
    tutorial_readme = tutorial_dir / "README.ru.md"

    if dsl_format != "student_v1":
        return 0

    missing = [
        path
        for path in (
            bundle_root / tutorial_config,
            bundle_root / tutorial_model,
            tutorial_readme,
        )
        if not path.exists()
    ]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        raise DeclarativeBundleError(
            f"student_v1 bundle `{bundle_root}` должен содержать tutorial-файлы: {joined}"
        )

    tutorial_bundle = load_declarative_bundle(
        bundle_root,
        config_filename=tutorial_config,
        model_filename=tutorial_model,
    )
    if _normalize_bundle(compact_bundle) != _normalize_bundle(tutorial_bundle):
        raise DeclarativeBundleError(
            "annotated tutorial-файлы должны быть семантически эквивалентны compact runtime-файлам"
        )

    tutorial_provider = load_declarative_provider(
        bundle_root,
        config_filename=tutorial_config,
        model_filename=tutorial_model,
    )
    _, tutorial_results, tutorial_sections = _validate_provider_presets(tutorial_provider)
    if compact_results != tutorial_results:
        raise DeclarativeBundleError(
            "Результаты tutorial bundle отличаются от compact bundle "
            "на одних и тех же preset-данных"
        )
    if compact_sections != tutorial_sections:
        raise DeclarativeBundleError("Result sections tutorial bundle отличаются от compact bundle")
    return 1


def validate_bundle(bundle_root: Path) -> BundleValidationReport:
    provider = load_declarative_provider(bundle_root)
    manifest = provider.get_manifest()
    validated_presets, compact_results, compact_sections = _validate_provider_presets(provider)
    tutorial_validated = _validate_tutorial_bundle(
        bundle_root=bundle_root,
        compact_bundle=provider._bundle,
        compact_results=compact_results,
        compact_sections=compact_sections,
    )
    return BundleValidationReport(
        manifest_alias=manifest.alias,
        validated_presets=validated_presets,
        tutorial_validated=tutorial_validated,
        bundle_root=bundle_root,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agent_core.extension_check",
        description="Validate one declarative extension bundle and all of its presets.",
    )
    parser.add_argument("extension", help="Extension alias or explicit bundle path")
    args = parser.parse_args()

    bundle_root = _bundle_root_from_arg(args.extension).resolve()
    try:
        report = validate_bundle(bundle_root)
    except Exception as exc:
        print(f"extension-check failed for `{bundle_root}`: {exc}")
        return 1

    print(
        f"extension-check ok: `{report.manifest_alias}` "
        f"({report.validated_presets} preset(s) validated, "
        f"tutorial parity: {report.tutorial_validated}, bundle root: {report.bundle_root})"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
