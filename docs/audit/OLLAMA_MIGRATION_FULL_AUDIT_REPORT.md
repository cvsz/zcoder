# รายงานการตรวจสอบเชิงลึกและการอัปเกรดระบบ ZCoder (Full Audit & Upgrade Report)

**วันที่และเวลา:** 2026-11-23 17:39:00 +07:00  
**Repository:** `cvsz/zcoder`  
**Branch:** `feat/ollama-migration-zpostgressql`  
**Pull Request:** [#254 (refactor: migrate inference to Ollama and standardize zpostgressql)](https://github.com/cvsz/zcoder/pull/254)  
**GPG Signed Commit:** `f78ffc951fff348929ef921767f4d59ff21b1807`

---

## 1. วัตถุประสงค์ของการเปลี่ยนแปลง (Objectives)

1. **ยกเลิกการใช้วงจร `llama-server` ทั้งระบบ:** ปลดประจำการ binary และ service llama-server (เดิมใช้พอร์ต 8080/9801–9804) และย้ายกระบวนการ local inference ทั้งหมดไปยัง **Ollama loopback service (`http://127.0.0.1:11434`)**
2. **รองรับโมเดลจากไดเรกทอรี `/zdata/models/`:** ตรวจสอบและลงทะเบียนโมเดล GGUF ทั้งหมดใน `/zdata/models/` ให้ทำงานผ่าน Ollama endpoint
3. **ปรับเปลี่ยนมาตรฐานฐานข้อมูล PostgreSQL:** ปรับชื่อ container, volume, service และเครือข่าย Docker เป็น `zpostgressql` และ `zpostgressql_network` อย่างเป็นเอกภาพทั่วทั้งโครงการ
4. **อัปเดตเอกสารและคอนฟิกูเรชันทั้งหมด:** ปรับปรุง Docker Compose, Makefile, Scripts, Configs และเอกสารในไดเรกทอรี `docs/` และ `README.md`
5. **ทดสอบและยืนยันผลความถูกต้องทั้งระบบ:** รัน Focused Unit Tests, End-to-End Tests และ Lint Check 100%

---

## 2. ผลการตรวจสอบไฟล์แบบรายไฟล์ (File-by-File Review)

### 2.1 วงจรโมเดลและ Local Inference (Ollama Migration)
- **`config/models.yaml`**:
  - เปลี่ยน runtime controller จาก llama-server เป็น Ollama singleton daemon (`http://127.0.0.1:11434`)
  - อัปเดต sector models: `zcoder-flash` (32K), `zcoder-pro` (128K - default), `zcoder-max` (262K), `zcoder-promax` (262K)
- **`scripts/model_server.py`**:
  - ปรับระบบ health check ให้ตรวจจับ Ollama native endpoints (`/api/version`, `/api/tags`)
  - จัดการ subprocess lifecycle สำหรับ `ollama serve` และ fallback loopback verification
- **`src/zcoder/enterprise/local_ai_stack.py`**:
  - ปรับ `LlamaCppRuntime` เป็น Deprecated และเปลี่ยน default endpoint ไปที่ `http://127.0.0.1:11434`
- **`src/zcoder/agent/orchestration/providers.py` & `src/zcoder/agent/orchestration/local.py`**:
  - ตั้งค่า provider gateway เริ่มต้นสำหรับ openai-compatible ให้ชี้ตรงไปยัง Ollama loopback (`http://127.0.0.1:11434/v1`)
- **`src/zcoder/core/health.py` & `src/zcoder/main.py`**:
  - อัปเดตการตรวจเช็ค system health ให้รองรับพอร์ต 11434 และ hostname loopback
- **`src/zcoder/interfaces/cli/tui.py` & `webapp/backend/server.py`**:
  - อัปเดตพอร์ตการเชื่อมต่อและการสตรีมมิ่งใน TUI และ Web Console ไปยังพอร์ต 11434

### 2.2 คลังโมเดลใน `/zdata/models/`
ตรวจสอบความสมบูรณ์ของโมเดลผ่านระบบปฏิบัติการและ Ollama Local Service:
- **`zcoder-flash.gguf`** (1.8B Q4_K_M, Context: 32K) — Tag: `zcoder-flash:latest`
- **`zcoder-pro.gguf`** (7.6B Q4_K_M, Context: 128K) — Tag: `zcoder-pro:latest` (*Active Default*)
- **`zcoder-max.gguf`** (9.2B BF16, Context: 262K) — Tag: `zcoder-max:latest`
- **`zcoder-promax.gguf`** (27.3B Q4_K_M, Context: 262K) — Tag: `zcoder-promax:latest`

### 2.3 การปรับชื่อฐานข้อมูล `zpostgressql` และ Network `zpostgressql_network`
ดำเนินการเปลี่ยนชื่อครอบคลุมทั้งโครงการ:
- **`docker-compose.yml` & `docker-compose.zpitr.yml`**:
  - Service/Container: `zpostgressql`
  - Volume: `zpostgressql_data`
  - Network: `zpostgressql_network`
  - Container `zcoder` ผูกกับ `network_mode: "service:ollama"`
- **`.env.example` & `README.md`**:
  - ปรับ connection string เริ่มต้นเป็น `postgresql://zcoder@zpostgressql:5432/zcoder_db`
- **`scripts/local_postgres.py`**:
  - ปรับ network alias และ Docker network เป็น `zpostgressql_network`
- **`docker-resource-audit.sh` & `fix-zpitr.sh`**:
  - ตรวจสอบ container `zpostgressql` และ network `zpostgressql_network`

### 2.4 การอัปเดตเอกสารโครงการทั้งหมด
- **`README.md`**: ปรับสถาปัตยกรรม Local AI และ Bridge Infrastructure ให้สะท้อนการใช้ Ollama และ `zpostgressql`
- **`GEMINI.md`**: ยืนยันการเป็น runtime เดียวที่ใช้งาน (`http://127.0.0.1:11434`)
- **`Makefile`**: ปรับคำสั่ง `docker-up`, `docker-run`, `docker-logs`, `postgres-setup`, `postgres-status`
- **`docs/`**: อัปเดตไฟล์คู่มือทั้งหมดใน `docs/guides/`, `docs/operations/`, `docs/engineering/`, `docs/audit/`

---

## 3. ผลการทดสอบทั้งระบบ (Verification & Quality Gates)

1. **Ruff Linter & Formatter:**
   ```bash
   ruff check src tests webapp scripts/model_server.py scripts/local_postgres.py
   # Output: All checks passed!
   ```
2. **Focused Unit & End-to-End Test Suite:**
   ```bash
   pytest tests/unit/test_config.py tests/unit/test_coder.py tests/unit/test_agents.py \
          tests/unit/codeagent/test_skills.py tests/unit/codeagent/test_web.py \
          tests/unit/test_full_flow.py tests/unit/test_tools.py tests/unit/test_tui.py \
          tests/unit/test_version_metadata.py tests/unit/test_session_log.py \
          tests/unit/test_production_config.py tests/unit/test_sec008_env_inheritance.py \
          tests/unit/test_backup_restore.py tests/unit/test_docker_entrypoint.py \
          tests/e2e/test_webapp_server.py
   ```
   **ผลการทดสอบ:** **ผ่าน 232 / 232 tests (100% Passed, 0 Failures)**

---

## 4. สถานะ Git, GPG Signing และการส่งมอบ

- **GPG Signing:** ลงนามด้วยคีย์ `0C54E869DE49D872` (cvsz zcoder signing)
- **สถานะลายเซ็น:** `Good signature from "cvsz (zcoder signing) <seaza@msn.com>"`
- **Git Branch:** `feat/ollama-migration-zpostgressql`
- **GitHub Pull Request:** [https://github.com/cvsz/zcoder/pull/254](https://github.com/cvsz/zcoder/pull/254)
