"""tests/test_claude_models_deprecation.py — claude_models.py DEPRECATED_MODELS

Covers the v1.37.0 addition: a way to represent "announced retirement,
still callable today" separately from RETIRED_MODELS ("already 404s").
claude_models.py had no dedicated test file before this cycle; scope here
is limited to the new deprecation-tracking surface, not a full backfill
of pre-existing untested functions (validate_fast_mode, cmd_upgrade_all,
etc.) — see docs/49_upgrade_v1.37.0_deferred_items.md for that note.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from claude_models import (
    DEPRECATED_MODELS,
    RETIRED_MODELS,
    _upgrade_source_ids,
    check_deprecated,
    check_retired,
    cmd_check_deprecated,
    cmd_model_info,
)


def test_check_retired_opus_4_1():
    rec = check_retired("claude-opus-4-1-20250805")
    assert rec is not None
    assert rec["retired"] == "2026-08-05"
    assert rec["replacement"] == "claude-opus-4-8"


def test_check_deprecated_unknown_id_returns_none():
    assert check_deprecated("claude-sonnet-5") is None


def test_deprecated_and_retired_are_disjoint():
    # A model shouldn't be in both dicts at once -- it's either still
    # callable-with-a-warning (deprecated) or already dead (retired).
    assert set(DEPRECATED_MODELS.keys()).isdisjoint(set(RETIRED_MODELS.keys()))


def test_cmd_model_info_warns_on_retired_id(capsys, monkeypatch):
    class _FakeModelsAPI:
        def __init__(self, api_key=None):
            pass

        def get_model(self, model_id):
            return {
                "id": model_id,
                "display_name": "x",
                "context_window": 0,
                "created_at": "2025-08-05T00:00:00Z",
            }

    monkeypatch.setattr("claude_models.ModelsAPI", _FakeModelsAPI)
    cmd_model_info("claude-opus-4-1-20250805", api_key="k")
    out = capsys.readouterr().out
    assert "retired" in out.lower()
    assert "2026-08-05" in out
    assert "claude-opus-4-8" in out


def test_cmd_check_deprecated_reports_retired_hit(capsys, tmp_path):
    f = tmp_path / "config.py"
    f.write_text('MODEL = "claude-opus-4-1-20250805"\n')
    cmd_check_deprecated(str(tmp_path))
    out = capsys.readouterr().out
    assert "claude-opus-4-1-20250805" in out
    assert "retired" in out.lower()


def test_cmd_check_deprecated_clean_tree(capsys, tmp_path):
    f = tmp_path / "config.py"
    f.write_text('MODEL = "claude-opus-4-8"\n')
    cmd_check_deprecated(str(tmp_path))
    out = capsys.readouterr().out
    assert "No retired or deprecated model IDs found" in out


def test_upgrade_source_ids_includes_retired():
    ids = _upgrade_source_ids("claude-fable-5")
    assert "claude-opus-4-1-20250805" in ids


def test_upgrade_source_ids_excludes_target():
    ids = _upgrade_source_ids("claude-opus-4-1-20250805")
    assert "claude-opus-4-1-20250805" not in ids
