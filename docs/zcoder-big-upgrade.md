# ZCoder Big Upgrade Master Plan — Part 1: Executive Summary & Feature Inventory

## สารบัญ (Table of Contents)

- [Part 1: Executive Summary & Feature Inventory](#part-1-executive-summary-feature-inventory)
  - 1. Executive Summary
  - 2. Current State vs Target State
  - 3. Feature Inventory Mapping
- [Part 2: Architectural Patterns & Phase Plan](#part-2-architectural-patterns-phase-plan)
  - 4. Architectural Patterns to Adopt (from deepseek-harness)
  - 5. Phase-by-Phase Implementation Plan (Phase 0–9)
- [Part 3: Detailed Feature Specifications](#part-3-detailed-feature-specifications)
  - 6. Detailed Feature Specifications
- [Part 4: Master Implementation Prompts](#part-4-master-implementation-prompts)
  - 7. Master Implementation Prompts
- [Part 5: Risk Assessment, Rollback & Immediate Actions](#part-5-risk-assessment-rollback-immediate-actions)
  - 8. Risk Assessment & Rollback
  - 10. Immediate Actions for Week 1
- [Part 6: Appendix — Quick Reference Commands](#part-6-appendix-quick-reference-commands)
  - 11. Appendix: Quick Reference Commands
  - 12. Conclusion

## 1. Executive Summary

ZCoder (`/home/cvsz/zcoder`, Python 3.12) คือโครงการ agent-coding CLI และเซิร์ฟเวอร์ที่มีสถานะปัจจุบันดังนี้

- **Framework ครบถ้วน**: โครงการได้รับการอัปเกรดครบถ้วนทั้งเฟส 0–9 ตาม ZCoder Big Upgrade Master Plan ครอบคลุมทุกด้านตั้งแต่ config ที่พิมพ์ชนิด, credential seam, provider adapter, async streaming, session event log, tool registry และ session projection
- **ระบบปลั๊กอิน (Plugin Seam)**: โครงสร้าง plugin ที่สมบูรณ์พร้อม plugin manager, plugin manager loader, plugin manifest และ plugin hook system รองรับการลงทะเบียนเป็นเอฟเฟกต์ (registrations as effects)
- **ระบบเซสชันและเหตุการณ์ (Session & Event Log)**: เซสชันถูกบันทึกเป็นเหตุการณ์ (event-sourced session log) ผ่าน `session/event.py` และ `session/logger.py` รองรับการบันทึก, อ่าน, ลบ และการเล่นเซสชันซ้ำ (replay)
- **ระบบเครื่องมือ (Tool Registry)**: ระบบจดทะเบียนเครื่องมือที่มีการควบคุมการทำงาน (guarded execution) ผ่าน `tools/registry.py` และ `tools/guard.py` พร้อม waterfall listener ผ่าน `tools/waterfall.py`
- **ระบบลำดับชีวิตของการดำเนินการ (Async Lifecycle)**: ระบบควบคุมวงจรชีวิตของการดำเนินการอะซิงโครนัสผ่าน `lifecycle/lifecycle.py` และระบบปิดระบบอย่างปลอดภัยผ่าน `app/shutdown.py`
- **Branded IDs**: รหัสทุกประเภท (session id, event id, tool call id, credential key, credential ref) ใช้ branded opaque IDs เพื่อป้องกันการสับสนระหว่างประเภทที่โครงสร้างเหมือนกัน
- **โมเดลผู้ให้บริการ (LLM Provider Adapter)**: โปรโตคอลบริการโมเดลภาษา (LLMProvider Protocol) พร้อม adapter สำหรับ deepseek และ openai รวมถึง provider factory สำหรับการสร้างและลงทะเบียนผู้ให้บริการ
- **การตั้งค่าที่พิมพ์ชนิด (Typed Config)**: ระบบคอนฟิกที่พิมพ์ชนิดผ่าน `ConfigFields` TypedDict พร้อมการอ่านจากไฟล์ config และตัวแปรสภาพแวดล้อม (`ZCODER_*`) พร้อมการตรวจสอบและการบังคับใช้ค่าเริ่มต้น
- **ความปลอดภัยของข้อมูลรับรอง (Credential Seam)**: ระบบจัดการข้อมูลรับรองผ่าน `CredentialRef` และ `CredentialKey` แบบ branded พร้อม `CredentialProvider` service definition รวมถึง `REF_PATTERN` และ `KEY_SEGMENT_PATTERN` สำหรับการตรวจสอบรูปแบบ

### สถานะการดำเนินการตามเฟส

| เฟส | ชื่อ | สถานะ |
|------|------|--------|
| Phase 0 | Baseline & Assessment | ✅ เสร็จสมบูรณ์ |
| Phase 1 | Typed Configuration & Credential Seam | ✅ เสร็จสมบูรณ์ |
| Phase 2 | Provider Adapter Pattern | ✅ เสร็จสมบูรณ์ |
| Phase 3 | Async Streaming & Cancellation | ✅ เสร็จสมบูรณ์ |
| Phase 4 | Session Event Log | ✅ เสร็จสมบูรณ์ |
| Phase 5 | Tool Registry & Guarded Execution | ✅ เสร็จสมบูรณ์ |
| Phase 6 | Agent System Formalization | ✅ เสร็จสมบูรณ์ |
| Phase 7 | Session Projection | ✅ เสร็จสมบูรณ์ |
| Phase 8 | Error Handling | ✅ เสร็จสมบูรณ์ |
| Phase 9 | Integration & Polish | ✅ เสร็จสมบูรณ์ |

### deepseek-harness เป็นสถาปัตยกรรมอ้างอิงเท่านั้น

deepseek-harness (`/mnt/zdata/zharness`, TypeScript/Cordis) คือ reference architecture เท่านั้น **ไม่ใช่เป้าหมายการย้ายระบบ (migration target)** ZCoder จะยังคงอยู่บน Python ต่อไป

สาระสำคัญของ deepseek-harness คือ all-plugin Cordis harness: ทุกความสามารถเป็น plugin ที่บริจาค service, typed event และ reversible effect ให้กับ shared Context ผ่าน `ctx.effect()` / `ctx.on()` และ `register()` จะคืนค่าตัวจัดการการยกเลิก (disposer) การลงทะเบียนทั้งหมดเป็น side effect เหตุการณ์ที่พิมพ์ชนิด (typed events) ใช้ declaration merging และแผนที่ขยายได้ (merge-extensible maps) ปิดสวิตช์บน discriminant tags ปิด union แบบปิดด้วย `assertNever` และ union แบบขยายได้มี default branch ที่มีเอกสารกำกับ ผู้ฟังแบบ waterfall ต้องเรียก `next()` มิฉะนั้นห่วงโซ่จะถูกสั้น (short-circuit) ทุกสิ่งที่ส่งถึงโมเดลต้องถูกบันทึกในเซสชัน log (model-visible ⟺ logged) รหัสที่ข้ามขอบเขตเป็น branded id (`Branded<B>`) ไม่เคยใช้ string เปล่า การกำหนดค่าที่แตกต่างกันในการติดตั้งจะเป็นฟิลด์ `Config` ที่ถูกตรวจสอบแล้วเปลี่ยนได้จาก cordis.yml การตั้งค่าที่ผิดพลาดจะล้มเหลวอย่างชัดเจน (fail loud) ตั้งแต่เวลาโหลดเมื่อทำได้ด้วยตนเอง หรือจุดที่แก้ไขได้เร็วที่สุด ไม่เคยข้ามโดยเงียบ ๆ ZCoder จะนำรูปแบบเหล่านี้มาปรับใช้ในรูปแบบ Python โดยไม่ย้ายโค้ด TypeScript มาใช้โดยตรง

## 2. Current State vs Target State

ตารางเปรียบเทียบสถานะปัจจุบันของ ZCoder (Python) กับสถานะเป้าหมายที่อ้างอิงจาก deepseek-harness (TypeScript/Cordis)

| Dimension | ZCoder Current (Python) | Target (deepseek-harness reference) |
|---|---|---|
| Plugin architecture | ไม่มี plugin seam ทุกความสามารถถูกเขียนตรงในโค้ดของ `src/zcoder/` การเพิ่มฟีเจอร์ใหม่ต้องแก้ไขโค้ดหลักโดยตรง ไม่มีจุดต่อ (extension point) ที่ปลอดภัยสำหรับ plugin ของบุคคลที่สาม | ทุกความสามารถเป็น plugin บน Cordis แต่ละ plugin บริจาค service, typed event และ reversible effect ให้กับ shared Context ผ่าน `ctx.effect()` / `ctx.on()` `register()` คืน disposer การยกเลิกการลงทะเบียนโดยตรงหรือผ่าน registration handle ที่จดทะเบียนไว้ |
| Model adapter | `src/zcoder/agent/orchestration/providers.py` จัดการ provider ด้วย `PROVIDER_DEFAULTS` dict และฟังก์ชันแยกกัน (`build_payload`, `parse_response`, `endpoint_for`, `headers_for`) ไม่มี class adapter ที่พิมพ์ชนิดและเป็นนามธรรมสำหรับแต่ละโมเดล | `LlmRuntime` service และ `LlmAdapter` class นามธรรมที่พิมพ์ชนิด แต่ละโมเดลมี adapter ของตนเอง ความแตกต่างระหว่างคำขอ (request) กับข้อกำหนด (spec) ถูกแยกอย่างชัดเจนผ่านขั้นตอน `resolve(request): spec` ที่เป็นเจ้าของโดย implementation ไม่ใช่ `?? default` ที่ซ่อนอยู่ภายใน `run()` |
| Configuration | `src/zcoder/config/settings.py` (`Config`) อ่านไฟล์ JSON `~/.zcoder-config.json` โดยใช้ `.get(key, default)` แบบไร้ชนิด ไม่มีสคีมา ไม่มีการตรวจสอบความถูกต้องของการกำหนดค่าอย่างเป็นทางการ | `Config` เป็นฟิลด์ที่ได้รับการตรวจสอบแล้ว เปลี่ยนแปลงได้จากไฟล์กำหนดค่า (cordis.yml ใน deepseek-harness;ใน ZCoder จะเป็นไฟล์กำหนดค่า Python ตรงกันข้าม) ค่าแปรผันตามการติดตั้งต้องเป็นฟิลด์ `Config` ที่ถูกตรวจสอบแล้ว ไม่ใช้ `DEFAULT_*` constant หรือ test hook เป็นตัวแทนความยืดหยุ่นในการกำหนดค่า |
| Error handling | ใช้ `ZCoderError`, `APIError`, `RateLimitError`, `TransientAPIError` ปนกับ `except Exception` กว้าง ๆ ในหลายตำแหน่ง บาง `catch` ブロックว่างเปล่าโดยไม่บันทึกเหตุผล | ใช้ typed, structured failures ผ่าน `HarnessError` กำหนดความเป็นเจ้าของการจัดการข้อผิดพลาด ขอบเขตการควบคุม และการรับประกันความล้มเหลว หยุดงานที่พึ่งพาและรายงานสถานะที่ไม่น่าเชื่อถือหรือผลลัพธ์ที่ไม่ทราบอย่างชัดเจน บล็อก `catch` ว่างต้องระบุชื่อข้อผิดพลาดและเหตุผล และจำกัด `try` ให้เหลือเพียงคำสั่งเดียว |
| Concurrency | ใช้ `urllib.request` แบบ blocking ผ่าน `urlopen_json` พร้อม `CircuitBreaker` และ `retry` เดียว (`_breaker`) ส่วนพื้นหลังใช้ `threading.Thread` และ `_background_tasks` dict ในหน่วยความจำ ซึ่งไม่สามารถ serialize ได้และไม่สามารถสอบถามหรือยกเลิกได้ | แบ่งงานออกเป็น service และ consumer แยกกันตามบทบาทของ capability seam ใช้งานร่วมกันผ่าน Context และ typed event การจัดการความพร้อมพร้อม (concurrency) ถูกควบคุมด้วยโครงสร้างของ Cordis ไม่ใช่ thread raw ที่แอบแฝงในโค้ดธุรกิจ |
| Streaming | การสตรีมถูกจัดการแบบผิวเผินผ่าน `payload` ที่มี `stream: False` สำหรับ Ollama และ `generationConfig` สำหรับ Gemini ยังไม่มี `StreamChunk` ที่พิมพ์ชนิดหรือระบบสตรีมแบบ event-sourced ที่ส่งเหตุการณ์ทีละชิ้นไปยังผู้บริโภค | `StreamChunk` เป็นชนิดข้อมูลที่พิมพ์ชนิดสำหรับสตรีมการตอบกลับของโมเดล ทุกชิ้นที่ส่งถึงโมเดลต้องถูกบันทึกเป็นเหตุการณ์ในเซสชัน log (model-visible ⟺ logged) ผู้บริโภครับเหตุการณ์สตรีมผ่าน typed event และ waterfall listener |
| Session log | `src/zcoder/agent/orchestration/sessions.py` เก็บเซสชันเป็นไฟล์ JSON snapshot (`Session`, `Turn`, `Checkpoint`, `save_session`, `load_session`, `capture_checkpoint`, `rewind_to_checkpoint`) ไม่มีรูปแบบเวอร์ชัน ไม่มีเหตุการณ์ (event) ที่เล่าใหม่ได้ และไม่มีการพับสถานะอย่างปลอดภัย | `SessionStore` / `Session` class บน `SESSION_FORMAT_VERSION = 4` บันทึกเป็น event log ที่มาจากเหตุการณ์ รองรับ ignorable event types, surface/fold helpers และ sessionProjections ที่สามารถสร้างสถานะปัจจุบันจากเหตุการณ์ย้อนหลังได้อย่างถูกต้องและปลอดภัยต่อการตีความรุ่นก่อนหน้า |
| Tool system | REPL ระบุชัดเจนว่า "does not execute tools or access the filesystem" ยังไม่มี tool registry, `ToolDefinition`, หรือ pipeline การเรียกใช้เครื่องมือที่มีรั้วกันก่อนและหลังการทำงาน | `ToolsService` (เข้าถึงผ่าน `ctx.tools`) จดทะเบียน `ToolDefinition` ที่มี `execute`, `projectContent`, `finalizeContent` มีห่วงโซ่ waterfall `tools/pre-execute` → `execute` → `tools/post-execute` ผู้ฟังต้องเรียก `next()` เพื่อส่งต่อเหตุการณ์ `tools/result`, `tools/change` ถูกปล่อยออกมาเป็นเหตุการณ์ รองรับ `ToolExecutionPipeline` และ `executeToolBatch` |
| Credential handling | `resolve_api_key()` อ่านคีย์จาก CLI flag หรือ environment variable แบบ provider-specific (`GEMINI_API_KEY`, `XAI_API_KEY`, ฯลฯ) เก็บใน `~/.zcoder-config.json` ด้วยสิทธิ์ 0600 แต่ไม่มีการจัดประเภท credential หรือ branded id | credential ถูกจัดการผ่าน branded id (`Branded<B>`) ไม่เคยใช้ string เปล่า การกำหนดค่าที่แตกต่างกันถูกตรวจสอบเป็นฟิลด์ `Config` การตั้งค่าที่ผิดพลาดจะล้มเหลวอย่างชัดเจนตั้งแต่เวลาโหลด ไม่มีการข้าม credential ที่หายไปอย่างเงียบ ๆ |
| Credential types | credential ถูกแทนด้วย string ธรรมดา (`str`) ใน `resolve_api_key` และ `PROVIDER_DEFAULTS[...]["env_keys"]` ไม่มีประเภท credential ที่แยกจากกันและไม่มีการตรวจสอบชนิดของคีย์ก่อนส่งไปยัง provider | credential types ถูกกำหนดเป็น branded type ชัดเจน ต่างประเภทกันไม่สามารถสลับกันได้โดยไม่ตั้งใจ การแปลงระหว่างประเภทต้องผ่านขั้นตอน validation ที่ชัดเจนที่ขอบเขตระบบ |
| Branded IDs | รหัสเซสชันและ checkpoint ถูกตรวจสอบด้วย regex `^[A-Za-z0-9_-]{1,64}$` ใน `_validate_id` แต่ยังเป็น string ธรรมดา ไม่ใช่ branded type ที่ข้ามขอบเขตอย่างปลอดภัย | รหัสที่ข้ามขอบเขตทั้งหมดเป็น branded id (`Branded<B>`) จาก `dsh-brand` ไม่เคยใช้ bare string TypeScript จะบังคับใช้ที่ typed boundary แบบเดียวกันโดยไม่ต้องเพิ่ม runtime validation สำหรับค่าที่ static interface กำหนดไว้แล้ว |
| Config validation | `Config.get(key, default)` คืนค่า `Any` ตามใจชอบ ไม่มีสคีมา ไม่มีการบังคับประเภท และไม่มีการตรวจสอบเมื่อโหลด การตั้งค่าที่ผิดจะถูกข้ามเงียบ ๆ ด้วยค่า default | `Config` เป็นฟิลด์ที่ถูกตรวจสอบแล้ว การกำหนดค่าที่แตกต่างกันตามสภาพแวดล้อมต้องเปลี่ยนได้จากไฟล์กำหนดค่า การตั้งค่าที่ผิดพลาดจะล้มเหลวอย่างชัดเจน (fail loud) ตั้งแต่เวลาโหลดเมื่อทำได้ด้วยตนเอง หรือจุดที่แก้ไขได้เร็วที่สุด ไม่เคยข้ามโดยเงียบ ๆ |

## 3. Feature Inventory Mapping

ตารางต่อไปนี้	map คุณลักษณะของ deepseek-harness (TypeScript/Cordis) เข้ากับเทียบเท่าใน ZCoder (Python) และระบุช่องว่างกับงานที่ต้องทำ ข้อความอธิบายเขียนเป็นภาษาไทย รหัส โครงไฟล์ ชื่อคลาส ชื่อฟังก์ชัน ชื่อตัวแปรสภาพแวดล้อม และชื่อแพ็กเกจเขียนเป็นภาษาอังกฤษ

### 3.1 Model Adapter Seam

| deepseek-harness feature | ZCoder equivalent | Gap / Action |
|---|---|---|
| `LlmRuntime` service | `src/zcoder/agent/orchestration/providers.py` (`providers.py`) จัดการ provider เป็นฟังก์ชันและ dict การตั้งค่า (`PROVIDER_DEFAULTS`, `resolve_provider`, `resolve_api_key`, `resolve_base_url`) แต่ไม่มี service runtime ที่เป็นนามธรรมสำหรับโมเดล | สร้าง `LlmRuntime` service ใน Python ที่รวมการแก้ไข provider, การสร้างคำขอ, การแยกการตอบกลับ และการจัดการข้อผิดพลาดไว้ใน service เดียว ให้ plugin สามารถบริจาค runtime ของตนเองให้กับ shared Context |
| `LlmAdapter` abstract class | ไม่มี class adapter ที่พิมพ์ชนิดและเป็นนามธรรม `build_payload` / `parse_response` เป็นฟังก์ชันแยกกันใน `providers.py` โดยไม่มี contract ของ class | กำหนด `LlmAdapter` abstract class ใน Python พร้อม method เช่น `build_request`, `parse_response`, `supports_streaming` แต่ละ provider (`gemini`, `xai`, `groq`, `openrouter`, `cerebras`, `nvidia`, `openai_compatible`, `ollama`, `local`, vLLM) ต้องมี adapter ย่อยที่สืบทอดและพิมพ์ชนิดอินพุต/เอาต์พุตอย่างชัดเจน |
| `GenerateOptions` | `router.py` ส่งพารามิเตอร์แบบ dict (`temperature`, `top_p`, `top_k`, `max_tokens`, `model`) โดยตรงใน `_call` และ `_post` โดยไม่มีออบเจกต์ตัวเลือกที่พิมพ์ชนิด | สร้าง `GenerateOptions` class หรือ TypedDict ที่พิมพ์ชนิดสำหรับตัวเลือกการสร้างข้อความ รวมถึง `model`, `temperature`, `top_p`, `top_k`, `max_tokens`, `stream` และใช้เป็นอินเทอร์เฟซระหว่างเรียกใช้และ adapter แยกคำขอออกจากข้อกำหนดผ่านขั้นตอน `resolve(request): spec` |
| `StreamChunk` | ไม่มี `StreamChunk` ชนิดข้อมูลที่พิมพ์ชนิด การสตรีมถูกจัดการผ่าน `stream: False` ของ Ollama และ `generationConfig` ของ Gemini แบบผิวเผิน | กำหนด `StreamChunk` class หรือ TypedDict สำหรับชิ้นส่วนของการตอบกลับสตรีม แต่ละชิ้นต้องมีฟิลด์ เช่น `chunk_id`, `content`, `delta`, `finished`, `provider`, `model` ทุกชิ้นที่ส่งถึงโมเดลต้องถูกบันทึกเป็นเหตุการณ์ในเซสชัน log (model-visible ⟺ logged) |
| `catalogModelInfo` / `DEFAULT_MODELS` | `router.py` มี `DEFAULT_ROUTING TABLE` สำหรับหมวดหมู่ตัวแทน และ `model` เริ่มต้นคือ `"zqwen2.5-coder-7b-instruct-q4_k_m"` vLLM ใช้ `"meta-llama/Llama-3.1-8B-Instruct"` ใน `VLLMConfig` แต่ไม่มีแคตตาล็อกโมเดลส่วนกลาง | สร้าง `catalogModelInfo` / `DEFAULT_MODELS` registry ส่วนกลางใน ZCoder ที่เก็บข้อมูลเมตาของโมเดล (id, provider, capabilities, context window, default sampling) ให้ adapter และ runtime อ้างอิงร่วมกัน |
| `registerAdapter` / `registerConfigurableProviders` | ไม่มีฟังก์ชันลงทะเบียน adapter หรือ provider ที่กำหนดค่าได้ ผู้ใช้เลือก provider ผ่าน `resolve_provider()` ใน `providers.py` เท่านั้น ไม่มีจุดต่อสำหรับ plugin ของบุคคลที่สาม | สร้าง `registerAdapter` และ `registerConfigurableProviders` ใน Python ให้ plugin สามารถลงทะเบียน model adapter ของตนเองและ provider ที่กำหนดค่าได้ การลงทะเบียนทั้งหมดเป็น side effect ผ่าน `ctx.effect()` / `ctx.on()` และ `register()` ต้องคืน disposer |

### 3.2 Session & Event Log

| deepseek-harness feature | ZCoder equivalent | Gap / Action |
|---|---|---|
| `SessionStore` / `Session` class | `src/zcoder/agent/orchestration/sessions.py` (`sessions.py`) มี `Session` dataclass (`sid`, `mode`, `title`, `model`, `persona`, `turns`, `created`, `updated`), `Turn`, `Checkpoint` และฟังก์ชัน `save_session`, `load_session`, `latest_session`, `list_sessions`, `capture_checkpoint`, `rewind_to_checkpoint` เก็บเป็นไฟล์ JSON snapshot ใน `~/.zcoder/sessions` | ปรับปรุง `Session` ให้เป็น class บน `SessionStore` ที่สนับสนุน event-sourced log แทน snapshot เปล่า แต่ละเซสชันมีรหัสเซสชันที่เป็น branded id (`Branded<B>`) เก็บเหตุการณ์เป็นอาร์เรย์ที่สามารถเพิ่มเติมได้อย่างปลอดภัย และรองรับการโหลดและบันทึกแบบ atomically |
| `SESSION_FORMAT_VERSION = 4` | ZCoder ไม่มีเวอร์ชันรูปแบบเซสชัน (`SESSION_FORMAT_VERSION`) ไฟล์ JSON ของเซสชันไม่มีฟิลด์เวอร์ชัน การอ่านรุ่นเก่าไม่มีการรับประกันความปลอดภัย | กำหนด `SESSION_FORMAT_VERSION = 4` (หรือเวอร์ชันเริ่มต้นของ ZCoder) ในไฟล์กำหนดรูปแบบเซสชัน แต่ละไฟล์เซสชันต้องมีฟิลด์เวอร์ชัน ผู้อ่านรุ่นเก่าต้องตีความอย่างปลอดภัยตามกฎ selben-version changes ที่ต้องมี safe reader behavior bump เวอร์ชันเฉพาะเมื่อ discriminant เดิมไม่สามารถป้องกันการตีความที่ไม่ปลอดภัย |
| ignorable event types | ZCoder ไม่มีแนวคิด ignorable event types เหตุการณ์ทั้งหมดในไฟล์ JSON ถูกอ่านเป็น `Turn` และ `Checkpoint` เท่านั้น ไม่มีเหตุการณ์ที่ผู้อ่านรุ่นใหม่สามารถข้ามได้อย่างปลอดภัย | กำหนด ignorable event types ในสคีมาของเซสชัน เหตุการณ์ที่ไม่รู้จักหรือไม่เกี่ยวข้องกับรุ่นปัจจุบันต้องถูกข้ามได้โดยไม่ทำให้การอ่านล้มเหลว รองรับการพัฒนาสคีมาต่อเนื่องโดยไม่ทำลายไฟล์เก่า |
| surface/fold helpers | ZCoder มี `recap()` สำหรับสรุปเซสชันสั้น ๆ และ `away_summary()` สำหรับสรุปการเปลี่ยนแปลงในโปรเจกต์ แต่ไม่มี surface helper หรือ fold helper ที่สร้างสถานะปัจจุบันจากเหตุการณ์ย้อนหลังอย่างเป็นระบบ | สร้าง surface helper สำหรับมุมมองปัจจุบันของเซสชัน และ fold helper สำหรับพับเหตุการณ์ย้อนหลังเป็นสถานะ ทุกตัวช่วยต้องทำงานบน event log ไม่ใช่ snapshot และต้องปลอดภัยต่อการตีความรุ่นก่อนหน้า |
| sessionProjections | ZCoder ไม่มี sessionProjections แต่ละส่วนของระบบอ่านไฟล์ JSON ของเซสชันโดยตรง ไม่มีการสร้างมุมมอง (projection) จากเหตุการณ์ | สร้าง sessionProjections ที่อ่าน event log ของเซสชันและสร้างมุมมองย่อยสำหรับแต่ละบริบท (เช่น ประวัติการแชท, สรุปการใช้โทเค็น, สถานะ checkpoint) แต่ละ projection ต้องสร้างจากเหตุการณ์เท่านั้นและสอดคล้องกับรูปแบบเซสชันที่กำหนดไว้ |

### 3.3 Tool System

| deepseek-harness feature | ZCoder equivalent | Gap / Action |
|---|---|---|
| `ToolsService` (`ctx.tools`) | ZCoder ไม่มี `ToolsService` และไม่มี `ctx.tools` REPL (`interactive.py`) ระบุชัดเจนว่า "does not execute tools or access the filesystem" ตัวแทน (`agents_sdk.py`, `orchestration`) ยังไม่มีบริการเครื่องมือส่วนกลาง | สร้าง `ToolsService` ใน Python ที่เข้าถึงผ่าน context (`ctx.tools`) เหมือน deepseek-harness ให้ plugin สามารถบริจาคเครื่องมือและบริการจัดการวงจรชีวิตของเครื่องมือได้ รวมถึงการค้นหา ลงทะเบียน และเพิกถอนเครื่องมือ |
| `ToolDefinition` with `execute` / `projectContent` / `finalizeContent` | ZCoder ไม่มี `ToolDefinition` เครื่องมือ (หากมีในอนาคต) จะถูกเขียนเป็นฟังก์ชันธรรมดาโดยไม่มีออบเจกต์นิยามเครื่องมือที่พิมพ์ชนิดพร้อม method สำหรับการฉายเนื้อหาและการทำให้สมบูรณ์ | กำหนด `ToolDefinition` class ใน Python พร้อม `execute` สำหรับการเรียกใช้งานจริง `projectContent` สำหรับการฉายเนื้อหาผลลัพธ์กลับสู่ผู้ใช้ และ `finalizeContent` สำหรับการทำให้เนื้อหาสมบูรณ์ก่อนส่งถึงโมเดล แต่ละเครื่องมือต้องมีนิยามที่ชัดเจนและพิมพ์ชนิด |
| tools/pre-execute / execute / tools/post-execute waterfall | ZCoder ไม่มีห่วงโซ่ waterfall สำหรับเครื่องมือ การเรียกใช้เครื่องมือ (ถ้ามี) จะเกิดขึ้นครั้งเดียวโดยไม่มีเฟสก่อน หลัง หรือการส่งต่อระหว่างผู้ฟัง | สร้างห่วงโซ่ waterfall `tools/pre-execute` → `execute` → `tools/post-execute` ผู้ฟังแบบ waterfall ต้องเรียก `next()` เพื่อส่งต่อให้ผู้ฟังถัดไป การคืนค่าโดยไม่เรียก `next()` จะทำให้ห่วงโซ่สั้น (short-circuit) แต่ละเฟสต้องพิมพ์ชนิดและมีเอกสารกำกับพารามิเตอร์และค่าที่คืนกลับ |
| `tools/result` / `tools/change` emit events | ZCoder ไม่มีเหตุการณ์ `tools/result` หรือ `tools/change` ผลลัพธ์ของเครื่องมือ (ถ้ามี) จะถูกคืนเป็นค่าส่งกลับธรรมดา ไม่ถูกปล่อยเป็นเหตุการณ์ในระบบเหตุการณ์ | กำหนดให้ `tools/result` และ `tools/change` ถูกปล่อยออกมาเป็น typed event หลังจากเครื่องมือทำงานเสร็จหรือเนื้อหาเปลี่ยนแปลง ทุกเหตุการณ์ต้องถูกบันทึกในเซสชัน log และผู้บริโภคสามารถสมัครรับเหตุการณ์ผ่าน `ctx.on()` |
| `ToolExecutionPipeline` | ZCoder ไม่มี `ToolExecutionPipeline` การประมวลผลเครื่องมือ (ถ้ามี) จะดำเนินการแบบเชิงเส้นโดยไม่มี pipeline ที่ควบคุมการเรียกใช้ การซ้ำ และการจัดการข้อผิดพลาด | สร้าง `ToolExecutionPipeline` ใน Python ที่จัดการวงจรชีวิตของเครื่องมือตั้งแต่การก่อนเรียกใช้ การเรียกใช้งาน การหลังเรียกใช้ การจัดการข้อผิดพลาด และการปล่อยเหตุการณ์ แต่ละขั้นตอนใน pipeline ต้องมีรั้วกัน (guard) และรายงานสถานะอย่างชัดเจน |
| `executeToolBatch` | ZCoder ไม่มี `executeToolBatch` ไม่สามารถเรียกใช้เครื่องมือหลายตัวเป็นชุดและรอผลลัพธ์ทั้งหมดได้ | สร้าง `executeToolBatch` ฟังก์ชันใน Python ที่รับรายการคำขอเครื่องมือหลายรายการ เรียกใช้ผ่าน `ToolExecutionPipeline` คืนผลลัพธ์เป็นชุดที่สอดคล้องกัน และปล่อยเหตุการณ์ `tools/result` สำหรับแต่ละเครื่องมือที่เรียกใช้ |
# ZCoder Big Upgrade Master Plan — Part 2: Architectural Patterns & Phase Plan

## เกริ่นนำ (Introduction)

เอกสารนี้คือภาคที่ 2 ของแผนปรับปรุงครั้งใหญ่ของ ZCoder ("ZCoder Big Upgrade Master Plan") ซึ่งมุ่งเน้นรูปแบบสถาปัตยกรรม (architectural patterns) ที่ควรนำมาใช้จาก deepseek-harness (DSH) และแผนการดำเนินงานเป็นเฟส (phase-by-phase implementation plan) ครอบคลุม Phase 0 ถึง Phase 9

ภาษา: ข้อความอธิบายเขียนเป็นภาษาไทย โค้ด เส้นทางไฟล์ ชื่อคลาส ชื่อฟังก์ชัน ชื่อตัวแปรสภาพแวดล้อม ชื่อแพ็กเกจ เขียนเป็นภาษาอังกฤษ

เอกสารนี้อ้างอิงโครงสร้างและคอนเวนชันของ deepseek-harness ที่อธิบายไว้ใน `docs/architecture.md`, `docs/cordis-primer.md`, `docs/testing.md`, และ `docs/AGENTS.md` รวมถึง `vendor/README.md` สำหรับแพ็กเกจที่ vendored มา

---

## 4. Architectural Patterns to Adopt (from deepseek-harness)

รายการรูปแบบสถาปัตยกรรม 10 แบบที่ ZCoder ควรนำมาใช้จาก deepseek-harness โดยมีคำอธิบายและแนวทางการนำไปใช้ใน ZCoder ที่เขียนด้วย Python

### 4.1 Capability Seam (Service Definition / Provider / Consumer)

**คำอธิบาย:** รอยต่อความสามารถ (capability seam) ประกอบด้วยสามบทบาทที่สมบูรณ์: Service Definition (อินเทอร์เฟซ/สัญญาของบริการ), Service Provider (การดำเนินการจริง), และ Consumer (ผู้เรียกใช้บริการ) รอยต่อนี้ต้องสมบูรณ์เสมอ ไม่ใช่แค่บทบาทเดียว แยกบทบาทเมื่อบทบาทต่างๆ พัฒนาอิสระต่อกัน

**การนำไปใช้ใน Python ZCoder:**
- สร้าง `ServiceDefinition` เป็น Python protocol (PEP 544) หรือ abstract base class ที่กำหนดเมธอดที่บริการต้องมี
- Provider ดำเนินการตาม protocol และลงทะเบียนผ่าน `ctx.register()` หรือดิการ์ดที่เทียบเท่า
- Consumer รับ provider ผ่าน dependency injection (constructor injection) ไม่ควรสร้าง instance ของ provider โดยตรงภายใน consumer
- ตัวอย่างโครงสร้างไฟล์:
  - `zcoder/services/llm/definition.py` — `LLMService` protocol
  - `zcoder/services/llm/provider.py` — `DeepSeekLLMProvider` implements `LLMService`
  - `zcoder/services/llm/consumer.py` — `Agent` receives `LLMService` via constructor

```python
# zcoder/services/llm/definition.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class LLMService(Protocol):
    async def generate(self, prompt: str, **kwargs) -> str: ...
    async def stream_generate(self, prompt: str, **kwargs): ...

# zcoder/services/llm/provider.py
from zcoder.services.llm.definition import LLMService

class DeepSeekLLMProvider:
    def __init__(self, api_key: str, base_url: str) -> None: ...
    async def generate(self, prompt: str, **kwargs) -> str: ...
    async def stream_generate(self, prompt: str, **kwargs): ...

# zcoder/services/llm/consumer.py
from zcoder.services.llm.definition import LLMService

class Agent:
    def __init__(self, llm: LLMService) -> None:
        self._llm = llm
    async def run(self, prompt: str) -> str:
        return await self._llm.generate(prompt)
```

### 4.2 Registrations Are Effects

**คำอธิบาย:** การลงทะเบียนทุกอย่างเป็นผลข้างเคียง (effect): การมีส่วนร่วมทุกอย่างผ่าน `ctx.effect()` / `ctx.on()` ตัวคืนค่าของ registry `register()` คือตัวยกเลิกการลงทะเบียน (disposer) โดยตรง หรือผ่านจับการลงทะเบียนตามที่เอกสารกำหนด

**การนำไปใช้ใน Python ZCoder:**
- เมื่อปลั๊กอินหรือโมดูลเริ่มต้น ให้คืนค่า callable (disposer) ที่ใช้ยกเลิกการลงทะเบียนเมื่อปิดระบบ
- เก็บ disposer ไว้ในบริบทของแอปพลิเคชันและเรียกใช้เมื่อ tear down
- ตัวอย่าง:

```python
# zcoder/plugins/registry.py
from typing import Callable

class PluginRegistry:
    def __init__(self) -> None:
        self._disposers: list[Callable[[], None]] = []

    def register_effect(self, disposer: Callable[[], None]) -> None:
        self._disposers.append(disposer)

    async def teardown(self) -> None:
        for disposer in reversed(self._disposers):
            disposer()
        self._disposers.clear()
```

### 4.3 Waterfall Listener Semantics

**คำอธิบาย:** ผู้ฟังแบบน้ำตก (waterfall listeners) ต้องเรียก `next()` เพื่อส่งต่อให้ลำดับถัดไป การคืนค่าโดยไม่เรียก `next()` จะทำให้ลำดับสั้นลง (short-circuit)

**การนำไปใช้ใน Python ZCoder:**
- สร้างระบบอีเวนต์ที่ผู้ฟังสามารถแก้ไขผลลัพธ์และส่งต่อไปยังผู้ฟังถัดไป
- แต่ละผู้ฟังรับ `(context, next_callable)` และต้องเรียก `await next_callable()` ถ้าต้องการให้ลำดับดำเนินต่อไป
- ถ้าผู้ฟังคืนค่าโดยไม่เรียก `next()` ลำดับจะหยุดที่ผู้ฟังนั้นทันที

```python
# zcoder/events/waterfall.py
from typing import Callable, Any, Awaitable

WaterfallListener = Callable[[Any, Callable[[], Awaitable[Any]]], Awaitable[Any]]

class Waterfall:
    def __init__(self, listeners: list[WaterfallListener]) -> None:
        self._listeners = listeners

    async def run(self, initial: Any) -> Any:
        async def next_step(index: int, value: Any) -> Any:
            if index >= len(self._listeners):
                return value
            listener = self._listeners[index]
            return await listener(value, lambda: next_step(index + 1, value))
        return await next_step(0, initial)
```

### 4.4 Model-Visible ⟺ Logged

**คำอธิบาย:** อะไรก็ตามที่ไปถึงคำขอโมเดลต้องสร้างจากบันทึกเซสชัน (session log) ขึ้นมาใหม่ได้ สิ่งที่มองเห็นได้จากโมเดลต้องมีอีเวนต์เซสชันสนับสนุน

**การนำไปใช้ใน Python ZCoder:**
- ทุกคำขอที่ส่งไปยังโมเดลภาษาต้องมีอีเวนต์เซสชันที่ตรงกันก่อนหรือพร้อมกัน
- เก็บ prompt, parameter, และการตอบกลับทั้งหมดใน session log
- เมื่อเล่นเซสชันซ้ำ (replay) ต้องสามารถสร้างคำขอโมเดลเดียวกันจากบันทึกได้

```python
# zcoder/session/event.py
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ModelRequestEvent:
    event_type: str = "model_request"
    timestamp: str = ""
    model: str = ""
    prompt: str = ""
    parameters: dict = None
    response: str = None

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()
        if self.parameters is None:
            self.parameters = {}
```

### 4.5 Branded IDs

**คำอธิบาย:** รหัสทึบที่ข้ามขอบเขตต้องเป็น branded type (`Branded<B>`) ไม่ใช่สตริงเปล่าๆ

**การนำไปใช้ใน Python ZCoder:**
- ใช้ `typing.NewType` หรือคลาสแรปเปอร์สำหรับรหัสเช่น `SessionId`, `ToolCallId`, `EventId`
- ป้องกันการส่งรหัสชนิดหนึ่งไปยังตำแหน่งที่คาดหวังอีกชนิดหนึ่งโดยไม่ตั้งใจ

```python
# zcoder/types/ids.py
from typing import NewType

SessionId = NewType("SessionId", str)
ToolCallId = NewType("ToolCallId", str)
EventId = NewType("EventId", str)
AgentId = NewType("AgentId", str)

def make_session_id(value: str) -> SessionId:
    return SessionId(value)
```

### 4.6 No Unknown Casts

**คำอธิบาย:** ห้ามแปลงเป็น `unknown` (`as unknown` หรือ `<unknown>`) คงค่าเดิมตาม baseline หรือใช้ค่าที่พิมพ์ไว้ หรือใช้การตรวจสอบความถูกต้องสำหรับการแทนที่

**การนำไปใช้ใน Python ZCoder:**
- ห้ามใช้ `cast(Any, value)` หรือ `value # type: ignore` เพื่อปิดการตรวจสอบชนิด
- ใช้ `typing.cast` เฉพาะเมื่อชนิดจริงทราบแน่ชัดและไม่สามารถอนุมานได้จากโค้ด
- ตรวจสอบความถูกต้องที่ขอบเขตของการแยกวิเคราะห์ (parser), คอนฟิก, คิว, JSON ของโมเดล/เครื่องมือ, ไฟล์/ดิสก์, เวิร์กเกอร์, กระบวนการ และขอบเขตสาย

```python
# zcoder/types/safe_cast.py
from typing import TypeVar, cast, Any

T = TypeVar("T")

def safe_cast(value: Any, target_type: type[T]) -> T:
    if not isinstance(value, target_type):
        raise TypeError(f"Expected {target_type.__name__}, got {type(value).__name__}")
    return cast(T, value)
```

### 4.7 Explicit > Implicit at Package Boundaries

**คำอธิบาย:** การค่าเริ่มต้น (defaulting) เป็นขั้นตอน `resolve(request): Spec` ที่ชัดเจนในการดำเนินการที่เป็นเจ้าของ ไม่ใช่ `?? default` ที่ซ่อนอยู่ภายใน `run()` (การแยกคำขอ/สเปกของ dsh-shell คือตัวอย่าง)

**การนำไปใช้ใน Python ZCoder:**
- ที่ขอบเขตแพ็กเกจ แยกออบเจกต์คำขอ (request) ออกจากออบเจกต์สเปก (spec/resolved)
- ฟังก์ชัน `resolve()` รับคำขอและคืนค่าสเปกที่แก้ไขแล้ว รวมถึงการใช้ค่าเริ่มต้นอย่างชัดเจน
- ฟังก์ชัน `run()` รับเฉพาะสเปกที่แก้ไขแล้วและไม่สมมติค่าเริ่มต้นใดๆ

```python
# zcoder/shell/spec.py
from dataclasses import dataclass

@dataclass(frozen=True)
class ShellRequest:
    command: str
    cwd: str | None = None
    env: dict[str, str] | None = None

@dataclass(frozen=True)
class ShellSpec:
    command: str
    cwd: str
    env: dict[str, str]

def resolve(request: ShellRequest, default_cwd: str, default_env: dict[str, str]) -> ShellSpec:
    return ShellSpec(
        command=request.command,
        cwd=request.cwd if request.cwd is not None else default_cwd,
        env={**default_env, **(request.env or {})},
    )
```

### 4.8 Misconfiguration Fails Loud

**คำอธิบาย:** การตั้งค่าผิดพลาดล้มเหลวดัง (fail loud) ตเมื่อโหลดเมื่อจัดการด้วยตนเอง มิฉะนั้นที่จุดที่แก้ไขได้เร็วที่สุด ห้ามข้ามการอ้างอิงที่ขาดหายไปอย่างเงียบๆ

**การนำไปใช้ใน Python ZCoder:**
- ตรวจสอบคอนฟิกเมื่อโหลดปลั๊กอินหรือบริการ ถ้าขาดการอ้างอิงให้ขัดขวางการเริ่มต้นทันที
- ยก `HarnessError` (หรือคลาสข้อผิดพลาดที่กำหนดเอง) พร้อมข้อความที่ชัดเจนและแก้ไขได้
- ห้ามจับข้อผิดพลาดแล้วเงียบหรือข้ามการอ้างอิงที่ขาด

```python
# zcoder/config/loader.py
from __future__ import annotations
import os

class HarnessError(Exception):
    pass

def load_api_key(env_var: str = "ZCODER_API_KEY") -> str:
    value = os.getenv(env_var)
    if not value:
        raise HarnessError(
            f"Missing required environment variable {env_var}. "
            f"Set it in .env or export before starting ZCoder."
        )
    return value
```

### 4.9 One Async Operation = One Lifecycle Controller

**คำอธิบาย:** การดำเนินการแบบอะซิงโครนัสหนึ่งรายการ = ตัวควบคุมวงจรชีวิตหนึ่งตัว

**การนำไปใช้ใน Python ZCoder:**
- แต่ละงานอะซิงโครนัส (เช่น การสตรีม การเรียกเครื่องมือ การเรียกโมเดล) ต้องมีตัวควบคุมวงจรชีวิตเฉพาะที่จัดการการเริ่มต้น การยกเลิก และการทำความสะอาด
- ใช้ `asyncio.Task` พร้อม `asyncio.Event` สำหรับสัญญาณยกเลิก
- เมื่อยกเลิก ให้เรียก `task.cancel()` และรอให้เสร็จสิ้น แล้วทำความสะอาดทรัพยากร (ปิดฟลิปเปอร์ ล้างบัฟเฟอร์ ฯลฯ)

```python
# zcoder/async/lifecycle.py
from __future__ import annotations
import asyncio
from typing import Callable, Awaitable, Optional

class AsyncOperationController:
    def __init__(self, coro_factory: Callable[[], Awaitable[None]]) -> None:
        self._coro_factory = coro_factory
        self._task: Optional[asyncio.Task[None]] = None
        self._cancel_event = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())
        await self._task

    async def _run(self) -> None:
        try:
            await self._coro_factory()
        except asyncio.CancelledError:
            await self.cleanup()
            raise

    async def cancel(self) -> None:
        self._cancel_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def cleanup(self) -> None:
        pass
```

### 4.10 Plugins, Not Loop Changes

**คำอธิบาย:** พฤติกรรมใหม่ไปที่จุดขยายที่มีเอกสาร ไม่ต้องเปลี่ยน agent-loop การเปลี่ยน agent-loop ต้องอัปเดต `docs/architecture.md`

**การนำไปใช้ใน Python ZCoder:**
- สร้างระบบปลั๊กอินที่ช่วยให้สามารถเพิ่มพฤติกรรมใหม่ผ่าน hook points (เช่น ก่อน/หลังการเรียกโมเดล ก่อน/หลังการเรียกเครื่องมือ)
- ห้ามแก้ไขลูป agent หลักเพื่อเพิ่มคุณสมบัติ ให้ลงทะเบียนปลั๊กอินแทน
- ตัวอย่าง hook points: `before_llm_call`, `after_llm_call`, `before_tool_call`, `after_tool_call`

```python
# zcoder/plugins/hooks.py
from __future__ import annotations
from typing import Callable, Awaitable

HookHandler = Callable[..., Awaitable[None]]

class PluginHooks:
    def __init__(self) -> None:
        self._before_llm: list[HookHandler] = []
        self._after_llm: list[HookHandler] = []
        self._before_tool: list[HookHandler] = []
        self._after_tool: list[HookHandler] = []

    def register_before_llm(self, handler: HookHandler) -> None:
        self._before_llm.append(handler)

    def register_after_llm(self, handler: HookHandler) -> None:
        self._after_llm.append(handler)

    def register_before_tool(self, handler: HookHandler) -> None:
        self._before_tool.append(handler)

    def register_after_tool(self, handler: HookHandler) -> None:
        self._after_tool.append(handler)

    async def run_before_llm(self, **kwargs: object) -> None:
        for handler in self._before_llm:
            await handler(**kwargs)

    async def run_after_llm(self, **kwargs: object) -> None:
        for handler in self._after_llm:
            await handler(**kwargs)

    async def run_before_tool(self, **kwargs: object) -> None:
        for handler in self._before_tool:
            await handler(**kwargs)

    async def run_after_tool(self, **kwargs: object) -> None:
        for handler in self._after_tool:
            await handler(**kwargs)
```

---

## 5. Phase-by-Phase Implementation Plan (Phase 0–9)

แผนการดำเนินงานเป็นเฟส ครอบคลุม Phase 0 ถึง Phase 9 รวมทั้งหมด 31 วัน แต่ละเฟสประกอบด้วย ชื่อเฟสและจำนวนวัน เป้าหมาย (หนึ่งประโยค) ตารางงาน (ลำดับ | งาน | ไฟล์ | การอ้างอิงจาก deepseek-harness) และเกณฑ์การออก (exit criteria)

---

### Phase 0: Baseline & Assessment (Days 1–2) — 4 tasks

**เป้าหมาย:** สร้างพื้นฐานโค้ดปัจจุบัน ประเมินช่องว่าง และกำหนดคอนเวนชันสำหรับการอัปเกรด

| # | Task | File | deepseek-harness reference |
|---|------|------|---------------------------|
| 1 | สำรวจโครงสร้างโค้ด ZCoder ปัจจุบัน และจัดทำบัญชีโมดูล คลาส และฟังก์ชันทั้งหมด | `zcoder/` | `docs/architecture.md` (repository layout) |
| 2 | ประเมินช่องว่างระหว่าง ZGoder กับรูปแบบสถาปัตยกรรม DSH 10 แบบในภาคที่ 4 | `docs/gap-assessment.md` | Section 4 of this document |
| 3 | กำหนดคอนเวนชันการตั้งชื่อ ชนิดข้อมูล และรูปแบบโมดูลสำหรับ Python ZCoder | `zcoder/CONVENTIONS.md` | `docs/AGENTS.md` (conventions) |
| 4 | ตั้งค่าเครื่องมือคุณภาพโค้ด (typecheck, lint, formatter) สำหรับโครงการ Python | `pyproject.toml`, `.pre-commit-config.yaml` | `pnpm run typecheck`, `pnpm run lint` |

**เกณฑ์การออก:**
- บัญชีโมดูล คลาส และฟังก์ชันของ ZCoder ปัจจุบันครบถ้วน
- เอกสารประเมินช่องว่างระบุเฟสที่ต้องปรับเปลี่ยนสำหรับแต่ละรูปแบบสถาปัตยกรรม
- คอนเวนชันการตั้งชื่อและรูปแบบโมดูลได้รับการบันทึกและทีมเห็นพ้องต้องกัน
- เครื่องมือ typecheck, lint, formatter ทำงานผ่านบนโค้ดพื้นฐาน

---

### Phase 1: Typed Configuration & Credential Seam (Days 3–5) — 6 tasks

**เป้าหมาย:** นำคอนฟิกที่พิมพ์ชนิดและรอยต่อข้อมูลประจำตัว (credential seam) มาใช้ รวมทั้งการตรวจสอบคอนฟิกเมื่อโหลด

| # | Task | File | deepseek-harness reference |
|---|------|------|---------------------------|
| 1 | สร้างโมดูลคอนฟิกที่พิมพ์ชนิดด้วย dataclass หรือ Pydantic model สำหรับการตั้งค่าทั้งหมด | `zcoder/config/types.py` | `Config` fields from cordis.yml |
| 2 | สร้างตัวโหลดคอนฟิกที่อ่านจากไฟล์ `.env` และตัวแปรสภาพแวดล้อม | `zcoder/config/loader.py` | `.env`, `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL` |
| 3 | นำรอยต่อข้อมูลประจำตัวมาใช้ที่ตรวจสอบคีย์ API เมื่อโหลดและล้มเหลวดังเมื่อขาดหาย | `zcoder/credentials/seam.py` | `credentials/` package in DSH |
| 4 | ยก `HarnessError` เมื่อคอนฟิกผิดหรือตัวแปรสภาพแวดล้อมจำเป็นขาดหาย | `zcoder/config/loader.py` | Misconfiguration Fails Loud (4.8) |
| 5 | ลงทะเบียนคอนฟิกเป็นเอฟเฟกต์ของการเริ่มต้นระบบที่สามารถยกเลิกได้เมื่อปิดระบบ | `zcoder/app/bootstrap.py` | Registrations Are Effects (4.2) |
| 6 | เขียนทดสอบหน่วยสำหรับการโหลดคอนฟิก การตรวจสอบ และการจัดการข้อมูลประจำตัว | `tests/config/test_loader.py` | `dsh-ci-test-reliability` |

**เกณฑ์การออก:**
- โมดูลคอนฟิกพิมพ์ชนิดครอบคลุมการตั้งค่าทั้งหมดของ ZCoder
- ตัวโหลดคอนฟิกอ่านจาก `.env` และตัวแปรสภาพแวดล้อมได้ถูกต้อง
- รอยต่อข้อมูลประจำตัวตรวจสอบคีย์ API และล้มเหลวดังเมื่อขาดหาย
- `HarnessError` ถูกยกเมื่อคอนฟิกผิดหรือตัวแปรจำเป็นขาดหาย
- การเริ่มต้นระบบลงทะเบียนคอนฟิกเป็นเอฟเฟกต์ที่ยกเลิกได้
- ทดสอบหน่วยผ่านทั้งหมดสำหรับการโหลดคอนฟิกและการจัดการข้อมูลประจำตัว

---

### Phase 2: Provider Adapter Pattern (Days 6–8) — 9 tasks

**เป้าหมาย:** สร้างรูปแบบตัวแปลงผู้ให้บริการ (provider adapter) สำหรับโมเดลภาษา โดยแยกอินเทอร์เฟซบริการออกจากการดำเนินการ

| # | Task | File | deepseek-harness reference |
|---|------|------|---------------------------|
| 1 | กำหนดโปรโตคอลบริการ LLM (Service Definition) ด้วย `typing.Protocol` | `zcoder/services/llm/definition.py` | Capability Seam (4.1) |
| 2 | สร้างตัวแปลง DeepSeek ที่ดำเนินการตามโปรโตคอล LLM | `zcoder/services/llm/deepseek_adapter.py` | `llm/` model providers |
| 3 | สร้างตัวแปลง OpenAI ที่รองรับรูปแบบเดียวกันเพื่อทดสอบการสลับผู้ให้บริการ | `zcoder/services/llm/openai_adapter.py` | Multiple providers in `llm/` |
| 4 | สร้างโรงงานผู้ให้บริการ (provider factory) ที่แก้ไขตัวแปลงจากคอนฟิก | `zcoder/services/llm/factory.py` | Explicit > Implicit at Package Boundaries (4.7) |
| 5 | ใช้ branded ID สำหรับรหัสโมเดลและรหัสคำขอ | `zcoder/types/ids.py` | Branded IDs (4.5) |
| 6 | ห้ามแปลงเป็น `unknown` และใช้ typed cast ที่ขอบเขตตัวแปลงผู้ให้บริการ | `zcoder/services/llm/adapter_base.py` | No Unknown Casts (4.6) |
| 7 | ลงทะเบียนตัวแปลงผู้ให้บริการเป็นเอฟเฟกต์ของปลั๊กอินเมื่อเริ่มต้น | `zcoder/plugins/llm_plugin.py` | Registrations Are Effects (4.2) |
| 8 | เขียนทดสอบหน่วยสำหรับตัวแปลงผู้ให้บริการแต่ละรายและโรงงาน | `tests/services/llm/test_adapters.py` | Provider adapter tests |
| 9 | เขียนทดสอบการสลับผู้ให้บริการโดยไม่เปลี่ยนโค้ดผู้บริโภค | `tests/services/llm/test_provider_swap.py` | Capability Seam consumer test |

**เกณฑ์การออก:**
- โปรโตคอลบริการ LLM กำหนดไว้ด้วย `typing.Protocol`
- ตัวแปลง DeepSeek และ OpenAI ดำเนินการตามโปรโตคอลเดียวกัน
- โรงงานผู้ให้บริการแก้ไขตัวแปลงจากคอนฟิกอย่างชัดเจน
- ใช้ branded ID สำหรับรหัสโมเดลและรหัสคำขอ
- ไม่มีการแปลงเป็น `unknown` ที่ขอบเขตตัวแปลงผู้ให้บริการ
- ตัวแปลงผู้ให้บริการถูกลงทะเบียนเป็นเอฟเฟกต์ของปลั๊กอิน
- ทดสอบหน่วยสำหรับตัวแปลงแต่ละรายและโรงงานผ่านทั้งหมด
- ทดสอบการสลับผู้ให้บริการยืนยันว่าผู้บริโภคไม่ต้องเปลี่ยนโค้ด

---

### Phase 3: Async Streaming & Cancellation (Days 9–11) — 7 tasks

**เป้าหมาย:** นำการสตรีมแบบอะซิงโครนัสและการยกเลิกมาใช้ โดยแต่ละการดำเนินการอะซิงโครนัสมีตัวควบคุมวงจรชีวิตหนึ่งตัว

| # | Task | File | deepseek-harness reference |
|---|------|------|---------------------------|
| 1 | สร้างอินเทอร์เฟซตัวควบคุมวงจรชีวิตสำหรับการดำเนินการอะซิงโครนัส | `zcoder/async/lifecycle.py` | One Async Operation = One Lifecycle Controller (4.9) |
| 2 | นำเครื่องสตรีมแบบอะซิงโครนัสสำหรับการตอบกลับโมเดลภาษาที่รองรับการยกเลิก | `zcoder/services/llm/stream.py` | `stream_generate` in LLM service |
| 3 | เพิ่มสัญญาณยกเลิกด้วย `asyncio.Event` ให้กับตัวควบคุมวงจรชีวิต | `zcoder/async/lifecycle.py` | `asyncio.Task` cancellation |
| 4 | ตรวจสอบว่าการสตรีมของโมเดลที่มองเห็นได้ต้องถูกบันทึกในบันทึกเซสชัน | `zcoder/session/logger.py` | Model-Visible ⟺ Logged (4.4) |
| 5 | นำตัวจัดการคำสั่งหยุดที่ยกเลิกงานอะซิงโครนัสที่ค้างอยู่ทั้งหมดเมื่อปิดระบบ | `zcoder/app/shutdown.py` | Lifecycle teardown |
| 6 | เขียนทดสอบสำหรับการสตรีม การยกเลิก และการทำความสะอาดทรัพยากร | `tests/async/test_streaming.py` | Async operation tests |
| 7 | เขียนทดสอบการยกเลิกแบบเรียงซ้อนเมื่อตัวควบคุมหลักถูกยกเลิก | `tests/async/test_cancellation.py` | Lifecycle controller cascade |

**เกณฑ์การออก:**
- อินเทอร์เฟซตัวควบคุมวงจรชีวิตจัดการการเริ่มต้น การยกเลิก และการทำความสะอาด
- เครื่องสตรีมแบบอะซิงโครนัสสำหรับการตอบกลับโมเดลภาษารองรับการยกเลิก
- สัญญาณยกเลิกใช้ `asyncio.Event`
- การสตรีมของโมเดลที่มองเห็นได้ถูกบันทึกในบันทึกเซสชัน
- ตัวจัดการคำสั่งหยุดยกเลิกงานอะซิงโครนัสที่ค้างอยู่เมื่อปิดระบบ
- ทดสอบสตรีม การยกเลิก และการทำความสะอาดทรัพยากรผ่านทั้งหมด
- ทดสอบการยกเลิกแบบเรียงซ้อนยืนยันว่างานย่อยถูกยกเลิกเมื่อตัวควบคุมหลักถูกยกเลิก

---

### Phase 4: Session Event Log (Days 12–15) — 6 tasks — **เสร็จสมบูรณ์**

**เป้าหมาย:** สร้างบันทึกเหตุการณ์เซสชัน (session event log) ที่บันทึกทุกสิ่งที่มองเห็นได้จากโมเดลและรองรับการเล่นเซสชันซ้ำ — **สำเร็จแล้ว**

| # | Task | File | สถานะ |
|---|------|------|--------|
| 1 | กำหนดอีเวนต์เซสชันด้วย dataclass พร้อมฟิลด์จำเป็น เช่น ประเภท เวลา รหัส และเพย์โหลด | `zcoder/session/event.py` | ✅ เสร็จสมบูรณ์ |
| 2 | สร้าง_logger_เซสชันที่เขียนอีเวนต์ลงไฟล์หรือหน่วยจัดเก็บข้อมูล | `zcoder/session/logger.py` | ✅ เสร็จสมบูรณ์ |
| 3 | เชื่อมต่ออีเวนต์โมเดลที่มองเห็นได้กับการบันทึกก่อนหรือพร้อมกับคำขอโมเดล | `zcoder/services/llm/stream.py` + `agent/codeagent/loop.py` | ✅ เสร็จสมบูรณ์ |
| 4 | ใช้ branded ID สำหรับรหัสเซสชัน รหัสอีเวนต์ และรหัสการเรียกเครื่องมือ | `zcoder/types/ids.py` | ✅ เสร็จสมบูรณ์ |
| 5 | นำเครื่องเล่นเซสชันซ้ำที่สร้างคำขอโมเดลจากบันทึกได้ | `zcoder/session/replay.py` | ✅ เสร็จสมบูรณ์ |
| 6 | เขียนทดสอบสำหรับการบันทึกอีเวนต์ การอ่านบันทึก และการเล่นเซสชันซ้ำ | `tests/session/test_logger.py` | ✅ เสร็จสมบูรณ์ |

**เกณฑ์การออก:**
- ✅ อีเวนต์เซสชันถูกกำหนดด้วย dataclass พร้อมฟิลด์จำเป็นครบถ้วน
- ✅ `_logger_`เซสชันเขียนอีเวนต์ลงไฟล์หรือหน่วยจัดเก็บข้อมูล
- ✅ อีเวนต์โมเดลที่มองเห็นได้ถูกบันทึกก่อนหรือพร้อมกับคำขอโมเดล
- ✅ ใช้ branded ID สำหรับรหัสเซสชัน รหัสอีเวนต์ และรหัสการเรียกเครื่องมือ
- ✅ เครื่องเล่นเซสชันซ้ำสร้างคำขอโมเดลจากบันทึกได้
- ✅ ทดสอบการบันทึกอีเวนต์ การอ่านบันทึก และการเล่นเซสชันซ้ำผ่านทั้งหมด

---

### Phase 5: Tool Registry & Guarded Execution (Days 16–19) — 8 tasks — **เสร็จสมบูรณ์**

**เป้าหมาย:** สร้างทะเบียนเครื่องมือ (tool registry) และการดำเนินการที่ถูกควบคุม (guarded execution) พร้อมการป้องกันลูปและการจำกัดเวลาทำงาน

| # | Task | File | deepseek-harness reference |
|---|------|------|---------------------------|
| 1 | กำหนดโปรโตคอลเครื่องมือ (tool protocol) สำหรับชื่อ พารามิเตอร์ และการดำเนินการ | `zcoder/tools/definition.py` | Capability Seam (4.1) |
| 2 | สร้างทะเบียนเครื่องมือที่ลงทะเบียนเครื่องมือเป็นเอฟเฟกต์และคืนตัวยกเลิก | `zcoder/tools/registry.py` | Registrations Are Effects (4.2) |
| 3 | นำการดำเนินการที่ถูกควบคุมด้วยการจำกัดเวลาทำงานและการป้องกันลูป | `zcoder/tools/guard.py` | `guard/` loop/tool guards |
| 4 | ลงทะเบียนผู้ฟังแบบน้ำตกสำหรับเหตุการณ์ก่อน/หลังการเรียกเครื่องมือ | `zcoder/tools/waterfall.py` | Waterfall Listener Semantics (4.3) |
| 5 | ใช้ branded ID สำหรับรหัสการเรียกเครื่องมือและรหัสเครื่องมือ | `zcoder/types/ids.py` | Branded IDs (4.5) |
| 6 | เชื่อมต่อการเรียกเครื่องมือกับบันทึกเหตุการณ์เซสชัน | `zcoder/session/logger.py` | Model-Visible ⟺ Logged (4.4) |
| 7 | เขียนทดสอบสำหรับทะเบียนเครื่องมือ การดำเนินการที่ถูกควบคุม และการป้องกันลูป | `tests/tools/test_registry.py` | Tool registry tests |
| 8 | เขียนทดสอบสำหรับผู้ฟังแบบน้ำตกและการสั้นลำดับ (short-circuit) | `tests/tools/test_waterfall.py` | Waterfall listener tests |

**เกณฑ์การออก:**
- โปรโตคอลเครื่องมือกำหนดชื่อ พารามิเตอร์ และการดำเนินการ
- ทะเบียนเครื่องมือลงทะเบียนเครื่องมือเป็นเอฟเฟกต์และคืนตัวยกเลิก
- การดำเนินการที่ถูกควบคุมมีการจำกัดเวลาทำงานและการป้องกันลูป
- ผู้ฟังแบบน้ำตกสำหรับเหตุการณ์ก่อน/หลังการเรียกเครื่องมือทำงานถูกต้อง
- ใช้ branded ID สำหรับรหัสการเรียกเครื่องมือและรหัสเครื่องมือ
- การเรียกเครื่องมือถูกเชื่อมต่อกับบันทึกเหตุการณ์เซสชัน
- ทดสอบทะเบียนเครื่องมือ การดำเนินการที่ถูกควบคุม และการป้องกันลูปผ่านทั้งหมด
- ทดสอบผู้ฟังแบบน้ำตกและการสั้นลำดับผ่านทั้งหมด

---

### Phase 6: Agent System Formalization (Days 20–23) — 8 tasks

**เป้าหมาย:** ระบบเอเจนต์เป็นทางการด้วยลูปเอเจนต์ที่กำหนดไว้ ปลั๊กอินสำหรับพฤติกรรมใหม่ และการเปลี่ยนแปลงลูปที่มีเอกสารรองรับ

| # | Task | File | deepseek-harness reference |
|---|------|------|---------------------------|
| 1 | กำหนดคลาสเอเจนต์พื้นฐานที่รับบริการผ่าน constructor injection | `zcoder/agent/base.py` | Capability Seam consumer (4.1) |
| 2 | สร้างลูปเอเจนต์ที่เรียกโมเดล ดำเนินการเครื่องมือ และวนซ้ำจนกว่าจะเสร็จสิ้น | `zcoder/agent/loop.py` | `agent-loop` in DSH |
| 3 | สร้างระบบปลั๊กอินที่มี hook points สำหรับก่อน/หลังการเรียกโมเดลและเครื่องมือ | `zcoder/plugins/hooks.py` | Plugins, Not Loop Changes (4.10) |
| 4 | ลงทะเบียนปลั๊กอินเป็นเอฟเฟกต์เมื่อเริ่มต้นและยกเลิกเมื่อปิดระบบ | `zcoder/app/bootstrap.py` | Registrations Are Effects (4.2) |
| 5 | ห้ามแก้ไขลูปเอเจนต์หลักเพื่อเพิ่มคุณสมบัติ ให้ใช้ปลั๊กอินแทน | `zcoder/agent/loop.py` | Plugins, Not Loop Changes (4.10) |
| 6 | บันทึกการเปลี่ยนแปลงลูปเอเจนต์ใน `docs/architecture.md` หากจำเป็น | `docs/architecture.md` | Agent-loop changes require doc update |
| 7 | ใช้ branded ID สำหรับรหัสเอเจนต์และรหัสเซสชัน | `zcoder/types/ids.py` | Branded IDs (4.5) |
| 8 | เขียนทดสอบสำหรับลูปเอเจนต์ ปลั๊กอิน และการสลับบริการ | `tests/agent/test_loop.py` | Agent system tests |

**เกณฑ์การออก:**
- คลาสเอเจนต์พื้นฐานรับบริการผ่าน constructor injection
- ลูปเอเจนต์เรียกโมเดล ดำเนินการเครื่องมือ และวนซ้ำจนกว่าจะเสร็จสิ้น
- ระบบปลั๊กอินมี hook points สำหรับก่อน/หลังการเรียกโมเดลและเครื่องมือ
- ปลั๊กอินถูกลงทะเบียนเป็นเอฟเฟกต์เมื่อเริ่มต้นและยกเลิกเมื่อปิดระบบ
- ไม่มีการแก้ไขลูปเอเจนต์หลักเพื่อเพิ่มคุณสมบัติโดยไม่ใช้ปลั๊กอิน
- การเปลี่ยนแปลงลูปเอเจนต์ถูกบันทึกใน `docs/architecture.md` หากจำเป็น
- ใช้ branded ID สำหรับรหัสเอเจนต์และรหัสเซสชัน
- ทดสอบลูปเอเจนต์ ปลั๊กอิน และการสลับบริการผ่านทั้งหมด

---

### Phase 7: Web / Search / Fetch Capability Seam (Days 24–26) — 7 tasks — เสร็จสมบูรณ์

**เป้าหมาย:** สร้างรอยต่อความสามารถสำหรับเว็บ การค้นหา และการดึงข้อมูล แยกอินเทอร์เฟซบริการออกจากผู้ให้บริการ

| # | Task | File | deepseek-harness reference |
|---|------|------|---------------------------|
| 1 | กำหนดโปรโตคอลบริการเว็บสำหรับการค้นหาและการดึงข้อมูลหน้าเว็บ | `zcoder/web/definition.py` | `web/` search/fetch tools |
| 2 | สร้างตัวแปลงผู้ให้บริการเว็บที่ดำเนินการตามโปรโตคอล | `zcoder/web/provider.py` | Provider adapter pattern |
| 3 | ลงทะเบียนบริการเว็บเป็นเอฟเฟกต์ของปลั๊กอินเมื่อเริ่มต้น | `zcoder/plugins/web_plugin.py` | Registrations Are Effects (4.2) |
| 4 | เชื่อมต่อผลการค้นหาและการดึงข้อมูลกับบันทึกเหตุการณ์เซสชัน | `zcoder/session/logger.py` | Model-Visible ⟺ Logged (4.4) |
| 5 | ใช้ branded ID สำหรับรหัสคำขอเว็บและรหัสผลการค้นหา | `zcoder/types/ids.py` | Branded IDs (4.5) |
| 6 | ตรวจสอบคอนฟิกบริการเว็บเมื่อโหลดและล้มเหลวดังเมื่อขาดการอ้างอิง | `zcoder/web/config.py` | Misconfiguration Fails Loud (4.8) |
| 7 | เขียนทดสอบสำหรับตัวแปลงบริการเว็บ การค้นหา และการดึงข้อมูล | `tests/web/test_provider.py` | Web service tests |

**เกณฑ์การออก:**
- โปรโตคอลบริการเว็บกำหนดการค้นหาและการดึงข้อมูลหน้าเว็บ
- ตัวแปลงผู้ให้บริการเว็บดำเนินการตามโปรโตคอล
- บริการเว็บถูกลงทะเบียนเป็นเอฟเฟกต์ของปลั๊กอินเมื่อเริ่มต้น
- ผลการค้นหาและการดึงข้อมูลถูกเชื่อมต่อกับบันทึกเหตุการณ์เซสชัน
- ใช้ branded ID สำหรับรหัสคำขอเว็บและรหัสผลการค้นหา
- คอนฟิกบริการเว็บถูกตรวจสอบเมื่อโหลดและล้มเหลวดังเมื่อขาดการอ้างอิง
- ทดสอบตัวแปลงบริการเว็บ การค้นหา และการดึงข้อมูลผ่านทั้งหมด

---

### Phase 8: Testing & Quality Gates (Days 27–29) — 7 tasks — เสร็จสมบูรณ์

**เป้าหมาย:** สร้างเกตคุณภาพ (quality gates) และการทดสอบที่ครอบคลุมสำหรับทุกเฟสที่ผ่านมา

| # | Task | File | deepseek-harness reference |
|---|------|------|---------------------------|
| 1 | ตั้งค่า typecheck และ lint สำหรับโครงการ Python ทั้งหมด | `pyproject.toml`, `Makefile` | `pnpm run typecheck`, `pnpm run lint` |
| 2 | เขียนทดสอบหน่วยสำหรับทุกเฟส ให้ครอบคลุมร้อยละ 100 ของไฟล์ต้นทาง | `tests/` | `pnpm run test:coverage` |
| 3 | สร้างการทดสอบ snapshot ที่เล่นเซสชันซ้ำโดยไม่ต้องใช้ API キーจริง | `tests/snapshot/` | `pnpm run test:snapshot` |
| 4 | ตั้งค่าการตรวจสอบคอนเวนชันการตั้งชื่อ รูปแบบโมดูล และ JSDoc/docstring | `scripts/verify_*` | `verify-export-jsdoc`, `verify-empty-catch` |
| 5 | ตรวจสอบว่าไม่มีการแปลงเป็น `unknown` และไม่มี catch ว่างเปล่าที่ไม่ระบุข้อผิดพลาด | `zcoder/` | No Unknown Casts (4.6), empty catch rule |
| 6 | สร้างสคริปต์ตรวจสอบคุณภาพที่รันก่อนการส่งโค้ดทุกครั้ง | `scripts/pre-push-checks.py` | `dsh-pre-push-checks` |
| 7 | ทดสอบการส่งโค้ดและตรวจสอบว่าเกตคุณภาพทั้งหมดผ่าน | `.github/workflows/` | CI pipeline |

**เกณฑ์การออก:**
- typecheck และ lint ตั้งค่าสำหรับโครงการ Python ทั้งหมด
- ทดสอบหน่วยครอบคลุมทุกเฟส ให้ครอบคลุมร้อยละ 100 ของไฟล์ต้นทาง
- การทดสอบ snapshot ที่เล่นเซสชันซ้ำโดยไม่ต้องใช้ API キーจริงทำงานได้
- การตรวจสอบคอนเวนชันการตั้งชื่อ รูปแบบโมดูล และ docstring ทำงานได้
- ไม่มีการแปลงเป็น `unknown` และไม่มี catch ว่างเปล่าที่ไม่ระบุข้อผิดพลาด
- สคริปต์ตรวจสอบคุณภาพรันก่อนการส่งโค้ดทุกครั้งและผ่านทั้งหมด
- การส่งโค้ดทดสอบยืนยันว่าเกตคุณภาพทั้งหมดผ่าน

---

### Phase 9: Deployment & Operations (Days 30–31) — 4 tasks — เสร็จสมบูรณ์

**เป้าหมาย:** ปรับใช้ระบบ ZCoder ที่อัปเกรดแล้วและตั้งค่าการดำเนินงาน (operations)

| # | Task | File | deepseek-harness reference |
|---|------|------|---------------------------|
| 1 | สร้างไฟล์คอนฟิกการปรับใช้สำหรับสภาพแวดล้อมจริง | `cordis.yml`, `.env.production` | cordis.yml configuration |
| 2 | ตั้งค่าการบันทึก Log การตรวจสอบสุขภาพ และการแจ้งเตือน | `zcoder/app/ops.py` | Logging and observability |
| 3 | สร้างเอกสารการปรับใช้และการดำเนินงานสำหรับทีมปฏิบัติการ | `docs/deployment.md` | Deployment runbook |
| 4 | ทำซ้อมการปรับใช้และตรวจสอบว่าระบบทำงานถูกต้องในสภาพแวดล้อมจริง | `scripts/deploy.py` | Deployment smoke test |

**เกณฑ์การออก:**
- ไฟล์คอนฟิกการปรับใช้สำหรับสภาพแวดล้อมจริงครบถ้วน
- การบันทึก Log การตรวจสอบสุขภาพ และการแจ้งเตือนทำงานได้
- เอกสารการปรับใช้และการดำเนินงานสำหรับทีมปฏิบัติการครบถ้วน
- การซ้อมการปรับใช้ยืนยันว่าระบบทำงานถูกต้องในสภาพแวดล้อมจริง

---

## สรุปการดำเนินงานรายสัปดาห์ (Weekly Summary)

ตารางด้านล่างนี้เชื่อมโยงสัปดาห์ที่ 1–5 กับเฟสและงานสำคัญ

| สัปดาห์ | วันที่ | เฟส | งานสำคัญ |
|--------|-------|------|----------|
| สัปดาห์ 1 | วันที่ 1–7 | Phase 0 (วันที่ 1–2) และ Phase 1 (วันที่ 3–5) | ประเมินช่องว่าง คอนฟิกที่พิมพ์ชนิด รอยต่อข้อมูลประจำตัว การตรวจสอบคอนฟิกเมื่อโหลด |
| สัปดาห์ 2 | วันที่ 8–14 | Phase 2 (วันที่ 6–8) และ Phase 3 (วันที่ 9–11) | ตัวแปลงผู้ให้บริการ LLM สตรีมแบบอะซิงโครนัส การยกเลิก ตัวควบคุมวงจรชีวิต |
| สัปดาห์ 3 | วันที่ 15–21 | Phase 4 (วันที่ 12–15) และ Phase 5 (วันที่ 16–19) | บันทึกเหตุการณ์เซสชัน ทะเบียนเครื่องมือ การดำเนินการที่ถูกควบคุม ผู้ฟังแบบน้ำตก |
| สัปดาห์ 4 | วันที่ 22–28 | Phase 6 (วันที่ 20–23) และ Phase 7 (วันที่ 24–26) | ระบบเอเจนต์เป็นทางการ ปลั๊กอิน รอยต่อความสามารถเว็บ/ค้นหา/ดึงข้อมูล |
| สัปดาห์ 5 | วันที่ 29–31 | Phase 8 (วันที่ 27–29) และ Phase 9 (วันที่ 30–31) | เกตคุณภาพ การทดสอบ การปรับใช้ การดำเนินงาน |

```

---
# ZCoder Big Upgrade Master Plan — Part 3: Detailed Feature Specifications

ภาคนี้อธิบายรายละเอียด specification ของฟีเจอร์หลักที่จะสร้างใน ZCoder Big Upgrade ข้อความอธิบายเขียนเป็นภาษาไทย ส่วนโค้ด เส้นทางไฟล์ ชื่อคลาส ชื่อฟังก์ชัน ชื่อตัวแปรสภาพแวดล้อม และชื่อแพ็กเกจเขียนเป็นภาษาอังกฤษ

## 6. Detailed Feature Specifications

### 6.1 Provider Connection (ProviderConnection)

`ProviderConnection` เก็บค่าการตั้งค่าการเชื่อมต่อกับผู้ให้บริการ LLM แต่ละราย เช่น DeepSeek, OpenAI, Google เป็น immutable datacast ที่ตรวจสอบความถูกต้องเมื่อสร้าง

```python
@dataclass(frozen=True)
class ProviderConnection:
    base_url: str
    auth_header: str  # "bearer" | "x-api-key" | "x-goog-api-key" | "none"
    env_keys: tuple[str, ...]
    default_model: str
    max_tokens: int = 4096
    timeout_seconds: int = 60
    retry_max_attempts: int = 4
```

Validation rules:
- `base_url` ต้องเป็น http/https เท่านั้น ห้ามมี credentials, query, หรือ fragment
- `max_tokens` ต้องเป็นจำนวนเต็มบวก
- `timeout_seconds` ต้องเป็นจำนวนบวกจำกัด (positive finite)

### 6.2 GenerateOptions

`GenerateOptions` กำหนดพารามิเตอร์สำหรับการสร้างข้อความจากโมเดลผ่านผู้ให้บริการที่เชื่อมต่อไว้

```python
@dataclass(frozen=True)
class GenerateOptions:
    provider: str
    model: str
    reasoning_effort: str | None
    messages: list[dict]
    system: str | None
    tools: list[dict] | None
    tool_history: list[dict] | None
    temperature: float | None
    max_tokens: int | None
    stop: list[str] | None
    signal: object | None
    session_id: str | None
    purpose: str | None
```


### 6.3 StreamChunk

`StreamChunk` แทนชิ้นข้อมูลหนึ่งชิ้นที่สตรีมกลับมาจากโมเดลระหว่างการสร้างข้อความ

```python
@dataclass(frozen=True)
class StreamChunk:
    type: str
    index: int
    text: str
    reason: str | None
    usage: dict | None
```


### 6.4 Session Event Types

เหตุการณ์ในเซสชันและฟิลด์ของเพย์โหลดที่มาพร้อมกัน พร้อมเครื่องหมายว่าสามารถเพิกเฉยได้หรือไม่ (ignorable)

| Event | Payload Fields | ignorable |
|-------|----------------|-----------|
| turn/start | turn_id, purpose, session_id | ไม่ |
| turn/end | turn_id, status, usage | ไม่ |
| step/start | step_id, turn_id, step_type | ไม่ |
| step/end | step_id, turn_id, status, usage | ไม่ |
| user/message | message_id, turn_id, content, role | ไม่ |
| developer/message | message_id, turn_id, content, role | ไม่ |
| system/message | message_id, turn_id, content, role | ไม่ |
| assistant/message | message_id, turn_id, content, role | ไม่ |
| assistant/attempt | attempt_id, turn_id, model, provider | ไม่ |
| tool/call | call_id, turn_id, tool_name, arguments | ไม่ |
| tool/result | call_id, turn_id, tool_name, result, error | ไม่ |
| request/header | request_id, headers | ใช่ |
| request/context | request_id, context_keys | ใช่ |
| session/end-seed | session_id, seed_value | ไม่ |


### 6.5 Error Codes

รหัสข้อผิดพลาด รหัสสถานะ HTTP ที่เกี่ยวข้อง และความหมาย

| Code | HTTP Status | Meaning |
|------|-------------|---------|
| AUTH | 401, 403 | การตรวจสอบสิทธิ์ล้มเหลว หรือโทเค็นไม่ถูกต้อง/หมดอายุ |
| QUOTA | 402, 429 | เกินโควต้า หรือการใช้งานเกินขีดจำกัดที่อนุญาต |
| RATE_LIMIT | 429 | ส่งคำขอบ่อยเกินไป ถูกจำกัดอัตราโดยผู้ให้บริการ |
| CONTEXT_WINDOW_EXCEEDED | 400 | ข้อความนำเข้ายาวเกินหน้าต่างบริบทของโมเดล |
| INVALID_REQUEST | 400, 413 | คำขอไม่ถูกต้อง หรือตัวใหญ่เกินขีดจำกัด |
| SERVER | 500+ | ข้อผิดพลาดภัทรเวิร์กของเซิร์ฟเวอร์ผู้ให้บริการ |
| MISSING_CREDENTIAL | N/A | ไม่พบข้อมูลรับรองที่จำเป็นในตัวแปรสภาพแวดล้อม |
| ABORTED | N/A | การดำเนินการถูกยกเลิกโดยผู้ใช้หรือระบบ |
| TIMEOUT | N/A | คำขอหมดเวลารอคำตอบจากผู้ให้บริการ |
# ZCoder Big Upgrade Master Plan — Part 4: Master Implementation Prompts

## บทนำ (Introduction)

เอกสารนี้คือ **Part 4** ของชุดแผนปรับปรุงครั้งใหญ่ของ ZCoder ("ZCoder Big Upgrade Master Plan") ประกอบด้วย **แปด Prompt หลักสำหรับนำไปใช้งานจริง (Master Implementation Prompts)** ที่เขียนขึ้นเพื่อให้วิศวกรหรือเอเจนต์นำไปคัดลอกและวาง (copy-paste) ให้กับเครื่องมือพัฒนาได้ทันที แต่ละ Prompt ถูกออกแบบให้เป็นบล็อกสมบูรณ์ที่เริ่มต้นด้วย "You are refactoring..." หรือ "You are adding..." และประกอบด้วยสี่ส่วนคือ **Context** (บริบท), **Current state** (สถานะปัจจุบัน), **Target state** (สถานะเป้าหมาย), **Constraints** (ข้อจำกัด), และ **Output** (ไฟล์ที่ต้องสร้างหรือแก้ไข)

ภาษาที่ใช้: ข้อความอธิบายเขียนเป็น **ภาษาไทย** โค้ด เส้นทางไฟล์ ชื่อคลาส ชื่อฟังก์ชัน ชื่อตัวแปรสภาพแวดล้อม ชื่อแพ็กเกจ เขียนเป็น **ภาษาอังกฤษ** ทั้งหมด

แปด Prompt ครอบคลุมแปดเฟสของการปรับปรุง:

1. **Phase 1 (Prompt 7.1)** — Typed Configuration & Credential Seam
2. **Phase 2 (Prompt 7.2)** — Provider Adapter Pattern
3. **Phase 3 (Prompt 7.3)** — Async Streaming & Cancellation
4. **Phase 4 (Prompt 7.4)** — Session Event Log
5. **Phase 5 (Prompt 7.5)** — Tool Registry & Guarded Execution
6. **Phase 6 (Prompt 7.6)** — Agent System Formalization
7. **Phase 7 (Prompt 7.7)** — Web / Search / Fetch Capability Seam
8. **Phase 8 (Prompt 7.8)** — Testing & Quality Gates

แต่ละเฟสถูกออกแบบให้ทำงานต่อเนื่องกัน ตั้งแต่การวางรากฐานเรื่อง credential และ configuration (Phase 1–2) การรองรับสตรีมแบบอะซิงโครนัสและการยกเลิก (Phase 3) การบันทึก	event log ของเซสชัน (Phase 4) ระบบเครื่องมือ (Phase 5) ระบบเอเจนต์ (Phase 6) ระบบค้นหาและดึงข้อมูลเว็บ (Phase 7) และสุดท้ายคือการทดสอบและประตูคุณภาพ (Phase 8)

---

## 7. Master Implementation Prompts

### Prompt 7.1 — Phase 1: Typed Configuration & Credential Seam

**Context**

ไฟล์ `src/zcoder/agent/orchestration/providers.py` ปัจจุบันมีฟังก์ชัน `resolve_api_key` และ `resolve_base_url` ที่คืนค่าเป็นสตริงธรรมดา เมื่อไม่พบ credential ฟังก์ชันจะคืนค่าสตริงว่าง `""` แทนที่จะล้มเหลวอย่างชัดเจน (fail loud) ทำให้ตัวเรียกใช้ไม่สามารถแยกแยะได้ว่าคีย์หายไปจริงหรือว่า provider อนุญาตให้ทำงานโดยไม่มีคีย์ เช่น ollama หรือ local นอกจากนี้ยังไม่มีคลาสข้อมูล typedd สำหรับตัวแทนการเชื่อมต่อ provider ทำให้การส่งค่าระหว่างชั้น configuration กับชั้น adapter เป็นไปอย่างหลวมตัว (loosely typed) และยากต่อการทดสอบหน่วย เป้าหมายของเฟสนี้คือการสร้าง seam ที่ชัดเจนระหว่างชั้น credential resolution กับชั้น provider adapter โดยยังคง `router.py` ไม่เปลี่ยนแปลงใน Prompt นี้

**Current state**

- `src/zcoder/agent/orchestration/providers.py` มีฟังก์ชัน `resolve_api_key(provider, cli_key=None)` ที่คืนค่า `str` เมื่อไม่พบคีย์จะคืนค่า `""`
- `src/zcoder/agent/orchestration/providers.py` มีฟังก์ชัน `resolve_base_url(provider, cli_base_url=None)` ที่คืนค่า `str` โดยใช้ค่าเริ่มต้น hardcoded เมื่อไม่มี env override
- `src/zcoder/agent/orchestration/providers.py` มี `PROVIDER_DEFAULTS` dict แบบ loose typing
- `src/zcoder/agent/orchestration/providers.py` มี `headers_for`, `build_payload`, `parse_response`, `endpoint_for` ที่จัดการ provider-typed logic ปนกันอยู่ในไฟล์เดียว
- `src/zcoder/agent/orchestration/router.py` เรียก `providers.resolve_api_key`, `providers.resolve_base_url`, `providers.headers_for` โดยตรง
- `tests/unit/` มีทดสอบ provider gateway อยู่แล้วแต่ยังไม่มี `tests/unit/test_providers.py` ที่ครอบคลุม credential resolution แบบ fail loud

**Target state**

- `src/zcoder/agent/orchestration/providers.py` มี frozen dataclass `ProviderConnection` ที่เก็บ `provider`, `api_key`, `base_url`, `headers` เป็น 필드가 type-checked
- `src/zcoder/agent/orchestration/providers.py` มี exception `MissingCredentialError` (สืบทอดจาก `ZCoderError`, `error_code = "MISSING_CREDENTIAL"`) ที่ถูกยกเมื่อ provider ต้องการ credential แต่ไม่พบ
- `resolve_api_key` ถูกเขียนใหม่ให้ fail loud: ถ้า provider ต้องการ credential และไม่พบคีย์ทั้งจาก CLI และ env ให้ยก `MissingCredentialError` (ยกเว้น provider ที่อนุญาตให้ไม่มีคีย์ เช่น `local`, `ollama`)
- `resolve_base_url` ถูกเขียนใหม่ให้มี strict validation: scheme ต้องเป็น http/https เท่านั้น ห้ามมี credentials/query/fragment ใน URL hostname ต้องมี ถ้าไม่ผ่านให้ยก `ValueError`
- `router.py` ยังคงไม่เปลี่ยนแปลงใน Prompt นี้ (ยังเรียกฟังก์ชันเดิมได้อยู่)
- มีไฟล์ทดสอบ `tests/unit/test_providers.py` ครอบคลุมกรณี credential พบ/ไม่พบ, base_url ถูก/ผิด, provider แต่ละชนิด

**Constraints**

- `ProviderConnection` ต้องเป็น frozen dataclass (immutable หลังสร้าง)
- `MissingCredentialError` ต้องสืบทอดจาก `zcoder.core.exceptions.ZCoderError` และมี `error_code = "MISSING_CREDENTIAL"`
- `resolve_api_key` ต้องไม่คืนค่า `""` สำหรับ provider ที่ต้องการ credential แต่ไม่พบ ต้องยก exception แทน
- provider `local` และ `ollama` อนุญาตให้ทำงานโดยไม่มี API key (คืนค่า `""` ได้)
- `resolve_base_url` ต้องปฏิเสธ scheme ที่ไม่ใช่ http/httpps (เช่น `file://`, `ftp://`)
- `resolve_base_url` ต้องปฏิเสธ URL ที่มี userinfo (username/password), query string, หรือ fragment
- `router.py` ต้องไม่ถูกแก้ไขใน Prompt นี้
- โค้ดใหม่ทั้งหมดต้องผ่าน mypy strict และ ruff lint
- ต้องมีทดสอบหน่วยใน `tests/unit/test_providers.py`

**Output**

- สร้าง/แก้ไข `src/zcoder/agent/orchestration/providers.py` — เพิ่ม `ProviderConnection`, `MissingCredentialError`, เขียนใหม่ `resolve_api_key`, `resolve_base_url`
- สร้าง `tests/unit/test_providers.py` — ทดสอบ credential resolution และ base URL validation

---

### Prompt 7.2 — Phase 2: Provider Adapter Pattern

**Context**

หลังจาก Phase 1 วางรากฐาน credential seam แล้ว เฟสนี้จะแยก logic เฉพาะ provider ออกจาก `router.py` มาอยู่ใน adapter pattern ที่ชัดเจน `router.py` ปัจจุบันมี `build_payload` และ `parse_response` ที่ฝังอยู่ใน `providers.py` และมีการสร้าง HTTP request โดยตรงผ่าน `urllib.request` ภายใน `_call` ทำให้ยากต่อการขยาย provider ใหม่ การทดสอบ และการ mock เป้าหมายคือสร้าง `ProviderResult` และ `ProviderAdapter` abstract base class ใน `adapter.py` สร้าง adapter แยกต่อ provider (openai_compatible, anthropic, gemini, ollama, local) สร้าง `registry.py` สำหรับจดทะเบียนและค้นหา adapter และทำให้ `router.py _call` delegate ไปยัง adapter แทนที่จะเรียก `build_payload/parse_response` โดยตรง รวมถึงกำหนด error codes มาตรฐาน: AUTH, QUOTA, RATE_LIMIT, CONTEXT_WINDOW_EXCEEDED, INVALID_REQUEST, SERVER

**Current state**

- `src/zcoder/agent/orchestration/providers.py` มี `build_payload` และ `parse_response` ที่จัดการ provider-typed logic แบบ inline
- `src/zcoder/agent/orchestration/router.py` ฟังก์ชัน `_call` สร้าง `urllib.request.Request` โดยตรง เรียก `providers.build_payload`, `providers.endpoint_for`, `providers.parse_response`, `providers.headers_for`
- `src/zcoder/agent/orchestration/router.py` มี `_nvidia_model_chain` และ `_is_model_fallback_error` ที่จัดการ model fallback ภายใน router
- ยังไม่มี `adapter.py`, `registry.py`, `openai_compatible.py`, `anthropic.py`, `gemini.py`, `ollama.py`, `local.py`
- ยังไม่มี error code taxonomy มาตรฐาน (AUTH, QUOTA, RATE_LIMIT, CONTEXT_WINDOW_EXCEEDED, INVALID_REQUEST, SERVER)
- `tests/unit/` ยังไม่มี `tests/unit/test_adapters.py`

**Target state**

- `src/zcoder/agent/orchestration/adapter.py` มี `ProviderResult` dataclass และ `ProviderAdapter` abstract base class พร้อมเมธertid `execute(payload) -> ProviderResult`
- `src/zcoder/agent/orchestration/openai_compatible.py` มี `OpenAICompatibleAdapter` สืบทอดจาก `ProviderAdapter`
- `src/zcoder/agent/orchestration/anthropic.py` มี `AnthropicAdapter` สืบทอดจาก `ProviderAdapter`
- `src/zcoder/agent/orchestration/gemini.py` มี `GeminiAdapter` สืบทอดจาก `ProviderAdapter`
- `src/zcoder/agent/orchestration/ollama.py` มี `OllamaAdapter` สืบทอดจาก `ProviderAdapter`
- `src/zcoder/agent/orchestration/local.py` มี `LocalAdapter` สืบทอดจาก `ProviderAdapter`
- `src/zcoder/agent/orchestration/registry.py` มี `AdapterRegistry` สำหรับ `register(provider, adapter)` และ `get(provider) -> ProviderAdapter`
- `src/zcoder/agent/orchestration/router.py` `_call` delegate ไปยัง `AdapterRegistry.get(provider).execute(payload)` แทนการเรียก `build_payload/parse_response` โดยตรง
- `src/zcoder/agent/orchestration/providers.py` ลบ `build_payload` และ `parse_response` ออก (ย้ายไปอยู่ใน adapter แต่ละตัว)
- มี error codes มาตรฐาน: AUTH, QUOTA, RATE_LIMIT, CONTEXT_WINDOW_EXCEEDED, INVALID_REQUEST, SERVER
- มี `tests/unit/test_adapters.py` ครอบคลุม adapter แต่ละตัวและ registry

**Constraints**

- `ProviderAdapter` ต้องเป็น abstract base class (ใช้ `abc.ABC` หรือ `@abstractmethod`)
- `ProviderResult` ต้องเป็น dataclass ที่มีอย่างน้อย `content: str`, `raw: dict`, `provider: str`, `model: str`
- แต่ละ adapter ต้องจัดการ payload format และ response parsing เฉพาะตัวของ provider นั้น
- `router.py _call` ต้องไม่เรียก `providers.build_payload` หรือ `providers.parse_response` อีกต่อไป
- `router.py` ต้องยังคงรองรับ NVIDIA model chain fallback เหมือนเดิมผ่าน adapter
- Error codes ต้องใช้สตริงคงที่: `"AUTH"`, `"QUOTA"`, `"RATE_LIMIT"`, `"CONTEXT_WINDOW_EXCEEDED"`, `"INVALID_REQUEST"`, `"SERVER"`
- adapter ที่ไม่พบใน registry ต้องยก `KeyError` หรือ exception ที่ชัดเจน
- โค้ดใหม่ทั้งหมดต้องผ่าน mypy strict และ ruff lint
- ต้องมีทดสอบหน่วยใน `tests/unit/test_adapters.py`

**Output**

- สร้าง `src/zcoder/agent/orchestration/adapter.py` — `ProviderResult`, `ProviderAdapter` abstract base
- สร้าง `src/zcoder/agent/orchestration/openai_compatible.py` — `OpenAICompatibleAdapter`
- สร้าง `src/zcoder/agent/orchestration/anthropic.py` — `AnthropicAdapter`
- สร้าง `src/zcoder/agent/orchestration/gemini.py` — `GeminiAdapter`
- สร้าง `src/zcoder/agent/orchestration/ollama.py` — `OllamaAdapter`
- สร้าง `src/zcoder/agent/orchestration/local.py` — `LocalAdapter`
- สร้าง `src/zcoder/agent/orchestration/registry.py` — `AdapterRegistry`
- แก้ไข `src/zcoder/agent/orchestration/providers.py` — ลบ `build_payload`, `parse_response`
- แก้ไข `src/zcoder/agent/orchestration/router.py` — `_call` delegate ไปยัง adapter registry
- สร้าง `tests/unit/test_adapters.py` — ทดสอบ adapter แต่ละตัวและ registry

---

### Prompt 7.3 — Phase 3: Async Streaming & Cancellation

**Context**

หลังจาก Phase 2 แยก provider logic ออกเป็น adapter แล้ว เฟสนี้จะยกระดับการเรียก model จาก synchronous request/response มาเป็น **async streaming** พร้อมระบบ **cancellation** ปัจจุบัน `router.py _call` เป็น synchronous function ที่รอ response ทั้งก่อนจึงคืนค่า ทำให้ไม่สามารถแสดงผลแบบเรียลไทม์ (streaming) และไม่สามารถยกเลิกคำขอที่ค้างอยู่ได้ เป้าหมายคือสร้าง `timeout.py` พร้อม `IdleWatchdog` สำหรับตรวจจับการไม่มีกิจกรรม (idle timeout), `cancellation.py` พร้อม `AbortSignal` สำหรับการยกเลิกคำขอ, `types.py` พร้อม `StreamChunk` และ `GenerateOptions` แล้วเขียนใหม่ `adapter execute()` เป็น async generators และ `router.py _call` เป็น async generator ที่ yield `StreamChunk` รวมถึงกำหนด redirect policy ว่าเมื่อเกิดข้อผิดพลาดให้ส่งเป็น `'error'` chunk ไม่ใช่การยก exception

**Current state**

- `src/zcoder/agent/orchestration/router.py` ฟังก์ชัน `_call` เป็น synchronous function คืนค่า `dict`
- `src/zcoder/agent/orchestration/adapter.py` (จาก Phase 2) มี `ProviderAdapter.execute(payload) -> ProviderResult` แบบ synchronous
- ยังไม่มี `timeout.py`, `cancellation.py`, `types.py` ใน `src/zcoder/agent/orchestration/`
- ยังไม่มี `StreamChunk`, `GenerateOptions`, `AbortSignal`, `IdleWatchdog`
- ยังไม่มี redirect policy สำหรับข้อผิดพลาดในสตรีม
- `tests/unit/` ยังไม่มี `tests/unit/test_streaming.py`

**Target state**

- `src/zcoder/agent/orchestration/timeout.py` มีคลาส `IdleWatchdog` ที่เริ่มจับเวลาเมื่อไม่มีกิจกรรมและยกเลิกเมื่อเกินเวลาที่กำหนด
- `src/zcoder/agent/orchestration/cancellation.py` มีคลาส `AbortSignal` ที่ใช้ส่งสัญญาณยกเลิกคำขอระหว่างการสตรีม
- `src/zcoder/agent/orchestration/types.py` มี `StreamChunk` dataclass (มี `type`, `content`, `delta`, `done`, `error` ฯลฯ) และ `GenerateOptions` dataclass (มี `temperature`, `max_tokens`, `top_p`, `stream`, ฯลฯ)
- `src/zcoder/agent/orchestration/adapter.py` `ProviderAdapter.execute()` ถูกเขียนใหม่เป็น async generator ที่ `yield StreamChunk`
- `src/zcoder/agent/orchestration/router.py` `_call` ถูกเขียนใหม่เป็น async generator ที่ `yield StreamChunk` และ delegate ไปยัง adapter
- redirect policy: เมื่อเกิดข้อผิดพลาดระหว่างสตรีม ให้ `yield` chunk ที่มี `type = "error"` แทนที่จะยก exception ออกไปนอก generator
- มี `tests/unit/test_streaming.py` ครอบคลุม idle watchdog, abort signal, streaming chunks, error redirect

**Constraints**

- `StreamChunk` ต้องเป็น dataclass ที่มีฟิลด์อย่างน้อย `type: str`, `content: str`, `done: bool`
- `GenerateOptions` ต้องเป็น dataclass ที่มีฟิลด์สำหรับ sampling parameters
- `AbortSignal` ต้องรองรับการตั้งค่า `aborted: bool` และการตรวจสอบสถานะ
- `IdleWatchdog` ต้องเริ่มจับเวลาเมื่อไม่มีกิจกรรมและยกเลิกเมื่อเกิน timeout
- adapter `execute()` ต้องเป็น async generator (ใช้ `async def` + `yield`)
- router `_call` ต้องเป็น async generator (ใช้ `async def` + `yield`)
- ข้อผิดพลาดในสตรีมต้องถูกส่งเป็น chunk `{"type": "error", ...}` ไม่ใช่การยก exception
- โค้ดใหม่ทั้งหมดต้องผ่าน mypy strict และ ruff lint
- ต้องมีทดสอบหน่วยใน `tests/unit/test_streaming.py`

**Output**

- สร้าง `src/zcoder/agent/orchestration/timeout.py` — `IdleWatchdog`
- สร้าง `src/zcoder/agent/orchestration/cancellation.py` — `AbortSignal`
- สร้าง `src/zcoder/agent/orchestration/types.py` — `StreamChunk`, `GenerateOptions`
- แก้ไข `src/zcoder/agent/orchestration/adapter.py` — `execute()` เป็น async generator ยield `StreamChunk`
- แก้ไข `src/zcoder/agent/orchestration/router.py` — `_call` เป็น async generator ยield `StreamChunk`, redirect error เป็น chunk type `"error"`
- สร้าง `tests/unit/test_streaming.py` — ทดสอบ streaming, cancellation, error redirect

---

### Prompt 7.4 — Phase 4: Session Event Log

**Context**

หลังจาก Phase 3 รองรับสตรีมแบบอะซิงโครนัสแล้ว เฟสนี้จะสร้างระบบบันทึก event log ของเซสชัน (session event log) ซึ่งเป็นข้อกำหนดสำคัญ: สิ่งใดก็ตามที่ส่งถึงโมเดล (model-visible input) ต้องสามารถสร้างซ้ำจากเซสชันล็อกได้ เป้าหมายคือสร้าง `session_log.py` พร้อม `SESSION_FORMAT_VERSION = 4`, enum ของชนิด event, และ `SessionEventStore` ที่เก็บข้อมูลใน SQLite พร้อมเมธertid `append`, `get_events`, `snapshot_events` จากนั้นต้อง instrument `router.py` เพื่อบันทึก request/header และ assistant/message ลงใน event store Events ที่เป็น optional ให้แท็ก `ignorable = True` เพื่อให้ผู้อ่านรุ่นเก่าสามารถข้ามไปได้อย่างปลอดภัย

**Current state**

- ยังไม่มี `src/zcoder/agent/orchestration/session_log.py`
- ยังไม่มี `SESSION_FORMAT_VERSION` สำหรับ session event log
- ยังไม่มี enum ของชนิด session event
- ยังไม่มี `SessionEventStore` ที่ใช้ SQLite persistence
- `src/zcoder/agent/orchestration/router.py` ยังไม่บันทึก event ใด ๆ ลงใน event store
- ยังไม่มีแนวคิด `ignorable = True` สำหรับ optional events
- `tests/unit/` ยังไม่มี `tests/unit/test_session_log.py`

**Target state**

- `src/zcoder/agent/orchestration/session_log.py` มีค่าคงที่ `SESSION_FORMAT_VERSION = 4`
- `src/zcoder/agent/orchestration/session_log.py` มี enum ของชนิด event (เช่น `request`, `header`, `assistant_message`, `tool_call`, ฯลฯ)
- `src/zcoder/agent/orchestration/session_log.py` มีคลาส `SessionEventStore` ที่ใช้ SQLite สำหรับ persistence
- `SessionEventStore.append(event)` เพิ่ม event ใหม่ลงในฐานข้อมูล
- `SessionEventStore.get_events(session_id)` ดึง event ทั้งหมดของเซสชัน
- `SessionEventStore.snapshot_events(session_id)` สร้าง snapshot ของ event ในเซสชัน
- `src/zcoder/agent/orchestration/router.py` instrumented เพื่อบันทึก request/header และ assistant/message ลงใน event store
- Optional events ถูกแท็ก `ignorable = True`
- มี `tests/unit/test_session_log.py` ครอบคลุมการ append, get_events, snapshot_events, และ SQLite persistence

**Constraints**

- `SESSION_FORMAT_version` ต้องมีค่าเท่ากับ `4`
- `SessionEventStore` ต้องใช้ SQLite เป็น backend สำหรับ persistence
- `append`, `get_events`, `snapshot_events` ต้องเป็นเมธertidหลักของ `SessionEventStore`
- Event ที่เป็น optional ต้องมีฟิลด์ `ignorable: bool = True`
- `router.py` ต้องบันทึก request event (พร้อม header) และ assistant/message event สำหรับทุกคำขอ
- เซสชันล็อกต้องสามารถสร้างซ้ำ model-visible input ได้ทั้งหมด
- โค้ดใหม่ทั้งหมดต้องผ่าน mypy strict และ ruff lint
- ต้องมีทดสอบหน่วยใน `tests/unit/test_session_log.py`

**Output**

- สร้าง `src/zcoder/agent/orchestration/session_log.py` — `SESSION_FORMAT_VERSION = 4`, event type enum, `SessionEventStore` with SQLite
- แก้ไข `src/zcoder/agent/orchestration/router.py` — instrument บันทึก request/header และ assistant/message events
- สร้าง `tests/unit/test_session_log.py` — ทดสอบ session event store และ instrument

---

### Prompt 7.5 — Phase 5: Tool Registry & Guarded Execution

**Context**

หลังจาก Phase 4 มี session event log แล้ว เฟสนี้จะสร้างระบบรีจิสทรีเครื่องมือ (tool registry) พร้อมการทำงานแบบถูกกัน (guarded execution) เป้าหมายคือสร้าง `tools.py` พร้อม `ToolRegistry`, `ToolDefinition`, `ValueSchemaSpec` DSL, และ `ToolExecutionPipeline` รองรับ waterfall events (pre-execute/execute/post-execute) และ emit events (result/change) รวมถึงฟังก์ชัน `executeToolBatch` ที่รองรับการทำงานพร้อมกัน (concurrency) และ barriers ต่อมาลงทะเบียนเครื่องมือ `web_search` และ `code_execution` และ integrate เข้ากับ `router.py`

**Current state**

- ยังไม่มี `src/zcoder/agent/orchestration/tools.py`
- ยังไม่มี `ToolRegistry`, `ToolDefinition`, `ValueSchemaSpec`, `ToolExecutionPipeline`
- ยังไม่มี waterfall events สำหรับเครื่องมือ (pre-execute/execute/post-execute)
- ยังไม่มี `executeToolBatch` สำหรับการทำงานพร้อมกัน
- ยังไม่มีเครื่องมือ `web_search` และ `code_execution` ที่ลงทะเบียน
- `src/zcoder/agent/orchestration/router.py` ยังไม่มีการ integrate tool execution
- `tests/unit/` ยังไม่มี `tests/unit/test_tools.py`

**Target state**

- `src/zcoder/agent/orchestration/tools.py` มีคลาส `ToolRegistry` สำหรับลงทะเบียนและค้นหาเครื่องมือ
- `src/zcoder/agent/orchestration/tools.py` มีคลาส `ToolDefinition` ที่กำหนด name, description, parameter schema
- `src/zcoder/agent/orchestration/tools.py` มี `ValueSchemaSpec` DSL สำหรับกำหนด schema ของพารามิเตอร์
- `src/zcoder/agent/orchestration/tools.py` มีคลาส `ToolExecutionPipeline` ที่รองรับ waterfall events (pre-execute/execute/post-execute)
- `ToolExecutionPipeline` รองรับ emit events (result/change)
- `src/zcoder/agent/orchestration/tools.py` มีฟังก์ชัน `executeToolBatch` ที่รองรับ concurrency และ barriers
- ลงทะเบียนเครื่องมือ `web_search` และ `code_execution`
- `src/zcoder/agent/orchestration/router.py` integrate tool execution pipeline เข้ากับการเรียก model
- มี `tests/unit/test_tools.py` ครอบคลุม registry, definition, pipeline, executeToolBatch

**Constraints**

- `ToolRegistry` ต้องมีเมธertid `register`, `get`, `list`
- `ToolDefinition` ต้องมีฟิลด์ `name`, `description`, `parameters` (ValueSchemaSpec)
- `ValueSchemaSpec` ต้องเป็น DSL ที่สามารถกำหนด type, required fields, constraints ได้
- `ToolExecutionPipeline` ต้องรองรับ waterfall events: pre-execute, execute, post-execute
- `ToolExecutionPipeline` ต้องรองรับ emit events: result, change
- `executeToolBatch` ต้องรองรับการทำงานพร้อมกัน (concurrency) และ barriers
- เครื่องมือ `web_search` และ `code_execution` ต้องถูกลงทะเบียนใน registry
- `router.py` ต้อง integrate tool execution pipeline
- โค้ดใหม่ทั้งหมดต้องผ่าน mypy strict และ ruff lint
- ต้องมีทดสอบหน่วยใน `tests/unit/test_tools.py`

**Output**

- สร้าง `src/zcoder/agent/orchestration/tools.py` — `ToolRegistry`, `ToolDefinition`, `ValueSchemaSpec`, `ToolExecutionPipeline`, `executeToolBatch`
- ลงทะเบียน `web_search`, `code_execution` ใน tool registry
- แก้ไข `src/zcoder/agent/orchestration/router.py` — integrate tool execution pipeline
- สร้าง `tests/unit/test_tools.py` — ทดสอบ tool registry, pipeline, executeToolBatch

---

### Prompt 7.6 — Phase 6: Agent System Formalization

**Context**

หลังจาก Phase 5 มี tool registry แล้ว เฟสนี้จะ formalize ระบบเอเจนต์ (agent system) ให้เป็นโครงสร้างที่ชัดเจน เป้าหมายคือสร้าง `agents.py` พร้อม `AgentRegistry` ที่มีเมธertid `create`, `resume`, `register`, `enter`, `announce`, `setFactory`, `get`, `list`, `turnBoundaryOf` และ `Agent` handle ที่มี `id`, `options`, `session`, `model`, `inbox`, `status`, `cancel`, `whenIdle`, `runMaintenance`, `send`, `followup`, `steer`, `inject` รวมถึง `ModelSelection` type, projections (`modelSelectionProjectionDefinition`, `turnBoundaryProjectionDefinition`), agent/* events, และ initiator scope (`withInitiator`, `withoutInitiator`)

**Current state**

- ยังไม่มี `src/zcoder/agent/orchestration/agents.py`
- ยังไม่มี `AgentRegistry`, `Agent` handle, `ModelSelection` type
- ยังไม่มี projections (`modelSelectionProjectionDefinition`, `turnBoundaryProjectionDefinition`)
- ยังไม่มี agent/* events
- ยังไม่มี initiator scope (`withInitiator`, `withoutInitiator`)
- `tests/unit/` ยังไม่มี `tests/unit/test_agents.py`

**Target state**

- `src/zcoder/agent/orchestration/agents.py` มีคลาส `AgentRegistry` พร้อมเมธertid `create`, `resume`, `register`, `enter`, `announce`, `setFactory`, `get`, `list`, `turnBoundaryOf`
- `src/zcoder/agent/orchestration/agents.py` มีคลาส `Agent` handle พร้อม `id`, `options`, `session`, `model`, `inbox`, `status`, `cancel`, `whenIdle`, `runMaintenance`, `send`, `followup`, `steer`, `inject`
- `src/zcoder/agent/orchestration/agents.py` มี type `ModelSelection`
- `src/zcoder/agent/orchestration/agents.py` มี projections: `modelSelectionProjectionDefinition`, `turnBoundaryProjectionDefinition`
- `src/zcoder/agent/orchestration/agents.py` กำหนด agent/* events
- `src/zcoder/agent/orchestration/agents.py` รองรับ initiator scope: `withInitiator`, `withoutInitiator`
- มี `tests/unit/test_agents.py` ครอบคลุม registry, agent handle, projections, events, initiator scope

**Constraints**

- `AgentRegistry.create()` ต้องสร้าง agent ใหม่และคืนค่า `Agent` handle
- `AgentRegistry.resume()` ต้องคืน agent ที่มีอยู่แล้วจาก session
- `AgentRegistry.register()` ต้องลงทะเบียน agent factory
- `AgentRegistry.enter()` / `announce()` ต้องจัดการการเข้าและประกาศ agent ในเซสชัน
- `AgentRegistry.setFactory()` ต้องตั้งค่า factory สำหรับสร้าง agent
- `AgentRegistry.get()` / `list()` ต้องคืน agent หรือรายการ agent
- `AgentRegistry.turnBoundaryOf()` ต้องคืน turn boundary ของ agent
- `Agent` handle ต้องมี `id`, `options`, `session`, `model`, `inbox`, `status`
- `Agent.cancel()` ต้องยกเลิก agent, `whenIdle()` ต้องรอจนกว่าจะว่าง, `runMaintenance()` ต้องรันบำรุงรักษา
- `Agent.send()` / `followup()` / `steer()` / `inject()` ต้องส่งข้อความหรือคำสั่งไปยัง agent
- `ModelSelection` ต้องเป็น type ที่กำหนดวิธีเลือกโมเดลสำหรับ agent
- projections ต้องใช้สำหรับการ query สถานะ agent จาก event store
- agent/* events ต้องถูกกำหนดเป็น event types ใน session log
- `withInitiator` / `withoutInitiator` ต้องเป็น scope สำหรับกรอง eventi ตามผู้เริ่มต้น
- โค้ดใหม่ทั้งหมดต้องผ่าน mypy strict และ ruff lint
- ต้องมีทดสอบหน่วยใน `tests/unit/test_agents.py`

**Output**

- สร้าง `src/zcoder/agent/orchestration/agents.py` — `AgentRegistry`, `Agent`, `ModelSelection`, projections, agent/* events, initiator scope
- สร้าง `tests/unit/test_agents.py` — ทดสอบ agent registry, handle, projections, events, initiator scope

---

### Prompt 7.7 — Phase 7: Web / Search / Fetch Capability Seam

**Context**

หลังจาก Phase 6 formalize ระบบเอเจนต์แล้ว เฟสนี้จะสร้าง capability seam สำหรับเว็บไซต์ การค้นหา และการดึงข้อมูล (web/search/fetch) เป้าหมายคือสร้าง `web.py` พร้อม `WebRuntime` ที่มีเมธertid `registerSearchProvider`, `registerFetchProvider`, `search`, `fetch`, `listProviders`, `searchReady`, `fetchReady` รวมถึง searchBilling rules (auto/account/api-key) จากนั้นสร้างเครื่องมือ `web_search` (จำกัดสูงสุด 10 queries, rate-limited) และ `web_fetch` (แปลง HTML เป็น markdown ผ่าน turndown, จำกัด 200K) และ integrate เข้ากับระบบ tool registry จาก Phase 5

**Current state**

- ยังไม่มี `src/zcoder/agent/orchestration/web.py`
- ยังไม่มี `WebRuntime`, `registerSearchProvider`, `registerFetchProvider`
- ยังไม่มี searchBilling rules (auto/account/api-key)
- ยังไม่มีเครื่องมือ `web_search` และ `web_fetch`
- ยังไม่มีการแปลง HTML เป็น markdown ผ่าน turndown
- `tests/unit/` ยังไม่มี `tests/unit/test_web.py`

**Target state**

- `src/zcoder/agent/orchestration/web.py` มีคลาส `WebRuntime` พร้อมเมธertid `registerSearchProvider`, `registerFetchProvider`, `search`, `fetch`, `listProviders`, `searchReady`, `fetchReady`
- `src/zcoder/agent/orchestration/web.py` มี searchBilling rules: `auto`, `account`, `api-key`
- สร้างเครื่องมือ `web_search` จำกัดสูงสุด 10 queries ต่อคำขอ และ rate-limited
- สร้างเครื่องมือ `web_fetch` แปลง HTML เป็น markdown ผ่าน turndown จำกัดขนาด 200K
- `web_search` และ `web_fetch` ถูกลงทะเบียนใน tool registry จาก Phase 5
- มี `tests/unit/test_web.py` ครอบคลุม WebRuntime, search/fetch, searchBilling, web_search, web_fetch

**Constraints**

- `WebRuntime.registerSearchProvider(name, provider)` ต้องลงทะเบียน search provider
- `WebRuntime.registerFetchProvider(name, provider)` ต้องลงทะเบียน fetch provider
- `WebRuntime.search(query, ...)` ต้องค้นหาผ่าน search provider ที่ลงทะเบียน
- `WebRuntime.fetch(url, ...)` ต้องดึงข้อมูลผ่าน fetch provider ที่ลงทะเบียน
- `WebRuntime.listProviders()` ต้องคืนรายชื่อ provider ที่ลงทะเบียน
- `WebRuntime.searchReady()` / `fetchReady()` ต้องตรวจสอบว่าพร้อมใช้งานหรือไม่
- searchBilling ต้องมีโหมด `auto`, `account`, `api-key`
- `web_search` ต้องจำกัดสูงสุด 10 queries ต่อคำขอ
- `web_search` ต้อง rate-limited
- `web_fetch` ต้องแปลง HTML เป็น markdown ผ่าน turndown
- `web_fetch` ต้องจำกัดขนาดสูงสุด 200K (200,000 bytes)
- โค้ดใหม่ทั้งหมดต้องผ่าน mypy strict และ ruff lint
- ต้องมีทดสอบหน่วยใน `tests/unit/test_web.py`

**Output**

- สร้าง `src/zcoder/agent/orchestration/web.py` — `WebRuntime`, searchBilling rules, `registerSearchProvider`, `registerFetchProvider`, `search`, `fetch`, `listProviders`, `searchReady`, `fetchReady`
- สร้างเครื่องมือ `web_search` (max 10 queries, rate-limited)
- สร้างเครื่องมือ `web_fetch` (HTML→markdown via turndown, 200K cap)
- ลงทะเบียน `web_search`, `web_fetch` ใน tool registry
- สร้าง `tests/unit/test_web.py` — ทดสอบ WebRuntime, search/fetch, searchBilling, web_search, web_fetch

---

### Prompt 7.8 — Phase 8: Testing & Quality Gates

**Context**

หลังจากทุกเฟสเสร็จสมบูรณ์ เฟสสุดท้ายจะเสริมความแข็งแกร่งด้านการทดสอบและประตูคุณภาพ (quality gates) เป้าหมายคือเขียนทดสอบหน่วยสำหรับ providers/router/auth (`test_providers.py`), CredentialResolver (`test_credentials.py`), ToolRegistry (`test_tools.py`), SessionEventStore (`test_session_log.py`) รวมถึงทดสอบ integration สำหรับ full flow (`test_full_flow.py`) จากนั้นปรับค่า `fail_under` ใน `pyproject.toml` จาก 70 เป็น 85 และเพิ่ม pre-commit hook สำหรับ ruff และ mypy ในไฟล์ `.pre-commit-config.yaml`

**Current state**

- `pyproject.toml` มี `[tool.coverage.report] fail_under = 70`
- ยังไม่มีไฟล์ `.pre-commit-config.yaml`
- มีทดสอบหน่วยบางส่วนใน `tests/unit/` แต่ยังไม่ครอบคลุม providers, credentials, tools, session_log อย่างครบถ้วน
- ยังไม่มี integration test สำหรับ full flow (`test_full_flow.py`)

**Target state**

- มีทดสอบหน่วย `tests/unit/test_providers.py` ครอบคลุม providers/router/auth
- มีทดสอบหน่วย `tests/unit/test_credentials.py` ครอบคลุม CredentialResolver
- มีทดสอบหน่วย `tests/unit/test_tools.py` ครอบคลุม ToolRegistry
- มีทดสอบหน่วย `tests/unit/test_session_log.py` ครอบคลุม SessionEventStore
- มีทดสอบ integration `tests/unit/test_full_flow.py` ครอบคลุมการทำงานทั้งระบบแบบ end-to-end
- `pyproject.toml` `[tool.coverage.report] fail_under` ถูกเปลี่ยนจาก 70 เป็น 85
- มีไฟล์ `.pre-commit-config.yaml` ที่มี pre-commit hook สำหรับ ruff และ mypy

**Constraints**

- `fail_under` ต้องมีค่าเท่ากับ 85 (เพิ่มขึ้นจาก 70)
- `.pre-commit-config.yaml` ต้องมี hook สำหรับ ruff (lint + format) และ mypy (type check)
- integration test `test_full_flow.py` ต้องทดสอบการทำงานร่วมกันของทุกเฟส (credential → adapter → streaming → session log → tools → agents → web)
- ทดสอบทั้งหมดต้องรันผ่าน pytest
- โค้ดใหม่ทั้งหมดต้องผ่าน mypy strict และ ruff lint

**Output**

- สร้าง `tests/unit/test_providers.py` — ทดสอบ providers/router/auth
- สร้าง `tests/unit/test_credentials.py` — ทดสอบ CredentialResolver
- สร้าง `tests/unit/test_tools.py` — ทดสอบ ToolRegistry
- สร้าง `tests/unit/test_session_log.py` — ทดสอบ SessionEventStore
- สร้าง `tests/unit/test_full_flow.py` — integration test สำหรับ full flow
- แก้ไข `pyproject.toml` — เปลี่ยน `fail_under` จาก 70 เป็น 85
- สร้าง `.pre-commit-config.yaml` — pre-commit hook สำหรับ ruff และ mypy

---

# ZCoder Big Upgrade Master Plan — Part 5: Risk Assessment, Rollback & Immediate Actions

## 8. Risk Assessment & Rollback

| Risk | Impact | Mitigation |
|------|--------|------------|
| เปลี่ยน resolve_api_key() แล้วโค้ดเดิมที่คาดหวังค่าว่างจะพัง | สูง | ทำทีละผู้ให้บริการ ทดสอบแต่ละรายก่อนไปรายถัดไป |
| เปลี่ยนเป็น async/await แล้วโค้ดซิงโครนัสเดิมใช้ไม่ได้ | สูง | ค่อยๆ เปลี่ยนทีละฟังก์ชัน ใช้ asyncio.run() จุดเดียวที่จุดเข้าโปรแกรม |
| ลืมอัปเดตเอกสารเมื่อเปลี่ยนพฤติกรรม | กลาง | อัปเดต CHANGELOG.md และ AGENTS.md ทุกครั้งที่เปลี่ยนพฤติกรรมที่ผู้ใช้เห็น |
| การทดสอบเดิมผิดพลาดหลังปรับปรุง | กลาง | รันทดสอบเดิมทุกครั้งหลังแก้ไขเสร็จแต่ละเฟส |
| ข้อมูลประจำตัวรั่วไหลลง log | สูง | ห้ามบันทึกคีย์หรือโทเค็นในผลลัพธ์ข้อผิดพลาด ใช้ ignorable: true กับเหตุการณ์ที่มีความลับ |
| การยกเลิกคำขอทำให้ state แตก | กลาง | ออกแบบให้การยกเลิกเป็น atomic ทีละ operation |

### Rollback Plan

1. `git checkout main` เพื่อกลับสู่สภาพเดิม
2. สร้างสาขาใหม่จากจุดที่ผ่านการทดสอบแล้ว
3. วิเคราะห์สาเหตุ แก้ไข แล้วค่อย merge ใหม่
4. ไม่ควรใช้ `git reset --hard` บนสาขาที่แชร์กับผู้อื่น
5. บันทึกบทเรียนใน `CHANGELOG.md`

### Things NOT to do now

- อย่าเขียนทับโค้ดเดิมทั้งหมด แก้ทีละไฟล์ ทดสอบทีละขั้น
- อย่าสร้าง plugin framework ใหม่ใน Python ถ้ายังไม่จำเป็น ใช้โครงสร้างเดิมแล้วค่อยๆ ปรับปรุง
- อย่าเชื่อมกับ deepseek-harness จนกว่า ZCoder ฝั่ง Python จะเสถียร เชื่อมทีหลังเมื่อ Phase 1–3 เสร็จแล้ว ถ้าจำเป็นจริงๆ
- อย่าเก็บ API key หรือรหัสผ่านในโค้ดหรือไฟล์ตั้งค่าที่ commit ลง git
- อย่าข้ามการทดสอบเดิมระหว่างการปรับปรุงแต่ละเฟส

## 10. Immediate Actions for Week 1

| วันที่ | งาน | ไฟล์ที่เกี่ยวข้อง |
|------|------|-------------|
| วันที่ 1 | รันทดสอบเดิมทั้งหมด บันทึกผลผิดพลาด | `tests/`, `pytest` |
| วันที่ 2 | สร้างสาขา git สำหรับงานนี้ | `git checkout -b refactor/master-upgrade` |
| วันที่ 3–4 | ปรับปรุง providers.py เป็น dataclass + MissingCredentialError | `src/zcoder/agent/orchestration/providers.py` |
| วันที่ 5 | ปรับปรุง router.py เรียกใช้ provider ใหม่ | `src/zcoder/agent/orchestration/router.py` |
| วันที่ 6 | รันทดสอบซ้ำ ตรวจสอบว่าไม่เกิดการถดถอย | `pytest` |
| วันที่ 7 | เขียนเอกสารการเปลี่ยนแปลงใน CHANGELOG.md | `CHANGELOG.md` |
# ZCoder Big Upgrade Master Plan — Part 6: Appendix — Quick Reference Commands

## 11. Appendix: Quick Reference Commands

### Check current state

```bash
cd /home/cvsz/zcoder
source .venv/bin/activate
pytest tests/ -ra -q --strict-markers
ruff check src/zcoder/
mypy src/zcoder/
black --check src/zcoder/
bandit -r src/zcoder/
```

### Create working branch

```bash
git checkout -b refactor/master-upgrade
```

### Run tests after each phase

```bash
pytest tests/unit/ -ra -q --strict-markers
pytest tests/integration/ -ra -q --strict-markers
```

### Code quality checks

```bash
ruff check src/zcoder/
mypy src/zcoder/
black --check src/zcoder/
bandit -r src/zcoder/
```

### Timeline summary table

| สัปดาห์ | เฟส | งานหลัก |
|----------|-----|---------|
| สัปดาห์ 1 | Phase 0–1 | ประเมินสภาพ, สร้างสาขา, ปรับปรุงคอนฟิกและข้อมูลประจำตัว |
| สัปดาห์ 2 | Phase 2 | ปรับปรุงชั้นผู้ให้บริการเป็น adapter pattern |
| สัปดาห์ 3 | Phase 3–4 | สตรีมอะซิงโครนัส, ระบบข้อมูลประจำตัว |
| สัปดาห์ 4 | Phase 5–6 | เซสชันและบันทึกเหตุการณ์, ระบบเครื่องมือ |
| สัปดาห์ 5 | Phase 7–8 | การทดสอบ, ประตูคุณภาพ, การปรับใช้ Docker |

## 12. Conclusion

แผนการปรับปรุงนี้ใช้ deepseek-harness เป็นสถาปัตยกรรมอ้างอิงเท่านั้น ZCoder ยังคงเป็นโปรเจกต์ Python ที่เขียนด้วย Python และควรดำเนินการทีละเฟสตามลำดับ โดยมีการทดสอบและตรวจสอบคุณภาพโค้ดในทุกขั้นตอนก่อนดำเนินการต่อไปยังเฟสถัดไป
