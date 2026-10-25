# การทบทวน Changelog ของผู้ช่วยเขียนโค้ดภายนอก — การปรับ zCoder ให้ทำงานแบบ Local-Only

แหล่งข้อมูล: https://github.com/PROVIDER_CREDENTIAL_OR_CONFIG/provider model ID/blob/main/CHANGELOG.md

ตรวจสอบ upstream ที่เวอร์ชัน **2.1.308** (รวม 2.1.307–2.1.304) เอกสารนี้บันทึก **แนวคิดด้านพฤติกรรม** ไม่ใช่การย้าย source code หรือการเชื่อมต่อกับ API ของ PROVIDER_CREDENTIAL_OR_CONFIG การ inference โมเดลใหม่สำหรับ normal prompt CLI ใช้ self-hosted llama.cpp GGUF server บน loopback เส้นทางนี้ไม่ต้องใช้ model, API key, SDK หรือสิทธิ์ PROVIDER_CREDENTIAL_OR_CONFIG

## การเปลี่ยนแปลงด้านความทนทานจาก upstream ที่เกี่ยวข้องและแนวทางนำมาใช้ในระบบ local

| รุ่นของผู้ช่วยเขียนโค้ดภายนอก | การเปลี่ยนแปลง upstream | แนวทางปรับใช้ใน zCoder | สถานะ |
|---|---|---|---|
| 2.1.307 | retry HTTP MCP เฉพาะการเรียกแบบ read-only/idempotent | ตรวจสอบ retry ของ MCP ที่มีอยู่ และห้าม auto-retry สำหรับ write ที่มี side effect | วางแผนไว้ ยังไม่ implement |
| 2.1.307 | ส่ง safety events แบบมีโครงสร้างสำหรับ permission, hooks และ sandbox decisions | ออกแบบ schema ของ local audit event โดยไม่พึ่ง remote telemetry | วางแผนไว้ |
| 2.1.307 | กู้คืนจาก tool call ที่ parse ไม่ได้ด้วย retry ที่มีขอบเขต | เพิ่ม repair attempts สูงสุดสองครั้ง โดยใช้ request ID ที่คงที่และมี evidence | วางแผนไว้ |
| 2.1.305 | ไม่รัน parallel tasks ที่เสร็จแล้วซ้ำเมื่อ workflow resume | บันทึก task ที่เสร็จแล้วลง journal และตรวจ replay behavior หลัง restart | วางแผนไว้ |
| 2.1.304 | ต้องมีบุคคลอนุมัติเมื่อ hook ร้องขอ approval | ให้ headless permissions เป็น deny เว้นแต่มี external approval ที่ถูกต้อง | วางแผนไว้ |
| 2.1.304 | รวม read-only metadata ในการตัดสิน permission | แยก pure reads ออกจาก mutations ใน tool policies และ tests | วางแผนไว้ |
| 2.1.304 | เคารพขอบเขตการลบที่ปลอดภัยใกล้ mounted drives | เพิ่มความเข้มงวดของ filesystem delete checks บน Windows, WSL และ Linux | วางแผนไว้ |

ข้อกำหนดเหล่านี้เป็นแนวทางที่ **ได้แรงบันดาลใจจาก public release notes** ไม่ใช่การยืนยันว่าได้คัดลอก implementation upstream หรือว่า zCoder ผ่าน acceptance tests เหล่านี้แล้ว

## การเปลี่ยนไปใช้ local model โดยเร่งด่วน

คำขอข้อความปกติและ `--agent ... -p` จะถูกส่งไปยัง llama.cpp HTTP server ภายในเครื่องที่ `http://127.0.0.1:8080/v1/chat/completions` local transport ตรวจสอบ loopback URL และจะไม่ fallback ไปยัง PROVIDER_CREDENTIAL_OR_CONFIG หรือ provider ภายนอกอื่นเมื่อเกิดข้อผิดพลาด

ไฟล์โมเดลที่รองรับใน WSL environment ของ operator:

- `/home/cvsz/zgpu/qwen2.5-coder-7b-instruct-q4_k_m.gguf`
- `/home/cvsz/zgpu/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf`

เริ่ม server ด้วย `bash scripts/start_local_gguf.sh 7b` หรือ `1.5b` repository นี้จะไม่ bundle, upload หรือ download ไฟล์โมเดลทั้งสอง

## Blockers ก่อนอ้างว่า "ไม่เรียก PROVIDER_CREDENTIAL_OR_CONFIG" ได้ในทุก feature

- Legacy modules จำนวนมากยัง import `PROVIDER_CREDENTIAL_OR_CONFIG` หรือเรียก endpoint เฉพาะของ PROVIDER_CREDENTIAL_OR_CONFIG
- feature ด้าน administration, compliance, billing, model registry และ SDK ของ PROVIDER_CREDENTIAL_OR_CONFIG ยังไม่มี local GGUF equivalent ต้อง disable/hide หรือปฏิเสธการทำงานเหล่านั้นอย่างชัดเจนก่อนกล่าวอ้างว่าไม่พึ่ง provider ภายนอกโดยรวม
- `--route`, `--code-agent`, interactive/TUI, projects และ workflows มี provider paths แยกกัน ต้องตรวจสอบแต่ละเส้นทาง
- legacy unit tests ที่จำลอง provider API responses ต้องย้ายไปใช้ local provider contracts แบบ staged
- CI, Ruff/Black, Bandit, full pytest และ real WSL llama.cpp smoke tests ต้องผ่านบน exact PR SHA

ห้ามใช้ local response ปลอมเป็นหลักฐานว่าเกิด model inference จริง และห้ามระบุว่า feature จาก upstream changelog ถูก implement แล้วจนกว่าจะมี tests รองรับ

## หลักฐานการยอมรับ

- `python -m pytest tests/unit/test_local_gguf_default.py -q`
- `python -m pytest tests/ -q`
- `black --check .`
- `ruff check .`
- `bandit -r . -ll -x ./tests,./build,./dist`
- CodeQL และ independent review
- การตอบสนองจาก real WSL model server และการตรวจสอบ egress

feature ที่ยังไม่มีหลักฐานจริงต้องคงสถานะ pending
