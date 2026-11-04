## วิธีใช้งาน

แนะนำให้เริ่มจาก OpenCode ก่อน เพราะมี Make Targets รองรับอยู่แล้ว

1\. ตรวจสอบ Models

```
make opencode-models
make opencode-free-models
make opencode-nvidia-models
make opencode-kilo-models
```

2\. เริ่มดำเนินการด้วย Free Model

นำ Master Prompt ไปบันทึกเป็น `AUSI_MASTER_PROMPT.md` แล้วสั่ง:

```
make opencode-free-prompt PROMPT="$(cat AUSI_MASTER_PROMPT.md)"
```

3\. หรือใช้ Background Execution

```
make opencode-free-bg PROMPT="$(cat AUSI_MASTER_PROMPT.md)"
```

4\. ใช้ Model ที่กำหนดเอง

```
make opencode-prompt \
  PROMPT="$(cat AUSI_MASTER_PROMPT.md)" \
  OPENCODE_MODEL="provider/model"
```

ต้องตรวจสอบ syntax และความสามารถของ Make Target จริงใน Makefile ก่อนใช้งาน โดยเฉพาะ Background Execution และการเลือก Free Model

## ข้อเสนอแนะด้าน Architecture

ผมแนะนำให้ใช้โครงสร้างแบบนี้:

| Layer             | หน้าที่                |
| ----------------- | ---------------------- |
| AUSI Core         | Orchestrator กลาง      |
| Agent Registry    | จัดการ Agents          |
| Skills Registry   | จัดการ Skills          |
| Provider Adapters | เชื่อมต่อ AI แต่ละค่าย |
| Model Router      | เลือก Model ตามงาน     |
| Execution Engine  | ควบคุมการทำงาน         |
| Governance        | Review, Security, QA   |
| Observability     | Logs, Metrics, Traces  |

หลักการสำคัญ: สร้าง Universal Skills กลางเพียงชุดเดียว แล้วทำ Native Adapter สำหรับ Claude, Codex, Gemini, Kilo, Antigravity และ OpenCode แทนการสร้างระบบแยกหกชุด วิธีนี้ลด Code Duplication และทำให้เพิ่ม Provider ใหม่ได้ง่ายกว่า

สถานะ ณ ตอนนี้: Prompt พร้อมใช้งาน — ยังไม่ได้ตรวจหรือแก้ไข Repository จริง