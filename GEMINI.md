# คำแนะนำสำหรับ Gemini และ ZCoder Configuration

ก่อนทำงานใน repository นี้ ให้อ่านและปฏิบัติตาม [AGENTS.md](AGENTS.md) ซึ่งเป็นแหล่งคำแนะนำหลักของ ZCoder ครอบคลุมขอบเขต ภาษา local inference ความปลอดภัย การตรวจสอบ และ release policy

## Active Default Model Configuration
- **Active Model ID:** `qwen3.8-27b-turbo-fable-neo-coder` (DavidAU Qwen3.8-27B-TURBO-Fable-Cold-Fusion-735-882-Heretic-Uncensored-NEO-CODER-MAX-MTP-GGUF).
- **Inference Provider:** Ollama / Llama.cpp local container (`zcoder-llm`) running on `http://127.0.0.1:8080/v1`.
- **Context Window:** 128,000 tokens.
- **Hardware Profile:** 32GB+ RAM, 24GB+ VRAM (GGUF quantization).
