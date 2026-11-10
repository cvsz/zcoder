# การติดตั้ง Prometheus แบบ Global (สำหรับ ZCoder)

เนื่องจาก agent-session ไม่มีรหัสพาสเวิร์ด sudo โปรดรันคำสั่งต่อไปนี้ด้วยตัวเองใน terminal ของเครื่อง

## 1. ติดตั้ง Prometheus (ถ้ายังไม่ได้ติดตั้ง)

```bash
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y prometheus
```

## 2. คัดลอกไฟล์กำหนดค่า

ไฟล์ที่เตรียมไว้ใน repository:

- `prometheus/prometheus.yml` — scrape config (รวม job `zcoder` ที่ดึงจาก `localhost:8088/metrics`)
- `prometheus/prometheus_rules.yml` — alerting rules (ZcoderApiDown, ZcoderApiSlow)

```bash
sudo cp prometheus/prometheus.yml /etc/prometheus/prometheus.yml
sudo cp prometheus/prometheus_rules.yml /etc/prometheus/prometheus_rules.yml
sudo chown root:root /etc/prometheus/prometheus.yml /etc/prometheus/prometheus_rules.yml
sudo chmod 644 /etc/prometheus/prometheus.yml /etc/prometheus/prometheus_rules.yml
```

## 3. อ้างอิง rules file ใน prometheus.yml

ตรวจสอบให้แน่ใจว่า `prometheus.yml` มีบรรทัดนี้อยู่ในส่วน `rule_files`:

```yaml
rule_files:
  - "prometheus_rules.yml"
```

## 4. รีสตาร์ท Prometheus service

```bash
sudo systemctl restart prometheus
sudo systemctl status prometheus
```

## 5. ตรวจสอบว่า Prometheus ดึง metrics จาก ZCoder ได้

เปิดเบราว์เซอร์ที่ `http://localhost:9090/targets` ตรวจสอบว่า job `zcoder` มี状态เป็น `UP`

หรือดูผ่าน API:

```bash
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep -A5 '"job":"zcoder"'
curl -sf http://localhost:8088/metrics | head -20
```

## หมายเหตุ

- ZCoder API server เปิด endpoint `/metrics` บนพอร์ต `8088` (ตัวแปร `PORT`, ค่าเริ่มต้น `8088`) รูปแบบ Prometheus text exposition (`text/plain; version=0.0.4`)
- หากรัน ZCord ผ่าน Docker ให้แน่ใจว่า container เผยแพร่พอร์ต 8088 ออกมาที่ host หรือใช้ `network_mode: host` เพื่อให้ Prometheus บน host เข้าถึงได้
- หาก ZCoder ยังไม่ได้รัน ให้เริ่มก่อน (`make start-api` หรือ `docker compose up zcoder`) จากนั้นค่อยรีสตาร์ท Prometheus
