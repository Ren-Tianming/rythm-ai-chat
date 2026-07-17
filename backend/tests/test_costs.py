from app.services.llm.registry import estimate_cost_microusd


def test_estimated_deepseek_cost() -> None:
    assert estimate_cost_microusd("deepseek", "deepseek-v4-flash", 3000, 500) == 560


def test_unknown_model_has_no_estimate() -> None:
    assert estimate_cost_microusd("unknown", "unknown", 1000, 1000) == 0
