# ZCoder Deployment & Operations Guide (Phase 9)

คู่มือการติดตั้งและดำเนินงาน ZCoder ในสภาพแวดล้อมจริง (production)
อ้างอิงจาก `docs/zcoder-big-upgrade.md` Phase 9 — Deployment & Operations

---

## 1. โครงสร้างไฟล์ที่เกี่ยวข้อง

| ไฟล์ | รายละเอียด |
|------|-------------|
| `cordis.yml` | การกำหนดค่าระบบหลัก (service, inference, model_sectors, web, session, logging, health, observability, security) |
| `.env.production` | ตัวแปรสภาพแวดล้อมสำหรับ production (คัดลอกเป็น `.env` แก้ไขค่าตามจริง) |
| `config/models.yaml` | คอนฟิก multi-sector GGUF model server (flash/pro/max/promax) |
| `src/zcoder/app/ops.py` | Operations facade: logging, health check, alerting, metrics |
| `src/zcoder/config/logging.py` | Structured logging (JSON/text), secret redaction |
| `scripts/deploy.py` | Smoke-test script สำหรับตรวจสอบว่าระบบทำงานถูกต้องหลัง deploy |
| `scripts/model-server-autostart.sh` | สคริปต์เริ่มต้น model server อัตโนมัติเมื่อ WSL boot |
| `scripts/setup-wsl-autostart.ps1` | PowerShell สำหรับตั้งค่า Windows Task Scheduler ให้ WSL เริ่มต้นอัตโนมัติ |

---

## 2. ขั้นตอนติดตั้ง (Production)

### 2.1 เตรียมไดเรกทอรีและสภาพแวดล้อม

```bash
cd /home/cvsz/zcoder
mkdir -p data logs run
cp .env.production .env
# แก้ไขค่าใน .env ให้ถูกต้อง โดยเฉพาะ ZCODER_WEB_API_KEY
```

### 2.2 ติดตั้ง dependencies

```bash
make install-all
# หรือ ติดตั้งเฉพาะส่วน web
pip install -r requirements.txt -r webapp/requirements-web.txt
```

### 2.3 กำหนดค่า model server

ตรวจสอบ `config/models.yaml` ว่า sector ที่ต้องการมี `enabled: true` และไฟล์ GGUF มีอยู่ใน `models_dir` (`/zdata/models`):

```bash
scripts/model-server list
```

หากยังไม่เริ่มต้น ให้เริ่มทุก sector:

```bash
scripts/model-server start all
```

---

## 3. การเริ่มระบบ (Start)

### 3.1 ใช้ Makefile (แนะนำ)

```bash
make start HOST=0.0.0.0 PORT=8420
```

Backend จะฟังที่ `0.0.0.0:8420` สามารถเรียกผ่าน `http://192.168.1.85:8420` หรือ `http://zcoder.zeaz.dev:8420` ได้

### 3.2 ใช้ uvicorn โดยตรง

```bash
ZCODER_WEB_API_KEY=<your-secret-key> \
uvicorn webapp.backend.server:app --host 0.0.0.0 --port 8420
```

### 3.3 ตรวจสอบว่าระบบพร้อมใช้งาน

```bash
curl -fsS http://192.168.1.85:8420/api/health
curl -fsS -H "Authorization: Bearer $ZCODER_WEB_API_KEY" \
  http://192.168.1.85:8420/api/models
```

---

## 4. การตรวจสอบสุขภาพ (Health Check)

ระบบมี endpoint สำหรับตรวจสอบสภาพการทำงาน:

| Endpoint | รายละเอียด |
|----------|-------------|
| `GET /api/health` | Shallow health check (config + python version) |
| `GET /api/health?deep=true` | Deep health check (รวมการเรียกโมเดลจริง) |

ตัวอย่างการตอบสนอง:

```json
{
  "status": "healthy",
  "checks": [
    {"name": "python_version", "ok": true, "detail": "3.12.x (ok)"},
    {"name": "config_dir_writable", "ok": true, "detail": ""},
    {"name": "local_model_configured", "ok": true, "detail": ""}
  ]
}
```

ถ้า `status` เป็น `unhealthy` ให้ตรวจสอบ log ใน `logs/` และตัวแปร `ZCODER_BASE_URL`

---

## 5. การดำเนินงานประจำวัน (Operations)

### 5.1 ดู log

```bash
tail -f logs/zcoder.log
# หรือ ถ้าใช้ JSON format
tail -f logs/zcoder.log | jq .
```

### 5.2 ดู metrics และ alerts

Metrics เขียนเป็น JSONL ที่ `logs/metrics.jsonl`:

```bash
tail -f logs/metrics.jsonl
```

Alerts ที่ออกได้แก่:
- `error` — เช่น โมเดลเรียกไม่สำเร็จ, auth ล้มเหลว
- `rate_limit` — เกินขีดจำกัดการเรียก API
- `degraded` — โมเดลเซิร์ฟเวอร์ไม่ตอบสนอง / health check ไม่ผ่าน

### 5.3 จัดการ model sector

```bash
scripts/model-server status zcoder-flash
scripts/model-server health zcoder-pro
scripts/model-server restart zcoder-max
scripts/model-server stop zcoder-promax
```

---

## 6. การปรับใช้ผ่าน Docker (ถ้ามี)

ไฟล์ `docker-compose.yml` ถูกกำหนดไว้แล้ว ให้ตั้งค่าตัวแปรสภาพแวดล้อมใน `.env` ก่อนรัน:

```bash
docker compose up -d
```

ตรวจสอบ health check ของคอนเทนเนอร์:

```bash
docker compose ps
```

---

## 7. การทดสอบหลังติดตั้ง (Smoke Test)

รันสคริปต์ทดสอบว่าระบบทำงานถูกต้อง:

```bash
python scripts/deploy.py
```

สคริปต์จะทดสอบ:
1. `/api/health` ตอบสนองหรือไม่
2. `/api/models` คืนรายชื่อโมเดลที่เปิดใช้งานหรือไม่
3. `/api/chat` สามารถส่ง prompt และรับคำตอบจากโมเดลได้หรือไม่
4. Health check ของแต่ละ model sector

ถ้าทุกขั้นตอนผ่านจะแสดง `SMOKE TEST PASSED` หากมีขั้นตอนใดล้มเหลวจะแสดงข้อผิดพลาดและคืนค่า exit code ไม่ใช่ศูนย์

---

## 8. การอัปเดตและ Rollback

### 7.1 อัปเดตโค้ด

```bash
git pull origin main
make install-all
make restart
```

### 7.2 Rollback (หากมีปัญหา)

```bash
git checkout <previous-commit>
make install-all
make restart
```

หรือใช้สำเนาสำรองของ `.env` และ `cordis.yml` ก่อนการเปลี่ยนแปลง

---

## 9. Checklist ก่อนส่ง production

- [ ] `.env` มี `ZCODER_WEB_API_KEY` ที่รัดกุม
- [ ] `ZCODER_BASE_URL` ชี้ไปยัง `127.0.0.1:9801/v1` (loopback ตามนโยบาย local-only)
- [ ] Model sector หลัก (`zcoder-flash`, `zcoder-pro`) `enabled: true` และไฟล์ GGUF มีอยู่จริง
- [ ] `logs/` และ `data/` สร้างไดเรกทอรีแล้ว
- [ ] รัน `python scripts/deploy.py` ผ่านทุกขั้นตอน
- [ ] ตรวจสอบ `curl /api/health` คืนค่า `status: healthy`

---

## 10. อ้างอิง

- `docs/zcoder-big-upgrade.md` — แผนปรับปรุงครั้งใหญ่ทั้งหมด (Phase 0–9)
- `config/models.yaml` — คอนฟิก model server รายละเอียด
- `.env.production` — ตัวแปรสภาพแวดล้อมตัวอย่าง
