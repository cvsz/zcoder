# คำแนะนำสำหรับ Gemini และ ZCoder Configuration

ก่อนทำงานใน repository นี้ ให้อ่านและปฏิบัติตาม [AGENTS.md](AGENTS.md) ซึ่งเป็นแหล่งคำแนะนำหลักของ ZCoder ครอบคลุมขอบเขต ภาษา local inference ความปลอดภัย การตรวจสอบ และ release policy

## Active Default Model Configuration
- **Active Model ID:** `zcoder-7b-q4km` (`/zdata/models/zcoder-7b-q4km.gguf`, Q4_K_M).
- **Inference Provider:** Ollama / Llama.cpp local container (`zcoder-llm`) running on `http://127.0.0.1:8080/v1`.
- **Context Window:** `ZCODER_CTX_SIZE` (default: 4096 tokens).
- **Model Inventory:** `zcoder-1.5b-q4km.gguf`, `zcoder-7b-q4km.gguf`, and `zcoder-32b-q4km.gguf` under `/zdata/models/`.
