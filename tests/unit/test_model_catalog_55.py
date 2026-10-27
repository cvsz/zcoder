"""Regression coverage for the v1.60.0 model catalog metadata."""

from zcoder.agent.models.registry import MODEL_CATALOG, UPGRADE_TARGETS, cmd_upgrade_all


def test_55_generation_models_have_documented_catalog_metadata():
    expected = {
        "claude-fable-5-1": (10.0, 50.0, "high"),
        "claude-opus-5-5": (4.0, 20.0, "medium"),
        "claude-sonnet-5-5": (2.0, 10.0, "high"),
        "claude-haiku-5-5": (0.1, 0.5, "medium"),
    }

    for model_id, (price_in, price_out, effort) in expected.items():
        model = MODEL_CATALOG[model_id]
        assert model["tier"] == "current"
        assert model["context_window"] == 1_000_000
        assert model["max_output"] == 128_000
        assert (model["price_in"], model["price_out"]) == (price_in, price_out)
        assert model["effort_default"] == effort
        assert "does not enable network inference" in model["notes"]


def test_haiku_55_catalog_preserves_variable_pricing_tiers():
    tiers = MODEL_CATALOG["claude-haiku-5-5"]["pricing_tiers"]
    assert tiers == [
        {"max_input_tokens": 100_000, "price_in": 0.1, "price_out": 0.5},
        {"min_input_tokens": 100_001, "price_in": 0.5, "price_out": 2.5},
    ]


def test_superseded_models_remain_catalogued_as_legacy():
    for model_id in (
        "claude-fable-5",
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-opus-4-8",
        "claude-haiku-4-5-20251001",
    ):
        assert MODEL_CATALOG[model_id]["tier"] == "legacy"


def test_55_generation_models_are_available_as_upgrade_targets():
    assert {name: UPGRADE_TARGETS[name] for name in ("fable51", "opus55", "sonnet55", "haiku55")} == {
        "fable51": "claude-fable-5-1",
        "opus55": "claude-opus-5-5",
        "sonnet55": "claude-sonnet-5-5",
        "haiku55": "claude-haiku-5-5",
    }


def test_upgrade_all_can_preview_a_55_generation_target(capsys, tmp_path):
    config = tmp_path / "models.toml"
    config.write_text('model = "claude-sonnet-5-5"\n')

    cmd_upgrade_all(str(config), target="opus55")

    assert config.read_text() == 'model = "claude-sonnet-5-5"\n'
    output = capsys.readouterr().out
    assert "Would upgrade" in output
    assert "claude-opus-5-5" in output
