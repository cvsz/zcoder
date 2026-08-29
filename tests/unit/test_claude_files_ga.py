"""Regression coverage for the Anthropic Files API GA response shapes."""

import json
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

import pytest

import zcoder.claude.integrations.files as files_module
from zcoder.claude.integrations.files import FilesAPI, parse_expires_at


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(files_module, "LOCAL_REGISTRY", tmp_path / "files_registry.json")
    return FilesAPI(api_key="sk-test", model="claude-sonnet-5")


def install_json_responses(monkeypatch, responses, captured=None):
    pending = list(responses)

    def fake_urlopen_json(request, timeout):
        if captured is not None:
            captured.append(request)
        return pending.pop(0)

    monkeypatch.setattr(files_module, "urlopen_json", fake_urlopen_json)


def test_parse_expires_at_prefers_absolute_timestamp():
    value = "2026-09-21T00:00:00Z"
    assert parse_expires_at({"expires_at": value, "expires_in_seconds": 60}) == value


def test_parse_expires_at_derives_absolute_timestamp_from_relative_seconds():
    base = datetime(2026, 8, 29, tzinfo=timezone.utc)
    assert parse_expires_at({"expires_in_seconds": 3600}, now=base) == "2026-08-29T01:00:00+00:00"


@pytest.mark.parametrize(
    "value",
    [None, "not-a-number", -1, True],
)
def test_parse_expires_at_is_defensive(value):
    assert parse_expires_at({"expires_in_seconds": value}) is None
    assert parse_expires_at(None) is None
    assert parse_expires_at("not-a-file") is None


def test_files_headers_are_ga_without_beta_header(api):
    headers = api._headers()
    assert "anthropic-beta" not in {key.lower() for key in headers}
    assert headers["anthropic-version"] == "2023-06-01"


def test_upload_normalizes_relative_expiration_before_registry_write(api, monkeypatch, tmp_path):
    install_json_responses(
        monkeypatch,
        [{"id": "file_ga", "filename": "report.pdf", "expires_in_seconds": 60}],
    )
    source = tmp_path / "report.pdf"
    source.write_bytes(b"pdf")

    result = api.upload(str(source))

    assert result["id"] == "file_ga"
    assert result["expires_at"]
    saved = json.loads(files_module.LOCAL_REGISTRY.read_text())
    assert saved["file_ga"]["local_path"] == str(source)


def test_upload_rejects_response_without_file_id(api, monkeypatch, tmp_path):
    install_json_responses(monkeypatch, [{"filename": "report.pdf"}])
    source = tmp_path / "report.pdf"
    source.write_bytes(b"pdf")

    with pytest.raises(RuntimeError, match="no file id"):
        api.upload(str(source))

    assert not files_module.LOCAL_REGISTRY.exists()


def test_list_files_supports_ga_page_cursor(api, monkeypatch):
    captured = []
    install_json_responses(monkeypatch, [{"data": [], "next_page": None}], captured)

    api.list_files(limit=10, page="cursor/2")

    query = parse_qs(urlsplit(captured[0].full_url).query)
    assert query["page"] == ["cursor/2"]


def test_list_files_all_follows_ga_next_page_and_normalizes_expiration(api, monkeypatch):
    captured = []
    install_json_responses(
        monkeypatch,
        [
            {
                "data": [{"id": "file_1", "expires_in_seconds": 60}],
                "next_page": "cursor-2",
                "has_more": True,
            },
            {"data": [{"id": "file_2"}], "next_page": None, "has_more": False},
        ],
        captured,
    )

    result = api.list_files_all()

    assert [item["id"] for item in result] == ["file_1", "file_2"]
    assert result[0]["expires_at"]
    assert "after_id" not in captured[0].full_url
    assert "page=cursor-2" in captured[1].full_url


def test_list_files_all_falls_back_to_legacy_after_id_cursor(api, monkeypatch):
    captured = []
    install_json_responses(
        monkeypatch,
        [
            {"data": [{"id": "file_1"}, {"id": "file_2"}], "has_more": True},
            {"data": [{"id": "file_3"}], "has_more": False},
        ],
        captured,
    )

    result = api.list_files_all()

    assert [item["id"] for item in result] == ["file_1", "file_2", "file_3"]
    assert "after_id=file_2" in captured[1].full_url
    assert all("page=" not in request.full_url for request in captured)


def test_list_files_all_tolerates_empty_and_malformed_pages(api, monkeypatch):
    install_json_responses(monkeypatch, [{"data": ["not-a-dict", {"id": "file_x"}], "has_more": False}])

    result = api.list_files_all()

    assert result == ["not-a-dict", {"id": "file_x"}]


def test_ask_about_file_omits_files_beta_header(api, monkeypatch):
    captured = []
    install_json_responses(
        monkeypatch,
        [{"content": [{"type": "text", "text": "answer"}]}],
        captured,
    )

    assert api.ask_about_file("file_1", "what is this?") == "answer"
    assert "anthropic-beta" not in {key.lower() for key in captured[0].headers}
