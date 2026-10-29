import json
from http.server import HTTPServer
from threading import Thread
from unittest.mock import MagicMock, patch
from urllib.request import urlopen

import pytest

from zgpu.llm.kv_cache import KVCache
from zgpu.llm.quantization import Quantizer
from zgpu.llm.server import JSONRPCHandler, run_server
from zgpu.llm.transformer import ZGPULLM, LLMConfig
from zgpu.nn.linear import Linear
from zgpu.runtime.runtime import ZRuntime


def test_linear_layer():
    rt = ZRuntime()
    # 4x4 input and linear layer with 4x4 weights
    layer = Linear(in_features=4, out_features=4, bias=True, runtime=rt)
    layer.weight = [[1.0] * 4 for _ in range(4)]
    layer.bias = [0.5] * 4

    x = [[1.0, 2.0, 3.0, 4.0]]
    out = layer(x)
    assert len(out) == 1
    assert len(out[0]) == 4
    # (1+2+3+4) * 1.0 + 0.5 = 10.5
    for val in out[0]:
        assert pytest.approx(val, rel=1e-3) == 10.5


def test_transformer_forward():
    rt = ZRuntime()
    cfg = LLMConfig(vocab_size=32, d_model=8, num_heads=2, d_ff=16, num_layers=1, max_seq_len=16)
    model = ZGPULLM(config=cfg, runtime=rt)

    tokens = [5, 12, 19]
    logits = model.forward(tokens)
    assert len(logits) == 3
    assert len(logits[0]) == cfg.vocab_size


def test_transformer_generate():
    rt = ZRuntime()
    cfg = LLMConfig(vocab_size=32, d_model=8, num_heads=2, d_ff=16, num_layers=1, max_seq_len=16)
    model = ZGPULLM(config=cfg, runtime=rt)

    prompt = [3, 7]
    generated = model.generate(prompt, max_new_tokens=4)
    assert len(generated) == 6
    assert generated[:2] == prompt


def test_server_rpc_methods():
    handler = JSONRPCHandler.__new__(JSONRPCHandler)
    handler.headers = {"Content-Length": "0"}
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()

    # Test health method
    req_body = json.dumps({"jsonrpc": "2.0", "id": 10, "method": "system.health"}).encode("utf-8")
    handler.rfile = MagicMock()
    handler.rfile.read.return_value = req_body
    handler.headers = {"Content-Length": str(len(req_body))}
    handler.do_POST()

    written_data = b"".join(call.args[0] for call in handler.wfile.write.call_args_list)
    res = json.loads(written_data.decode("utf-8"))
    assert res["id"] == 10
    assert res["result"]["healthy"] is True
    assert res["result"]["engine"] == "zGPU-Python-SIMT-TensorCore-Simulator"
    assert res["result"]["device"] == "zGPU-Simulator-0"


def test_llm_api_rejects_network_wide_bind():
    with pytest.raises(ValueError, match="loopback only"):
        run_server(host="0.0.0.0")  # nosec B104


def test_server_exposes_openai_model_discovery():
    handler = JSONRPCHandler.__new__(JSONRPCHandler)
    handler.path = "/v1/models"
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()

    handler.do_GET()

    response = json.loads(b"".join(call.args[0] for call in handler.wfile.write.call_args_list))
    assert response["object"] == "list"
    assert response["data"]
    assert response["data"][0]["owned_by"] == "zgpu"


def test_server_serves_openai_model_discovery_over_loopback_http():
    server = HTTPServer(("127.0.0.1", 0), JSONRPCHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        assert host == "127.0.0.1"
        with urlopen(f"http://{host}:{port}/v1/models", timeout=2) as response:  # nosec B310
            payload = json.load(response)
        assert payload["object"] == "list"
        assert payload["data"]
        assert all(model["owned_by"] == "zgpu" for model in payload["data"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_server_exposes_openai_chat_completion_route():
    handler = JSONRPCHandler.__new__(JSONRPCHandler)
    payload = {"model": "zgpu-small", "messages": [{"role": "user", "content": "Hi"}]}
    raw_body = json.dumps(payload).encode()
    handler.path = "/v1/chat/completions"
    handler.headers = {"Content-Length": str(len(raw_body))}
    handler.rfile = MagicMock()
    handler.rfile.read.return_value = raw_body
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()
    expected = {"id": "chatcmpl-test", "object": "chat.completion", "choices": []}

    with patch("zgpu.llm.server.openai_adapter.create_completion", return_value=expected):
        handler.do_POST()

    response = json.loads(b"".join(call.args[0] for call in handler.wfile.write.call_args_list))
    assert response == expected


def test_server_streams_openai_chat_completion_as_sse():
    handler = JSONRPCHandler.__new__(JSONRPCHandler)
    payload = {"messages": [{"role": "user", "content": "Hi"}], "stream": True}
    raw_body = json.dumps(payload).encode()
    handler.path = "/v1/chat/completions"
    handler.headers = {"Content-Length": str(len(raw_body))}
    handler.rfile = MagicMock()
    handler.rfile.read.return_value = raw_body
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()

    def fake_completion(_payload, event_callback):
        event_callback({"object": "chat.completion.chunk", "choices": [{"delta": {"content": "Hi"}}]})

    with patch("zgpu.llm.server.openai_adapter.create_completion", side_effect=fake_completion):
        handler.do_POST()

    stream = b"".join(call.args[0] for call in handler.wfile.write.call_args_list).decode()
    assert "text/event-stream; charset=utf-8" in [
        call.args[1] for call in handler.send_header.call_args_list if call.args[0] == "Content-Type"
    ]
    assert '"content":"Hi"' in stream
    assert "data: [DONE]" in stream


def test_quantization_int8():
    data = [-1.0, -0.5, 0.0, 0.5, 1.0]
    q_tensor = Quantizer.quantize_int8_symmetric(data, shape=(5,))
    assert q_tensor.bits == 8
    assert len(q_tensor.q_data) == 5
    assert q_tensor.q_data[0] == -127
    assert q_tensor.q_data[-1] == 127

    deq = q_tensor.dequantize()
    for orig, d in zip(data, deq, strict=False):
        assert pytest.approx(orig, abs=0.02) == d


def test_quantization_int4_pack_unpack():
    data = [-1.0, 0.0, 1.0, -0.5]
    q_tensor = Quantizer.quantize_int4_symmetric(data, shape=(4,))
    assert q_tensor.bits == 4
    assert len(q_tensor.q_data) == 4

    packed = Quantizer.pack_int4(q_tensor.q_data)
    assert len(packed) == 2

    unpacked = Quantizer.unpack_int4(packed, target_len=4)
    assert unpacked == q_tensor.q_data


def test_kv_cache():
    cache = KVCache(max_seq_len=8, num_layers=1, d_model=4)
    assert cache.current_seq_len == 0

    k0 = [1.0, 2.0, 3.0, 4.0]
    v0 = [0.1, 0.2, 0.3, 0.4]
    all_k, _all_v = cache.update(0, k0, v0)
    assert len(all_k) == 1
    assert all_k[0] == k0
    cache.advance_step()
    assert cache.current_seq_len == 1

    k1 = [5.0, 6.0, 7.0, 8.0]
    v1 = [0.5, 0.6, 0.7, 0.8]
    all_k2, _all_v2 = cache.update(0, k1, v1)
    assert len(all_k2) == 2
    assert all_k2[1] == k1


def test_kv_cache_rejects_invalid_layers_vectors_and_capacity():
    cache = KVCache(max_seq_len=1, num_layers=1, d_model=2)
    for layer_idx in (-1, 1, True):
        with pytest.raises(ValueError):
            cache.update(layer_idx, [1.0, 2.0], [3.0, 4.0])
    with pytest.raises(ValueError, match="each contain 2 values"):
        cache.update(0, [1.0], [2.0])
    with pytest.raises(ValueError, match="finite numeric"):
        cache.update(0, [float("nan"), 1.0], [2.0, 3.0])

    key = [1.0, 2.0]
    values, _ = cache.update(0, key, [3.0, 4.0])
    key[0] = 99.0
    assert values[0] == [1.0, 2.0]
    cache.advance_step()
    with pytest.raises(ValueError, match="capacity is exhausted"):
        cache.update(0, [1.0, 2.0], [3.0, 4.0])
    with pytest.raises(ValueError, match="capacity is exhausted"):
        cache.advance_step()
    cache.reset()
    assert cache.current_seq_len == 0
    assert cache.update(0, [5.0, 6.0], [7.0, 8.0])[0] == [[5.0, 6.0]]


@pytest.mark.parametrize("field", ["max_batch_size", "max_seq_len", "num_layers", "d_model"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_kv_cache_dimensions_must_be_positive_integers(field, value):
    with pytest.raises(ValueError, match="positive integer"):
        KVCache(**{field: value})


def test_thai_multilingual_tokenizer():
    from zgpu.llm.thai_tokenizer import ThaiMultilingualTokenizer

    tok = ThaiMultilingualTokenizer(vocab_size=256)
    text = "สวัสดี zGPU ภาษาไทย"
    ids = tok.encode(text)
    assert len(ids) > 0
    decoded = tok.decode(ids)
    assert decoded == text
