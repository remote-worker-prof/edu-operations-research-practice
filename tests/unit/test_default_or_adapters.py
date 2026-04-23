"""Focused unit coverage for `default_or` compatibility adapters."""

from __future__ import annotations

from agent_core.default_or_adapters import DefaultOrStateSyncAdapter
from or_core.models import ScenarioDraft


def test_default_or_state_sync_adapter_roundtrips_between_legacy_and_generic_drafts() -> None:
    """Compatibility adapter should preserve the four-stage legacy draft structure."""
    scenario_draft = ScenarioDraft(
        production={"products": ["A", "B"], "profits": [40, 30]},
        shipment={"warehouses": ["W1"], "clients": ["C1"]},
        assignment={"resources": ["R1"]},
        routing={"depot_index": 0},
        preset_ref="demo",
    )

    generic = DefaultOrStateSyncAdapter.to_extension_draft(scenario_draft)
    restored = DefaultOrStateSyncAdapter.to_scenario_draft(generic)

    assert generic["production"]["products"] == ["A", "B"]
    assert restored.production["profits"] == [40, 30]
    assert restored.shipment["warehouses"] == ["W1"]
    assert restored.assignment["resources"] == ["R1"]
    assert restored.routing["depot_index"] == 0
