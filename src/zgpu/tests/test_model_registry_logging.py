from zgpu.llm.model_registry import _safe_log_value


def test_model_registry_log_values_strip_control_characters_and_bound_length():
    assert _safe_log_value("model\r\nforged-entry") == "model?forged-entry"
    assert _safe_log_value("model\nforged-entry") == "model?forged-entry"
    assert _safe_log_value("model\rforged-entry") == "model?forged-entry"
    assert len(_safe_log_value("x" * 500)) == 128


def test_model_registry_log_values_never_contain_line_breaks():
    for probe in ("forged\r\nentry", "forged\nentry", "forged\rEntry", "\n\r\n"):
        sanitized = _safe_log_value(probe)
        assert "\r" not in sanitized
        assert "\n" not in sanitized
