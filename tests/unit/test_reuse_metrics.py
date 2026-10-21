from test_runtime_control import SPEC, context, gateway

from career_agent.models.control.recovery_contracts import JournalData
from career_agent.ops.query import cache_telemetry
from career_agent.runtime.contracts import Usage


async def test_cache_telemetry_uses_reported_usage_and_unknown_denominators():
    g = gateway()
    request = await g.prepare(context(), SPEC.task({}))
    selection = request.selection.model_dump(mode="json", exclude={"deadline"})
    facts = [
        JournalData(selection=selection, financial_reservation=Usage(), usage=u, latency_ms=ms)
        for u, ms in [
            (
                Usage(
                    input_tokens=100,
                    cached_tokens=50,
                    cache_write_tokens=None,
                    measurement="reported",
                ),
                20,
            ),
            (
                Usage(
                    input_tokens=100, cached_tokens=0, cache_write_tokens=10, measurement="reported"
                ),
                40,
            ),
            (
                Usage(
                    input_tokens=100,
                    cached_tokens=100,
                    cache_write_tokens=100,
                    measurement="estimated",
                ),
                10,
            ),
            (None, None),
        ]
    ]
    result = cache_telemetry(facts)
    assert result["cached_tokens"] == {
        "known_sum": 50,
        "reported_attempts": 2,
        "unknown_attempts": 2,
    }
    assert result["cache_write_tokens"] == {
        "known_sum": 10,
        "reported_attempts": 1,
        "unknown_attempts": 3,
    }
    assert result["token_cache_hit_rate"] == 0.25
    assert result["cache_hit_call_rate"] == 0.5
    assert result["hit"]["latency_p50_ms"] == 20
    assert result["miss"]["latency_p50_ms"] == 40
    assert result["actual_billed_savings_usd"] is None
    assert cache_telemetry([])["cached_tokens"]["known_sum"] is None
    assert cache_telemetry([facts[-1]])["token_cache_hit_rate"] is None
    g.cancel_prepared(request)
