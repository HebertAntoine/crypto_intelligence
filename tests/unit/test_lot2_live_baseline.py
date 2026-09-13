from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_single_server_deployment_enables_the_live_scheduler() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert 'SCHEDULER_ENABLED: "true"' in compose


def test_initial_analysis_runs_after_live_input_refreshes() -> None:
    from crypto_intel import scheduler

    source = Path(scheduler.__file__).read_text(encoding="utf-8")
    offset_block = source.split("offset = {", 1)[1].split("}[job_id]", 1)[0]

    def offset(job: str) -> int:
        marker = f'"{job}": '
        return int(offset_block.split(marker, 1)[1].split(",", 1)[0])

    assert offset("ohlcv_sync") < offset("analysis")
    assert offset("derivatives_sync") < offset("analysis")
    assert offset("market") < offset("analysis")
