import pytest

from zgpu.llm.openai_compat import CompletionRequestError, OpenAICompatibleAdapter, ProviderPool


class FakeRegistry:
    def __init__(self):
        self.prompts = []

    def list_models(self):
        return [{"name": "zgpu-small"}, {"name": "zgpu-code"}]

    def tokenize(self, model_name, text):
        assert model_name in {"zgpu-small", "zgpu-code", "zgpu-thai"}
        return list(text)

    def generate(self, prompt, model_name=None, max_tokens=16, token_callback=None):
        self.prompts.append((prompt, model_name, max_tokens))
        text = "OK"
        if token_callback:
            for piece in text:
                token_callback(piece)
        return {
            "text": text,
            "tokens_generated": len(text),
            "finish_reason": "stop",
            "model": model_name,
        }


def test_lists_models_using_openai_model_shape():
    adapter = OpenAICompatibleAdapter(FakeRegistry())

    assert adapter.list_models() == {
        "object": "list",
        "data": [
            {"id": "zgpu-small", "object": "model", "created": 0, "owned_by": "zgpu"},
            {"id": "zgpu-code", "object": "model", "created": 0, "owned_by": "zgpu"},
        ],
    }


def test_creates_openai_chat_completion_with_usage():
    registry = FakeRegistry()
    adapter = OpenAICompatibleAdapter(registry)

    response = adapter.create_completion(
        {
            "model": "zgpu-code",
            "messages": [
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "Hello"},
            ],
            "max_completion_tokens": 4,
        }
    )

    assert response["object"] == "chat.completion"
    assert response["model"] == "zgpu-code"
    assert response["choices"][0]["message"] == {"role": "assistant", "content": "OK"}
    assert response["usage"]["completion_tokens"] == 2
    assert response["usage"]["total_tokens"] == response["usage"]["prompt_tokens"] + 2
    assert registry.prompts == [("system: Be concise.\nuser: Hello\nassistant:", "zgpu-code", 4)]


def test_streaming_emits_role_content_and_finish_chunks():
    adapter = OpenAICompatibleAdapter(FakeRegistry())
    events = []

    adapter.create_completion(
        {"model": "zgpu-small", "messages": [{"role": "user", "content": "Hi"}], "stream": True},
        event_callback=events.append,
    )

    assert events[0]["choices"][0]["delta"] == {"role": "assistant"}
    assert [event["choices"][0]["delta"].get("content") for event in events[1:3]] == ["O", "K"]
    assert events[-1]["choices"][0]["finish_reason"] == "stop"


def test_lists_and_routes_optional_local_provider_with_zgpu_branding():
    class FakeLocalProvider:
        def list_models(self):
            return [{"id": "zgpu-local-test", "object": "model", "created": 0, "owned_by": "zgpu"}]

        def create_completion(self, payload, event_callback=None):
            assert payload["model"] == "zgpu-local-test"
            if event_callback:
                event_callback({"choices": [{"delta": {"content": "local"}}]})
                return None
            return {"choices": [{"message": {"role": "assistant", "content": "local"}}]}

    provider = FakeLocalProvider()
    adapter = OpenAICompatibleAdapter(FakeRegistry(), external_provider=provider)

    assert adapter.list_models()["data"][-1]["owned_by"] == "zgpu"
    response = adapter.create_completion(
        {"model": "zgpu-local-test", "messages": [{"role": "user", "content": "Hi"}]}
    )
    assert response["choices"][0]["message"]["content"] == "local"

    events = []
    result = adapter.create_completion(
        {"model": "zgpu-local-test", "messages": [{"role": "user", "content": "Hi"}], "stream": True},
        event_callback=events.append,
    )
    assert result is None
    assert events[0]["choices"][0]["delta"]["content"] == "local"


def test_remote_provider_receives_openai_payload_without_simulator_restrictions():
    class FakeRemoteProvider:
        def __init__(self):
            self.payload = None

        def list_models(self):
            return [{"id": "zgpu-remote-model", "object": "model", "created": 0, "owned_by": "zgpu"}]

        def create_completion(self, payload, event_callback=None):
            self.payload = payload
            return {"model": payload["model"], "choices": []}

    registry = FakeRegistry()
    provider = FakeRemoteProvider()
    adapter = OpenAICompatibleAdapter(registry, external_provider=provider)
    payload = {
        "model": "zgpu-remote-model",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "Inspect this image"}]}],
        "tools": [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}],
        "max_completion_tokens": 2048,
        "stream": False,
    }

    result = adapter.create_completion(payload)

    assert result["model"] == "zgpu-remote-model"
    assert provider.payload is payload
    assert registry.prompts == []


def test_remote_provider_accepts_one_signature_checked_inline_image():
    class FakeRemoteProvider:
        def __init__(self):
            self.payload = None

        def list_models(self):
            return [{"id": "zgpu-remote-model", "owned_by": "zgpu"}]

        def create_completion(self, payload, event_callback=None):
            self.payload = payload
            return {"model": payload["model"], "choices": []}

    provider = FakeRemoteProvider()
    adapter = OpenAICompatibleAdapter(FakeRegistry(), external_provider=provider)
    payload = {
        "model": "zgpu-remote-model",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "iVBORw0KGgo="}},
                ],
            }
        ],
    }

    adapter.create_completion(payload)

    assert provider.payload is payload


def test_remote_provider_rejects_oversized_and_multiple_inline_images():
    class FakeRemoteProvider:
        def list_models(self):
            return [{"id": "zgpu-remote-model", "owned_by": "zgpu"}]

        def create_completion(self, payload, event_callback=None):
            raise AssertionError("invalid image payload must not be forwarded")

    adapter = OpenAICompatibleAdapter(FakeRegistry(), external_provider=FakeRemoteProvider())
    valid_png = "data:image/png;base64," + "iVBORw0KGgo="
    for image_urls in (
        ["data:image/png;base64," + "iVBORw0KGgo=" + "A" * 700_000],
        [valid_png, valid_png],
    ):
        payload = {
            "model": "zgpu-remote-model",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}} for image_url in image_urls
                    ],
                }
            ],
        }
        with pytest.raises(CompletionRequestError, match="image"):
            adapter.create_completion(payload)


@pytest.mark.parametrize(
    "image_url",
    [
        "https://example.invalid/image.png",
        "data:image/png;base64,SGVsbG8=",
        "data:image/svg+xml;base64,PHN2Zy8+",
    ],
)
def test_remote_provider_rejects_external_or_mislabeled_image_urls(image_url):
    class FakeRemoteProvider:
        def list_models(self):
            return [{"id": "zgpu-remote-model", "owned_by": "zgpu"}]

        def create_completion(self, payload, event_callback=None):
            raise AssertionError("invalid image payload must not be forwarded")

    adapter = OpenAICompatibleAdapter(FakeRegistry(), external_provider=FakeRemoteProvider())
    payload = {
        "model": "zgpu-remote-model",
        "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": image_url}}]}],
    }

    with pytest.raises(CompletionRequestError, match="image"):
        adapter.create_completion(payload)


def test_local_completion_does_not_depend_on_remote_provider_availability():
    class OfflineProvider:
        def list_models(self):
            raise RuntimeError("remote service is offline")

    registry = FakeRegistry()
    adapter = OpenAICompatibleAdapter(registry, external_provider=OfflineProvider())

    response = adapter.create_completion(
        {"model": "zgpu-code", "messages": [{"role": "user", "content": "Hello"}]}
    )

    assert response["choices"][0]["message"]["content"] == "OK"
    assert registry.prompts


def test_provider_pool_combines_and_routes_models():
    class FakeProvider:
        def __init__(self, model_id):
            self.model_id = model_id

        def list_models(self):
            return [{"id": self.model_id, "object": "model", "owned_by": "zgpu"}]

        def create_completion(self, payload, event_callback=None):
            return {"model": self.model_id, "choices": []}

    pool = ProviderPool([None, FakeProvider("zgpu-local-test"), FakeProvider("zgpu-remote-test")])

    assert [model["id"] for model in pool.list_models()] == ["zgpu-local-test", "zgpu-remote-test"]
    assert pool.create_completion({"model": "zgpu-remote-test"})["model"] == "zgpu-remote-test"

    with pytest.raises(CompletionRequestError, match="unavailable"):
        pool.create_completion({"model": "missing"})


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"messages": []},
        {"messages": [{"role": "tool", "content": "result"}]},
        {"messages": [{"role": "user", "content": [{"type": "text", "text": "Hi"}]}]},
        {"messages": [{"role": "user", "content": "Hi"}], "max_tokens": True},
        {"messages": [{"role": "user", "content": "Hi"}], "max_tokens": 129},
        {"model": "missing", "messages": [{"role": "user", "content": "Hi"}]},
        {"messages": [{"role": "user", "content": "Hi"}], "stream": "true"},
    ],
)
def test_rejects_invalid_or_unsupported_completion_requests(payload):
    adapter = OpenAICompatibleAdapter(FakeRegistry())

    with pytest.raises(CompletionRequestError):
        adapter.create_completion(payload)
