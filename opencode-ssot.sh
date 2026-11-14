#!/usr/bin/env bash
# ==============================================================================
# OpenCode Autonomous Free-Router & Enterprise Workflow (Single Source of Truth)
# มาตรฐาน: shellcheck-clean | Zero-Paid-Model Leak | Multi-Provider Auto-Retry
# ==============================================================================
set -Eeuo pipefail

# --------------------------- 1. ค่าเริ่มต้น (Defaults) ---------------------------
ENV_FILE="${ENV_FILE:-.env}"
MODELS_FILE="${MODELS_JSON_PATH:-}"
PROMPT_LANG="${PROMPT_LANG:-th}"          # th | en
MAX_ROUNDS="${MAX_RETRY_ROUNDS:-2}"
INCLUDE_LOCAL="${INCLUDE_LOCAL:-1}"       # 1 = รวมโมเดล local เป็นด่านสุดท้าย, 0 = เฉพาะ cloud free
CLEAN_ONLY=0
DRY_RUN=0
CUSTOM_PROMPT=""

usage() {
  cat <<'USAGE'
Usage: opencode-ssot [OPTIONS]

Options:
  -f, --models-file PATH   ระบุพาธไฟล์ models.json / opencode.json ที่ต้องการล้าง Paid Models
  -e, --env-file PATH      ระบุพาธไฟล์ .env (ค่าเริ่มต้น: ./.env)
  -l, --lang th|en         เลือกภาษาของ Master Enterprise Prompt ในตัว (ค่าเริ่มต้น: th)
  -p, --prompt TEXT        ส่งคำสั่ง Prompt เฉพาะกิจแทน Master Prompt มาตรฐาน
  -r, --max-rounds NUM     จำนวนรอบสูงสุดในการวนลูปโมเดลฟรีทั้งหมด (ค่าเริ่มต้น: 2)
      --no-local           ตัดโมเดลตระกูล Local ออกจากคิวสำรอง
      --clean-only         ล้าง Paid Models ในไฟล์ให้เหลือเฉพาะ Free Models อย่างเดียวโดยไม่รันงาน
      --dry-run            ตรวจสอบคิวโมเดลและโครงสร้าง Config โดยไม่สั่งรันจริง
  -h, --help               แสดงวิธีใช้งาน
USAGE
}

# ------------------------- 2. รับค่าพารามิเตอร์ (CLI Args) -----------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -f|--models-file) MODELS_FILE="${2:?ต้องระบุพาธไฟล์หลัง $1}"; shift 2 ;;
    -e|--env-file)    ENV_FILE="${2:?ต้องระบุพาธไฟล์หลัง $1}"; shift 2 ;;
    -l|--lang)        PROMPT_LANG="${2:?ต้องระบุ th หรือ en}"; shift 2 ;;
    -p|--prompt)      CUSTOM_PROMPT="${2:?ต้องระบุข้อความคำสั่ง}"; shift 2 ;;
    -r|--max-rounds)  MAX_ROUNDS="${2:?ต้องระบุตัวเลขรอบ}"; shift 2 ;;
    --no-local)       INCLUDE_LOCAL=0; shift ;;
    --clean-only)     CLEAN_ONLY=1; shift ;;
    --dry-run)        DRY_RUN=1; shift ;;
    -h|--help)        usage; exit 0 ;;
    *) echo "พารามิเตอร์ไม่ถูกต้อง: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# --------------------- 3. โหลด .env และล็อก Non-Interactive ---------------------
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

export LANG="${LANG:-C.UTF-8}"
export LC_CTYPE="${LC_CTYPE:-C.UTF-8}"
export GIT_TERMINAL_PROMPT=0
export GH_PROMPT_DISABLED=1
export GIT_PAGER=cat
export PAGER=cat

# ค้นหาไฟล์ models.json อัตโนมัติหากไม่ได้ระบุพาธมา
if [[ -z "${MODELS_FILE}" ]]; then
  for candidate in \
    "./models.json" \
    "${HOME}/.config/opencode/models.json" \
    "${HOME}/.local/share/opencode/models.json" \
    "${HOME}/.config/opencode/opencode.json"; do
    if [[ -f "${candidate}" ]]; then
      MODELS_FILE="${candidate}"
      break
    fi
  done
fi

# ------------ 4. คัดกรอง Free Models + ล้าง Paid + สร้าง Config JSON -----------
QUEUE_DATA="$(python3 - "${MODELS_FILE}" "${INCLUDE_LOCAL}" <<'PY'
import json
import os
import shutil
import subprocess
import sys
import time

path = sys.argv[1]
include_local = sys.argv[2] == "1"

def is_strict_free(full_id: str) -> bool:
    s = full_id.strip().lower()
    if not s:
        return False
    return (
        s.endswith(":free")
        or s.endswith("-free")
        or s.endswith("/free")
        or s.startswith("openrouter-free/")
        or s == "opencode/big-pickle"
    )

def is_local_model(full_id: str) -> bool:
    s = full_id.strip().lower()
    if not s:
        return False
    return (
        s.startswith("local-llama/")
        or s.startswith("local-llama-small/")
        or s.startswith("zcoder-local/")
        or s.endswith("-local")
    )

def is_allowed(full_id: str) -> bool:
    return is_strict_free(full_id) or (include_local and is_local_model(full_id))

PRIORITY = [
    "opencode/deepseek-v4.1-flash-free",
    "opencode/glm-5.3-flash-free",
    "opencode/minimax-m3.1-flash-free",
    "opencode/mimo-v2.6-flash-free",
    "openrouter-free/nemotron-3-ultra-free",
    "openrouter-free/north-mini-code-free",
    "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
    "openrouter/cohere/north-mini-code:free",
    "kilo/nvidia/nemotron-3-ultra-550b-a55b:free",
    "kilo/cohere/north-mini-code:free",
    "zeaz/zeaz-free",
    "dmr/zeaz-free",
    "opencode/beam-free",
    "opencode/flint-40b-free",
    "opencode/longcat-2.5-free",
    "opencode/iceman-free",
    "opencode/big-pickle",
    "openrouter-free/gemma-4-31b-free",
    "openrouter/google/gemma-4-31b-it:free",
    "openrouter-free/gemma-4-26b-a4b-free",
    "openrouter/google/gemma-4-26b-a4b-it:free",
    "openrouter-free/flint-v1-free",
    "openrouter/recursive/flint-v1.0:free",
    "openrouter-free/ernie-5.5-flash-preview-free",
    "openrouter/baidu/ernie-5.5-flash-preview:free",
    "kilo/baidu/ernie-5.5-flash-preview:free",
    "opencode/nemotron-3.5-lightning-free",
    "openrouter-free/nemotron-3.5-lightning-free",
    "openrouter/nvidia/nemotron-3.5-lightning:free",
    "kilo/nvidia/nemotron-3.5-lightning:free",
    "openrouter-free/nemotron-3-nano-omni-free",
    "openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "kilo/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "openrouter-free/free-router",
    "openrouter/openrouter/free",
    "kilo/kilo-auto/free",
    "kilo/openrouter/free",
]

def sort_models(items):
    seen, ordered = set(), []
    for p in PRIORITY:
        if p in items and p not in seen and is_allowed(p):
            ordered.append(p)
            seen.add(p)
    cloud_rest = [m for m in items if m not in seen and is_strict_free(m)]
    local_rest = [m for m in items if m not in seen and include_local and is_local_model(m)]
    for m in cloud_rest + local_rest:
        if m not in seen:
            ordered.append(m)
            seen.add(m)
    return ordered

def atomic_write_json(target_path: str, payload) -> None:
    tmp_path = f"/tmp/opencode-clean-{os.getpid()}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as wf:
        json.dump(payload, wf, indent=2, ensure_ascii=False)
        wf.write("\n")
    shutil.move(tmp_path, target_path)

discovered = []

if path and os.path.isfile(path):
    # สำรองไฟล์เดิมไว้ที่ /tmp เพื่อไม่ให้เกิดไฟล์ขยะใน Git Repository
    bak_name = f"/tmp/{os.path.basename(path)}.{int(time.time())}.bak"
    shutil.copy2(path, bak_name)
    with open(path, "r", encoding="utf-8") as rf:
        raw = rf.read().strip()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            discovered = sort_models([x.strip() for x in data if isinstance(x, str) and is_allowed(x)])
            atomic_write_json(path, discovered)
        elif isinstance(data, dict):
            if "provider" in data and isinstance(data["provider"], dict):
                new_prov = {}
                for prov, pcfg in data["provider"].items():
                    if isinstance(pcfg, dict) and isinstance(pcfg.get("models"), dict):
                        fmods = {}
                        for mid, mval in pcfg["models"].items():
                            full = f"{prov}/{mid}"
                            if is_allowed(full):
                                fmods[mid] = mval
                                discovered.append(full)
                        if fmods:
                            cp = dict(pcfg)
                            cp["models"] = fmods
                            new_prov[prov] = cp
                discovered = sort_models(discovered)
                data["provider"] = new_prov
                if discovered:
                    data["model"] = discovered[0]
                    data["small_model"] = discovered[min(1, len(discovered) - 1)]
                atomic_write_json(path, data)
            elif "models" in data and isinstance(data["models"], list):
                pool = [x.strip() for x in data["models"] if isinstance(x, str)]
                if isinstance(data.get("local_fallback_models"), list):
                    pool.extend([x.strip() for x in data["local_fallback_models"] if isinstance(x, str)])
                discovered = sort_models([x for x in pool if is_allowed(x)])
                data["models"] = [m for m in discovered if not is_local_model(m)]
                if "local_fallback_models" in data:
                    data["local_fallback_models"] = [m for m in discovered if is_local_model(m)]
                if discovered:
                    data["default_model"] = discovered[0]
                    data["small_model"] = discovered[min(1, len(discovered) - 1)]
                atomic_write_json(path, data)
            else:
                kept = {k: v for k, v in data.items() if is_allowed(k)}
                discovered = sort_models(list(kept.keys()))
                atomic_write_json(path, {k: kept[k] for k in discovered})
    except json.JSONDecodeError:
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip() and is_allowed(ln)]
        discovered = sort_models(lines)
        atomic_write_json(path, {"models": discovered})

if not discovered:
    try:
        out = subprocess.check_output(["opencode", "models"], text=True, stderr=subprocess.DEVNULL)
        discovered = sort_models([ln.strip() for ln in out.splitlines() if is_allowed(ln)])
        if path:
            atomic_write_json(path, {"models": discovered})
    except Exception:
        discovered = sort_models(PRIORITY)

if not discovered:
    sys.exit(1)

small_candidates = [m for m in discovered if "glm-5.3-flash-free" in m or "free-router" in m or m.endswith("/free")]
small_model = small_candidates[0] if small_candidates else discovered[min(1, len(discovered) - 1)]
or_subs = [m.split("/", 1)[1] for m in discovered if m.startswith("openrouter/")]

for m in discovered:
    cfg = {
        "$schema": "https://opencode.ai/config.json",
        "model": m,
        "small_model": small_model,
        "permission": {"*": "allow"},
    }
    if m.startswith("openrouter/"):
        sub = m.split("/", 1)[1]
        fb = [x for x in or_subs if x != sub][:3]
        entry = {"id": sub, "name": sub, "tool_call": True}
        if fb:
            entry["options"] = {"models": fb}
        cfg["provider"] = {"openrouter": {"models": {sub: entry}}}
    print(f"{m}\t{json.dumps(cfg, ensure_ascii=False, separators=(',', ':'))}")
PY
)"

mapfile -t MODEL_QUEUE <<< "${QUEUE_DATA}"

if [[ "${#MODEL_QUEUE[@]}" -eq 0 || -z "${MODEL_QUEUE[0]}" ]]; then
  echo "ไม่พบโมเดลฟรีที่พร้อมใช้งาน กรุณาตรวจสอบไฟล์โมเดลหรือการเชื่อมต่อ Provider" >&2
  exit 1
fi

echo "=== [SSOT Clean Audit] คัดกรองเหลือเฉพาะ Free Models ทั้งหมด ${#MODEL_QUEUE[@]} รายการ ==="
if [[ -n "${MODELS_FILE}" ]]; then
  echo "=== อัปเดตไฟล์สะอาดแล้วที่: ${MODELS_FILE} (ไฟล์สำรองเก็บไว้ใน /tmp) ==="
fi

if [[ "${CLEAN_ONLY}" -eq 1 || "${DRY_RUN}" -eq 1 ]]; then
  for idx in "${!MODEL_QUEUE[@]}"; do
    IFS=$'\t' read -r m_id m_cfg <<< "${MODEL_QUEUE[$idx]}"
    printf "  [%02d] %s\n" "$((idx + 1))" "${m_id}"
    if [[ "${DRY_RUN}" -eq 1 && "${idx}" -eq 0 ]]; then
      echo "       Sample OPENCODE_CONFIG_CONTENT=${m_cfg}"
    fi
  done
  exit 0
fi

# ----------------- 5. แม่แบบคำสั่ง Master Prompt ในตัว (TH / EN) ----------------
if [[ -n "${CUSTOM_PROMPT}" ]]; then
  FINAL_PROMPT="${CUSTOM_PROMPT}"
  RESUME_PROMPT="ดำเนินการต่อจากสถานะล่าสุดจนงานเสร็จสมบูรณ์ไร้ข้อผิดพลาด"
elif [[ "${PROMPT_LANG}" == "en" ]]; then
  RESUME_PROMPT="Continue autonomously from the exact current repository state and complete all 5 phases with zero errors and zero warnings under all hard constraints."
  FINAL_PROMPT="$(cat <<'EOF_EN'
You are an Omnidisciplinary Principal Systems Architect, Staff Production Engineer, and Application Security Specialist. Operate with maximum analytical depth, end-to-end ownership, and zero-defect engineering rigor in a headless non-interactive shell (never launch editors, pagers, or interactive prompts; always pass explicit flags like -m, --title, --body, --no-edit).

HARD CONSTRAINTS (NON-NEGOTIABLE):
- NO NEW DIRECTORIES: Strictly DO NOT create any new folders or subdirectories anywhere in the repository. Place all edits and Final-Report.md exclusively within the existing directory structure.
- 100% COMPLETE IMPLEMENTATION: Deliver full, independent, production-ready implementations across the entire codebase with zero TODO, FIXME, stubs, dead code, or half-wired features.
- ENTERPRISE PRODUCTION STANDARDS: Enforce Clean Architecture, strict Type Safety, deterministic state handling, Robust Error Handling, and high-throughput Scalability.

EXECUTE ALL 5 PHASES AUTONOMOUSLY TO COMPLETION:
1. PHASE 1 (Deep Dive): Inspect the entire codebase, dependency graph, configs, and scripts to identify every missing implementation, broken integration, bottleneck, latent bug, warning, and security gap.
2. PHASE 2 (Implementation & Optimization): Complete, upgrade, and optimize every subsystem to 100% production readiness without creating new directories.
3. PHASE 3 (Zero-Error QA & AppSec Gate): Iterate until build, integration tests, linters, ruff, shellcheck, pytest, warning/TODO sweeps, and local defensive AppSec/OWASP verification all pass with 0 errors and 0 warnings.
4. PHASE 4 (Documentation & Final Report): Sync all existing documentation with the latest codebase state and generate a comprehensive Final-Report.md in the root directory covering executive readiness, changelog, benchmarks, and full validation matrix.
5. PHASE 5 (Four-Eyes Git & PR Workflow): Configure git credential helper to /home/cvsz/.config/gh/.git-credentials (and run gh auth setup-git), then:
   - Switch to cvsz (gh auth switch -u cvsz), verify via gh auth status, create upgrade branch, GPG-sign commit verified files (git commit -S -m "..."), push, and open PR (gh pr create --title "..." --body "...").
   - Switch to policedbc (gh auth switch -u policedbc), audit PR diff and checks (gh pr diff / gh pr checks), and approve (gh pr review --approve --body "...").
   - Switch back to cvsz (gh auth switch -u cvsz), verify green checks, merge cleanly (gh pr merge --merge --delete-branch), sync local default branch, and report final commit SHA and PR URL.
EOF_EN
)"
else
  RESUME_PROMPT="ดำเนินการต่อจากสถานะล่าสุดในโปรเจกต์ให้ครบทั้ง 5 ขั้นตอนตามข้อบังคับเดิมจนเสร็จสมบูรณ์ไร้ข้อผิดพลาด"
  FINAL_PROMPT="$(cat <<'EOF_TH'
คุณคือหัวหน้าสถาปนิกซอฟต์แวร์ วิศวกรระบบอาวุโส และผู้เชี่ยวชาญด้านความมั่นคงปลอดภัยของระบบที่รอบรู้ลึกซึ้งครบทุกสาขาวิชา จงปฏิบัติงานด้วยความละเอียดลุ่มลึกสูงสุด วิเคราะห์เจาะลึกถึงแก่นของรหัสต้นฉบับทั้งหมด รับผิดชอบการพัฒนาตั้งแต่ต้นจนจบด้วยตนเองอย่างเบ็ดเสร็จ และยึดถือมาตรฐานวิศวกรรมที่ไร้ข้อผิดพลาดภายใต้สภาพแวดล้อมแบบไร้หน้าต่างโต้ตอบ (ห้ามเรียกโปรแกรมแก้ไขข้อความหรือคำสั่งที่รอรับค่าจากผู้ใช้ ให้ระบุพารามิเตอร์ข้อความเช่น -m, --title, --body, --no-edit เสมอ)

จงดำเนินงานตามแผนปฏิบัติการ 5 ขั้นตอนต่อไปนี้อย่างต่อเนื่องจนเสร็จสมบูรณ์ครบถ้วน โดยไม่ต้องหยุดรอคำสั่งระหว่างทาง:

### ข้อบังคับเด็ดขาด (ห้ามละเมิดทุกกรณี)
- ห้ามสร้างโฟลเดอร์ใหม่โดยเด็ดขาด: ห้ามสร้างไดเรกทอรีหรือโฟลเดอร์ย่อยใหม่ในทุกส่วนของโครงการ ให้พัฒนา แก้ไข ปรับปรุงโครงสร้าง และจัดวางไฟล์ทั้งหมด (รวมถึงไฟล์รายงาน Final-Report.md) ไว้ภายในโครงสร้างโฟลเดอร์เดิมที่มีอยู่แล้วเท่านั้น
- พัฒนาและเติมเต็มทุกระบบให้สมบูรณ์ 100%: ลงมือเขียน แก้ไข อัปเกรด และเชื่อมต่อทุกส่วนงานให้ทำงานได้จริงอย่างสมบูรณ์ครบถ้วน ห้ามทิ้งงานค้าง ข้อความระบุงานที่ยังไม่ได้ทำ โค้ดจำลองชั่วคราว โค้ดที่ไม่ได้ใช้งาน หรือฟังก์ชันที่เขียนไว้เพียงบางส่วนโดยเด็ดขาด
- ยึดมาตรฐานระดับองค์กรที่พร้อมใช้งานจริง: ออกแบบและเขียนโค้ดตามหลักสถาปัตยกรรมที่สะอาดแยกส่วนชัดเจน กำหนดและตรวจสอบชนิดข้อมูลอย่างเคร่งครัดรัดกุม จัดการข้อผิดพลาดอย่างครอบคลุมทนทานต่อปัญหาหน้างาน รองรับการทำงานพร้อมกันและขยายขีดความสามารถในการประมวลผลได้ในระดับสูงสุด

### ขั้นตอนที่ 1: เจาะลึกโครงสร้างรหัสต้นฉบับและวิเคราะห์ส่วนที่ขาดหาย
1. ตรวจสอบโครงสร้างไฟล์ทั้งหมด ความสัมพันธ์ระหว่างโมดูล ไฟล์ตั้งค่าระบบ สคริปต์การทำงาน และสถาปัตยกรรมขณะรันจริงอย่างละเอียดตั้งแต่พื้นฐาน
2. ค้นหาและรวบรวมส่วนที่ยังพัฒนาไม่เสร็จ การเชื่อมต่อที่ขาดตอน คอขวดด้านประสิทธิภาพ จุดบกพร่องแฝง สถานะข้อมูลที่ไม่ถูกต้อง รูปแบบโค้ดที่ล้าสมัย ช่องโหว่ด้านความปลอดภัย และรายการงานค้างทั้งหมดในทุกระบบย่อย

### ขั้นตอนที่ 2: พัฒนา อัปเกรด และปรับแต่งประสิทธิภาพสูงสุดครบวงจร
1. แก้ไข อัปเกรด และเติมเต็มทุกโมดูลและทุกระบบย่อยให้ทำงานประสานกันได้อย่างสมบูรณ์ 100% พร้อมใช้งานจริงในระดับองค์กร โดยไม่สร้างโฟลเดอร์ใหม่
2. ปรับแต่งประสิทธิภาพในจุดสำคัญทั้งหมด ทั้งความเร็วในการประมวลผล การทำงานแบบขนานและรับส่งข้อมูล การจัดการหน่วยความจำ การสืบค้นฐานข้อมูลและสถานะระบบ ตลอดจนความเร็วในการประกอบสร้างระบบ
3. ยกระดับความมั่นคงแข็งแรงในทุกจุดเชื่อมต่อ ด้วยการตรวจสอบความถูกต้องของข้อมูลขาเข้าอย่างรัดกุม การฟื้นฟูระบบเมื่อเกิดเหตุขัดข้อง การบันทึกประวัติการทำงานอย่างเป็นระบบ และการป้องกันการประมวลผลซ้ำซ้อน

### ขั้นตอนที่ 3: การตรวจสอบความถูกต้อง ทดสอบระบบ และตรวจสอบความปลอดภัย (ต้องไร้ข้อผิดพลาด 100%)
ดำเนินการตรวจสอบและแก้ไขซ้ำจนกว่าทุกหัวข้อจะผ่านการทดสอบทั้งหมดโดยไม่มีข้อผิดพลาดและไม่มีคำเตือนใดๆ หลงเหลือแม้แต่รายการเดียว:
1. การตรวจสอบคุณภาพโค้ดและไวยากรณ์: รันเครื่องมือตรวจสอบมาตรฐานโค้ด รูปแบบการจัดวาง ชนิดข้อมูล และสคริปต์คำสั่งทั้งหมด รวมถึง ruff และ shellcheck ให้ผ่านทุกไฟล์
2. การประกอบสร้างและทดสอบการเชื่อมต่อ: ทดสอบประกอบสร้างระบบทั้งหมด และตรวจสอบความถูกต้องของการเชื่อมต่อระหว่างบริการ โมดูล และตัวแปรสภาพแวดล้อมทุกจุด
3. การรันชุดทดสอบอัตโนมัติ: รัน pytest และชุดทดสอบทั้งหมดของโครงการ (ทั้งการทดสอบระดับหน่วยย่อย การทดสอบคุณสมบัติ และการทดสอบการเชื่อมต่อรวม) พร้อมเขียนกรณีทดสอบเพิ่มเติมในไฟล์ทดสอบเดิมให้ครอบคลุมส่วนที่พัฒนาใหม่และกรณีขอบเขตทั้งหมด
4. การกวาดล้างจุดบกพร่องและคำเตือน: กำจัดคำเตือนเรื่องคำสั่งล้าสมัย การตั้งค่าที่ไม่ถูกต้อง ข้อผิดพลาดที่ไม่ได้ดักจับ ปัญหาการแย่งชิงทรัพยากร และข้อความงานค้างทั้งหมดให้เป็นศูนย์
5. การทดสอบเจาะระบบเชิงป้องกันและตรวจสอบความมั่นคงปลอดภัย: ตรวจสอบช่องโหว่ด้านความปลอดภัยของซอฟต์แวร์ในสภาพแวดล้อมภายในอย่างรอบด้าน ทั้งการตรวจสอบสิทธิ์และการเข้าถึง การป้องกันการแทรกคำสั่งแปลกปลอม ขอบเขตการรับข้อมูล การรั่วไหลของข้อมูลความลับ และช่องโหว่ของชุดคำสั่งภายนอก พร้อมแก้ไขทุกจุดที่พบทันที

### ขั้นตอนที่ 4: ปรับปรุงเอกสารทั้งหมดและสร้างรายงานสรุปฉบับสมบูรณ์
1. ปรับปรุงเอกสารโครงการทั้งหมดให้เป็นปัจจุบัน: ตรวจสอบและอัปเดตไฟล์เอกสารทุกฉบับที่มีอยู่ในโครงการ ให้สอดคล้องกับรหัสต้นฉบับและสถาปัตยกรรมล่าสุดอย่างถูกต้องตรงกัน 100% ทั้งผังการทำงาน คำสั่งใช้งาน ข้อกำหนดการเชื่อมต่อ และตัวแปรตั้งค่า
2. สร้างไฟล์รายงาน Final-Report.md: สร้างรายงานสรุปผลทั้งระบบอย่างละเอียดไว้ที่ไดเรกทอรีหลักของโครงการ โดยระบุเนื้อหาครอบคลุม:
   - บทสรุปผู้บริหารยืนยันความพร้อมใช้งานจริงระดับองค์กรที่ผ่านการตรวจสอบครบถ้วน
   - รายการเปลี่ยนแปลงทั้งหมด ทั้งฟีเจอร์ที่เติมเต็ม จุดบกพร่องที่แก้ไข และการอัปเกรดสถาปัตยกรรม
   - ผลลัพธ์การปรับแต่งประสิทธิภาพและความสามารถในการรองรับการขยายตัวของระบบ
   - ตารางสรุปผลการตรวจสอบทุกมิติ (ผลการประกอบสร้างระบบ, ruff, shellcheck, pytest, การทดสอบการเชื่อมต่อ และผลการตรวจสอบความมั่นคงปลอดภัย)

### ขั้นตอนที่ 5: กระบวนการบันทึกงาน ตรวจสอบอิสระ และรวมรหัสต้นฉบับแบบแยกบทบาท
ใช้ไฟล์ข้อมูลรับรองสิทธิ์จาก /home/cvsz/.config/gh/.git-credentials สำหรับจัดการสิทธิ์การใช้งาน (git config credential.helper "store --file=/home/cvsz/.config/gh/.git-credentials" และ gh auth setup-git ตามความเหมาะสม) และดำเนินขั้นตอนตามลำดับนี้อย่างเคร่งครัด:
1. ลงนามบันทึกการแก้ไขและเปิดคำขอรวมโค้ด (บัญชี cvsz):
   - รันคำสั่ง gh auth switch -u cvsz และตรวจสอบสถานะบัญชีที่ใช้งานด้วย gh auth status
   - สร้างหรือสลับไปยังสาขาสำหรับการปรับปรุงจากสาขาหลักล่าสุด เลือกเฉพาะไฟล์ที่ผ่านการตรวจสอบแล้ว (ระมัดระวังไม่ให้นำไฟล์ความลับหรือไฟล์ขยะเข้าสู่ระบบ) บันทึกการเปลี่ยนแปลงพร้อมลงลายเซ็นเข้ารหัสด้วย git commit -S -m "..." ส่งขึ้นแม่ข่าย และเปิดคำขอรวมโค้ดพร้อมอธิบายรายละเอียดอย่างครบถ้วนผ่าน gh pr create --title "..." --body "..."
2. ตรวจสอบอิสระ ตรวจทานโค้ด และอนุมัติ (บัญชี policedbc):
   - รันคำสั่ง gh auth switch -u policedbc และตรวจสอบสถานะบัญชีที่ใช้งาน
   - ดำเนินการตรวจสอบส่วนต่างของรหัสต้นฉบับ สถาปัตยกรรม ผลลัพธ์ชุดทดสอบ และความปลอดภัยของคำขอรวมโค้ดอย่างละเอียด (gh pr diff และ gh pr checks)
   - บันทึกความเห็นสรุปผลการตรวจสอบอย่างเป็นทางการ และกดอนุมัติผ่านคำสั่ง gh pr review --approve --body "..."
3. รวมรหัสต้นฉบับเข้าสู่สาขาหลัก (บัญชี cvsz):
   - รันคำสั่ง gh auth switch -u cvsz และตรวจสอบสถานะบัญชีที่ใช้งาน
   - ยืนยันว่าสถานะการทดสอบและการอนุมัติผ่านครบถ้วนทุกเงื่อนไข จากนั้นรวมรหัสต้นฉบับเข้าสู่สาขาหลักด้วย gh pr merge --merge --delete-branch ปรับข้อมูลสาขาหลักในเครื่องให้เป็นปัจจุบัน และรายงานรหัสอ้างอิงการบันทึกสุดท้ายพร้อมลิงก์ของคำขอรวมโค้ด
EOF_TH
)"
fi

# ------------- 6. Auto-Switch & Session-Resume Retry Engine --------------
STARTED_SESSION=0
PREV_PROVIDER=""

for ((round = 1; round <= MAX_ROUNDS; round++)); do
  for idx in "${!MODEL_QUEUE[@]}"; do
    IFS=$'\t' read -r TARGET_MODEL TARGET_CFG <<< "${MODEL_QUEUE[$idx]}"
    CURR_PROVIDER="${TARGET_MODEL%%/*}"
    export OPENCODE_CONFIG_CONTENT="${TARGET_CFG}"

    echo ">>> [Round ${round}/${MAX_ROUNDS} | Free $((idx + 1))/${#MODEL_QUEUE[@]}] กำลังรันด้วยโมเดล: ${TARGET_MODEL}"

    if [[ "${STARTED_SESSION}" -eq 0 ]]; then
      STARTED_SESSION=1
      if opencode run --agent build -m "${TARGET_MODEL}" "${FINAL_PROMPT}"; then
        echo ">>> [SUCCESS] ดำเนินการครบทุกขั้นตอนสำเร็จด้วยโมเดล ${TARGET_MODEL}"
        exit 0
      fi
    else
      # หากสลับภายใน Provider เดิมให้พักรอรอบโควตานานขึ้น หากข้ามค่ายสลับต่อได้ไวทันที
      if [[ "${CURR_PROVIDER}" == "${PREV_PROVIDER}" ]]; then
        sleep "$((6 * round))"
      else
        sleep 2
      fi
      if opencode run -c --agent build -m "${TARGET_MODEL}" "${RESUME_PROMPT}"; then
        echo ">>> [SUCCESS] ดำเนินการต่อจนเสร็จสมบูรณ์ด้วยโมเดล ${TARGET_MODEL}"
        exit 0
      fi
    fi

    PREV_PROVIDER="${CURR_PROVIDER}"
    echo ">>> [Auto-Switch] โมเดล ${TARGET_MODEL} ติดข้อจำกัดหรือหยุดกลางคัน กำลังสลับไปยังโมเดลฟรีลำดับถัดไป..." >&2
  done
done

echo ">>> [ABORT] วนครบทุกโมเดลฟรีทั้ง ${MAX_ROUNDS} รอบแล้วยังไม่จบงาน (รันซ้ำได้ทันทีเพื่อทำต่อจากเซสชันเดิม)" >&2
exit 1
