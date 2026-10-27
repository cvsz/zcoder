# คำแนะนำการทำงานใน Repository ZCoder

## ขอบเขตและข้อมูลพื้นฐาน

- ทำงานเฉพาะ repository นี้ เว้นแต่ผู้ใช้จะขยายขอบเขตอย่างชัดเจน
- ก่อนแก้ subtree ให้ตรวจ `README.md`, ไฟล์นี้ และ `AGENTS.md` ที่อยู่ใกล้ subtree ที่สุด รวมถึงตรวจ `git status` เพื่อรักษางานที่มีอยู่
- โครงสร้าง Python หลักอยู่ใน `src/zcoder/` ให้คง module boundary และ public interface เดิม เว้นแต่โจทย์ต้องเปลี่ยน
- ปัจจุบัน package ระบุ Python `>=3.12`; Ruff, Black และ mypy ตั้งเป้า Python 3.12 ให้ตรวจ `pyproject.toml` และ CI workflows ก่อนเปลี่ยน toolchain
- SQLite เป็นค่าเริ่มต้นสำหรับการใช้งานคนเดียว PostgreSQL ใช้ Docker service `zPostgreSQL` บน `zPostgreSQL_network`; ฐานข้อมูลเฉพาะของ ZCoder คือ `zcoder_db` และ role คือ `zcoder` service นี้มี lifecycle แยกจาก repository

## ภาษาในการสื่อสารและเอกสาร

- สื่อสารกับผู้ใช้เป็นภาษาไทย เว้นแต่ผู้ใช้ขอภาษาอื่น
- source code, identifiers, commands, configuration และ syntax ใช้ภาษาอังกฤษ
- เอกสารและ comments ให้ใช้ภาษาไทยตาม convention ของ repository นี้ โดยคง technical terms ภาษาอังกฤษเมื่อช่วยให้แม่นยำ

## Local inference และบริการภายนอก

- เมื่องานอยู่ในขอบเขต local ZCoder ให้ใช้ local inference เท่านั้น ห้ามเรียก Anthropic API หรือ hosted model API อื่น เว้นแต่ผู้ใช้เปลี่ยนข้อกำหนดอย่างชัดเจน
- ห้ามเพิ่ม API key, credential placeholder, cloud fallback แบบเงียบ หรือ network inference ใน local workflow ให้ใช้ model endpoint แบบ loopback ที่ตั้งค่าไว้ และแจ้งข้อผิดพลาดชัดเจนเมื่อใช้งานไม่ได้
- อาจมี Anthropic compatibility code อยู่ใน repository ให้ตรวจ call path และ configuration ก่อนแก้ไข การพบข้อความจาก static scan อย่างเดียวไม่ได้ยืนยันว่าเรียก network ได้
- ใช้ GitHub, PostgreSQL, telemetry และ integration อื่นตามขอบเขตที่ผู้ใช้ระบุเท่านั้น ห้ามเปิดเผย credentials, DSN, tokens, ข้อมูลส่วนบุคคล หรือ logs ที่มีความลับ

## การพัฒนาและความปลอดภัยของ repository

- รักษา dirty และ untracked work ห้าม reset, clean, overwrite หรือย้ายงานเหล่านั้นโดยไม่มีคำสั่งชัดเจน
- เลือก diff ที่เล็กและครบตามผลลัพธ์ที่ต้องการ ห้ามแก้ generated output, vendor code, build artifacts หรือไฟล์นอกขอบเขต
- รักษา architecture และ security defaults ห้ามลดความเข้มของ authentication, authorization, tenant isolation, validation, TLS, CI checks, tests, scanners, branch protection หรือ release gates เพื่อให้ผ่าน
- ห้าม commit secrets, credentials, private keys, production tokens, sensitive personal data หรือ artifacts ที่มีความลับ
- การเปลี่ยนฐานข้อมูลต้องใช้ฐานเฉพาะของ ZCoder ตรวจ migration และ rollback ห้ามแก้ฐานข้อมูลของแอปอื่นหรือ configuration ของ shared service
- การเปลี่ยนที่มีผลต่อ production ต้องคำนึงถึง migration, backup/restore, rollback, observability, failure handling และเอกสารปฏิบัติการ

## การตรวจสอบ

- เลือก checks ให้เหมาะกับขอบเขตการเปลี่ยน รัน focused tests และ lint, type, security, build หรือ integration checks ที่เกี่ยวข้องเมื่อผู้ใช้ร้องขอหรือจำเป็นต่อการยืนยันผล
- สำหรับ PostgreSQL-backed tests ในเครื่อง ให้ใช้ `python scripts/local_postgres.py status` แล้วตามด้วย `python scripts/local_postgres.py run -- <command>` วิธีนี้ใช้ connection ของ `zcoder_db` โดยไม่พิมพ์รหัสผ่าน
- รายงาน command และผลที่เกิดขึ้นจริง แยกหลักฐานจาก source inspection, unit tests, database integration, local model inference, hosted CI และ production ออกจากกัน หลักฐานประเภทหนึ่งใช้แทนอีกประเภทไม่ได้
- ห้ามอ้างว่า production-ready หากยังมี required check, release-gate item, deployment behavior หรือ recovery path ที่ไม่ทราบหรือยังไม่ได้ตรวจ

## GitHub และการปล่อยเวอร์ชัน

- ก่อน commit, push, review หรือ merge ให้ตรวจ branch ปัจจุบัน, worktree, remote state, repository policy และ commit เป้าหมาย
- ใช้ signed commit เมื่อ release protocol กำหนด ห้าม rewrite shared history หรือข้าม protection
- ตรวจ required checks แบบ live, independent review, release-gate evidence และ post-merge verification แยกเป็นข้อกำหนด ห้ามอนุมัติงานตัวเองด้วยการสลับ identity หรือข้าม review policy
- ห้าม commit, push, approve, merge, publish หรือ deploy จน implementation ที่ร้องขอเสร็จและ gates ที่เกี่ยวข้องผ่าน หาก gate ยังไม่ผ่าน ให้คงงานในสภาพตรวจสอบได้และแจ้ง blocker อย่างเจาะจง

## วินัยการเปลี่ยนแปลง

- ทำให้การแก้ไขตรงจุด อ่านง่าย มี type และสอดคล้องกับโค้ดข้างเคียง
- ปรับเอกสาร, configuration, workflows และ tests เมื่อ behavior หรือ operational contract เปลี่ยน
- ห้ามเพิ่มข้อกล่าวอ้างที่ไม่มีหลักฐาน หรือรายงานว่างานเสร็จจาก intent, static scan หรือ test เฉพาะจุดเพียงอย่างเดียว
