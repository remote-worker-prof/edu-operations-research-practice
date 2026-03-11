from or_core.pipeline import ORPipeline


def test_or_subgraph_sequence(runtime_input) -> None:
    pipeline = ORPipeline()
    result = pipeline.run(runtime_input)

    assert result.execution_trace == [
        "optimize_production",
        "allocate_shipments",
        "assign_resources",
        "build_routes",
        "finalize_report",
    ]
    assert result.final_report
