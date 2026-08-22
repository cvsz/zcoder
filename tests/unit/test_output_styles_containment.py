"""Regression tests for SEC-007.1 — output-style file containment.

Custom/plugin output styles are model-bound prompt content; loading must use
the same safe_resolve containment + size cap as skills/commands/agents.
"""

from __future__ import annotations

import os
from pathlib import Path

from zcoder.claude.eval import output_styles


def _style(path: Path, name: str = "terse") -> None:
    path.write_text(
        f"---\nname: {name}\ndescription: d\n---\nSTYLE BODY\n",
    )


def test_valid_custom_style_loads(tmp_path, monkeypatch):
    styles = tmp_path / "output-styles"
    styles.mkdir()
    _style(styles / "terse.md")
    monkeypatch.setattr(output_styles, "PROJECT_STYLES_DIR", styles)
    monkeypatch.setattr(output_styles, "USER_STYLES_DIR", tmp_path / "none")
    out = output_styles.discover_custom_styles()
    assert out["terse"]["prompt"] == "STYLE BODY"


def test_symlink_escape_rejected(tmp_path, monkeypatch):
    styles = tmp_path / "output-styles"
    styles.mkdir()
    secret = tmp_path / "secret.md"
    secret.write_text("---\nname: leak\n---\nSECRET CONTENT\n")
    os.symlink(secret, styles / "leak.md")  # escape target outside styles dir
    monkeypatch.setattr(output_styles, "PROJECT_STYLES_DIR", styles)
    monkeypatch.setattr(output_styles, "USER_STYLES_DIR", tmp_path / "none")
    out = output_styles.discover_custom_styles()
    assert "leak" not in out


def test_oversize_style_skipped(tmp_path, monkeypatch):
    styles = tmp_path / "output-styles"
    styles.mkdir()
    big = styles / "huge.md"
    big.write_text("---\nname: huge\n---\n" + ("x" * (256 * 1024 + 1)))
    _style(styles / "ok.md", name="ok")
    monkeypatch.setattr(output_styles, "PROJECT_STYLES_DIR", styles)
    monkeypatch.setattr(output_styles, "USER_STYLES_DIR", tmp_path / "none")
    out = output_styles.discover_custom_styles()
    assert "huge" not in out
    assert "ok" in out


def test_plugin_style_contained_to_plugin_dir(tmp_path, monkeypatch):
    plugin_dir = tmp_path / "plugin-one"
    styles = plugin_dir / "output-styles"
    styles.mkdir(parents=True)
    _style(styles / "plug.md", name="plug")

    import zcoder.claude.tools.plugins as plugins

    monkeypatch.setattr(
        plugins,
        "load_plugin_output_styles",
        lambda: [
            {
                "name": "plug",
                "path": str(styles / "plug.md"),
                "plugin": "plugin-one",
                "plugin_dir": str(plugin_dir),
            }
        ],
    )
    # escape attempt: path outside the declared plugin dir must be rejected
    evil = tmp_path / "evil.md"
    evil.write_text("---\nname: plug\n---\nEVIL\n")

    def fake_loader():
        return [
            {
                "name": "plug",
                "path": str(evil),
                "plugin": "plugin-one",
                "plugin_dir": str(plugin_dir),
            }
        ]

    monkeypatch.setattr(plugins, "load_plugin_output_styles", fake_loader)
    monkeypatch.setattr(output_styles, "PROJECT_STYLES_DIR", tmp_path / "none1")
    monkeypatch.setattr(output_styles, "USER_STYLES_DIR", tmp_path / "none2")
    out = output_styles.discover_custom_styles()
    assert out.get("plug", {}).get("prompt") != "EVIL"
