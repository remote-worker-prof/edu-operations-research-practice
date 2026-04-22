"""CLI validation entrypoint for declarative extensions."""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_core.declarative_extensions import DeclarativeBundleError, load_declarative_provider


def _bundle_root_from_arg(raw: str) -> Path:
    candidate = Path(raw)
    if candidate.exists():
        return candidate
    return Path.cwd() / "extensions" / raw


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agent_core.extension_check",
        description="Validate one declarative extension bundle and all of its presets.",
    )
    parser.add_argument("extension", help="Extension alias or explicit bundle path")
    args = parser.parse_args()

    bundle_root = _bundle_root_from_arg(args.extension).resolve()
    try:
        provider = load_declarative_provider(bundle_root)
        manifest = provider.get_manifest()
        runtime = provider.create_runtime()
        validated_presets = 0
        for preset_ref in sorted(provider._bundle.config.presets):
            preset = provider.load_preset(preset_ref)
            errors = runtime.validate_draft(preset)
            if any(messages for messages in errors.values()):
                raise DeclarativeBundleError(
                    f"Preset `{preset_ref}` is invalid for `{manifest.alias}`: {errors}"
                )
            runtime_input = runtime.build_runtime_input(preset)
            runtime.run(runtime_input)
            validated_presets += 1
    except Exception as exc:
        print(f"extension-check failed for `{bundle_root}`: {exc}")
        return 1

    print(
        f"extension-check ok: `{manifest.alias}` ({validated_presets} preset(s) validated, "
        f"bundle root: {bundle_root})"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
