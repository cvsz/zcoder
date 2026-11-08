from zgpu.llm.model_registry import _safe_log_value


def test_model_registry_log_values_strip_control_characters_and_bound_length():
    assert _safe_log_value("model\r\nforged-entry") == "model??forged-entry"
    assert len(_safe_log_value("x" * 500)) == 128
