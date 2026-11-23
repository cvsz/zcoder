# คำแนะนำสำหรับ Gemini และ ZCoder Configuration

ก่อนทำงานใน repository นี้ ให้อ่านและปฏิบัติตาม [AGENTS.md](AGENTS.md) ซึ่งเป็นแหล่งคำแนะนำหลักของ ZCoder ครอบคลุมขอบเขต ภาษา local inference ความปลอดภัย การตรวจสอบ และ release policy

## Active Default Model Configuration
- **Inference Runtime:** Ollama local service (`zcoder-llm`) บน `http://127.0.0.1:11434` — **เป็น runtime เดียวที่ใช้งาน ไม่มี llama-server อีกต่อไป**
- **Models dir:** `/zdata/models/` (zcoder-flash, zcoder-pro, zcoder-max, zcoder-promax)
- **Active Model ID:** `zcoder-pro` (default; override ด้วย `ZCODER_MODEL`)
- **Context Window:** 128,000 tokens (zcoder-pro/max), 32,768 tokens (zcoder-flash)
- **Hardware Profile:** 32GB+ RAM, 24GB+ VRAM (GGUF quantization Q4_K_M–Q8_0)
