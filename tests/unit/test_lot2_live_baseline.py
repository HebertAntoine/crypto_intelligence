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


def test_macro_cycle_uses_the_documented_three_hour_utc_clock() -> None:
    from crypto_intel import scheduler
    from crypto_intel.engines.macro_drivers import CYCLE_HOURS

    source = Path(scheduler.__file__).read_text(encoding="utf-8")

    assert 'CronTrigger(hour=",".join(str(h) for h in CYCLE_HOURS), minute=0' in source
    assert tuple(CYCLE_HOURS) == tuple(range(0, 24, 3))
