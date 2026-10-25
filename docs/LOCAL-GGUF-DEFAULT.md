# โหมด Local GGUF สำหรับ ZCoder Prompt CLI

คำสั่งปกติ `zcoder -p`, `zcoder --agent ... -p`, multi-agent router และ web chat ใช้เซิร์ฟเวอร์ llama.cpp chat completion แบบ **loopback-only** เป็นค่าเริ่มต้น transport สำหรับ inference จำกัดเฉพาะ endpoint ของโมเดลภายในเครื่อง ส่วนคำสั่ง legacy สำหรับ administration, compliance, managed-agent และโมเดลเฉพาะยังคงอยู่เพื่อ compatibility แต่ไม่พร้อมใช้งานใน build แบบ local-only นี้

## ไฟล์โมเดลบน Ubuntu/WSL ของผู้ใช้

- `/home/cvsz/zgpu/qwen-7b-q4km.gguf`
- `/home/cvsz/zgpu/qwen-1.5b-q4km.gguf`

พาธ Windows `\\\\wsl.localhost\\...` **ไม่เหมาะสำหรับ Linux CLI** ห้ามคัดลอกไฟล์โมเดล GGUF เข้าไปใน repository

## ข้อกำหนดเบื้องต้น

ติดตั้งหรือ build `llama.cpp` แยกต่างหาก เพื่อให้เรียก `llama-server` ได้จาก PATH repository นี้จะไม่ดาวน์โหลด executable หรือ model weights

Terminal A:

```bash
cd ~/zcoder
bash scripts/start_local_gguf.sh 7b
# หากต้องการตัวเลือกที่ใช้หน่วยความจำน้อยกว่า ให้หยุด server แรกก่อนแล้วรัน:
# bash scripts/start_local_gguf.sh 1.5b
```

Terminal B:

```bash
cd ~/zcoder
export ZCODER_PROVIDER=llama_cpp
export ZCODER_BASE_URL=http://127.0.0.1:8080
zcoder --agent security_auditor -p "Audit cvsz/zgpu source for vulnerabilities; cite files and recommend tests."
```

Model server รับการเชื่อมต่อที่ `127.0.0.1:8080` เท่านั้น การสร้างข้อความในเครื่องไม่ต้องใช้ API key หาก local server ไม่พร้อม คำขอต้อง fail closed และ **ห้าม fallback ไปยัง provider ภายนอก** ไม่สามารถเลือก legacy cloud provider ผ่าน inference router ได้

ชื่อโมเดลสาธารณะคือ `zcoder-qwen2.5-coder-7b` และ `zcoder-qwen2.5-coder-1.5b`; launcher จะกำหนด alias ของ llama.cpp server ให้ตรงกัน

การทดสอบแรกควรใช้ prompt สั้น ๆ สำหรับ text completion การระบุชื่อ GitHub repository เพียงอย่างเดียวไม่ได้ทำให้ ZCoder เข้าถึง source code ของ repository นั้นโดยอัตโนมัติ ต้องตรวจสอบหรือส่งไฟล์ให้ระบบอย่างชัดเจน

### คำสั่งตรวจสอบสำหรับนักพัฒนา

```bash
ruff check src/zcoder/main.py src/zcoder/services/coder.py tests/unit/test_local_gguf_default.py
ruff format --check src/zcoder/main.py src/zcoder/services/coder.py tests/unit/test_local_gguf_default.py
python -m pytest tests/unit/test_local_gguf_default.py -q
```

การเปลี่ยน backend เริ่มต้นเป็นการเปลี่ยนแปลงที่อาจกระทบ compatibility ของ tests ซึ่งพึ่งพา implicit `PROVIDER_CREDENTIAL_OR_CONFIG` mock เดิม tests เหล่านั้นต้องระบุ legacy provider ที่ต้องการอย่างชัดเจน หรือย้ายไปใช้ contract ใหม่ ห้าม merge จนกว่า full test suite และ independent review จะผ่าน

**ข้อจำกัด:** ยังไม่ได้ลบ legacy provider modules และ model metadata ออกจาก source code แต่ feature เหล่านี้ยังใช้ไม่ได้จนกว่าจะมี local implementation มาทดแทน SDK dependency ยังคงอยู่เพื่อ compatibility ขณะที่ application client factory ใช้ transport ที่ปฏิเสธ network requests นี่คือการบังคับใช้ขณะ runtime ไม่ใช่การลบโค้ดต้นทางทั้งหมด
