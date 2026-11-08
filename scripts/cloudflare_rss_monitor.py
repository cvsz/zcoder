#!/usr/bin/env python3
"""
RSS Feed Monitor — Cloudflare Changes for zeaz.dev Infrastructure

ดึง RSS feeds จาก Cloudflare changelog และกรองเฉพาะรายการที่
เกี่ยวข้องกับ infrastructure ของ zeaz.dev (DNS, SSL/TLS, Tunnel,
Terraform, API Deprecations, WAF, Fundamentals)

ใช้งาน:
    python3 scripts/cloudflare_rss_monitor.py [--daily] [--weekly]

ผลลัพธ์จะแสดงรายการที่อาจส่งผลต่อ zeaz.dev พร้อมคำแนะนำ
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from defusedxml import ElementTree as ET

# Feeds ที่ควรติดตามสำหรับ zeaz.dev
FEEDS = {
    "dns": "https://developers.cloudflare.com/changelog/rss/dns.xml",
    "ssl": "https://developers.cloudflare.com/changelog/rss/ssl.xml",
    "tunnel": "https://developers.cloudflare.com/changelog/rss/tunnel.xml",
    "terraform": "https://developers.cloudflare.com/changelog/rss/terraform.xml",
    "fundamentals": "https://developers.cloudflare.com/changelog/rss/fundamentals.xml",
    "waf": "https://developers.cloudflare.com/changelog/rss/waf.xml",
    "api_deprecations": "https://developers.cloudflare.com/fundamentals/api/reference/deprecations/index.xml",
}

# คำสำคัญที่บ่งชี้ว่ารายการนี้เกี่ยวข้องกับ zeaz.dev
RELEVANT_KEYWORDS = [
    "dns",
    "dns_record",
    "cname",
    "a record",
    "ssl",
    "tls",
    "https",
    "certificate",
    "universal ssl",
    "tunnel",
    "cloudflared",
    "cloudflare tunnel",
    "terraform",
    "provider",
    "cloudflare provider",
    "api deprecation",
    "deprecated",
    "sunset",
    "waf",
    "rate limit",
    "rate limiting",
    "zone_setting",
    "edge",
    "hsts",
    "opportunistic encryption",
    "cache",
    "cache rule",
    "logpush",
]


def fetch_feed(url: str, timeout: int = 15) -> ET.Element | None:
    """ดึง RSS feed และคืนค่า root element หรือ None ถ้าไม่สำเร็จ"""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        print(f"  [WARN] ไม่อนุญาต URL {url}: อนุญาตเฉพาะสก์ที https เท่านั้น", file=sys.stderr)
        return None
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (zeaz.dev rss-monitor)"})
        # B310 mitigation: urlopen follows HTTP redirects; request URL pre-validated to
        # https (line 73) and final response URL re-validated via resp.geturl() below
        # before reading, blocking file:///ftp:// redirect escapes.
        with urlopen(req, timeout=timeout) as resp:  # nosec B310  # https enforced before and after redirects
            final_url = urlparse(resp.geturl())
            if final_url.scheme != "https":
                print(f"  [WARN] Feed redirect left https {url} -> {resp.geturl()}", file=sys.stderr)
                return None
            data = resp.read()
        # defusedxml.ElementTree ป้องกัน XXE / XML External Entity injection ตามค่าเริ่มต้น
        return ET.fromstring(data)
    except (URLError, HTTPError, ET.ParseError, OSError) as exc:
        print(f"  [WARN] ไม่สามารถดึง feed {url}: {exc}", file=sys.stderr)
        return None


def is_relevant(title: str, description: str = "") -> bool:
    """ตรวจสอบว่ารายการเกี่ยวข้องกับ zeaz.dev infrastructure หรือไม่"""
    text = f"{title} {description}".lower()
    return any(kw in text for kw in RELEVANT_KEYWORDS)


def is_recent(pub_date_str: str, days: int) -> bool:
    """ตรวจสอบว่ารายการเผยแพร่ภายในจำนวนวันที่กำหนดหรือไม่"""
    try:
        # RSS pubDate format: "Wed, 02 Oct 2024 08:00:00 GMT"
        pub_date = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z")
        pub_date = pub_date.replace(tzinfo=UTC)
        cutoff = datetime.now(UTC) - timedelta(days=days)
        return pub_date >= cutoff
    except (ValueError, TypeError):
        return True  # ถ้าแปลงวันที่ไม่ได้ ให้ถือว่ารายการใหม่


def parse_feed(root: ET.Element, feed_name: str, days: int) -> list[dict]:
    """แปลง XML root เป็นรายการที่เกี่ยวข้องและเป็นล่าสุด"""
    items: list[dict] = []
    channel = root.find("channel")
    if channel is None:
        return items

    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()

        if not is_recent(pub_date, days):
            continue
        if not is_relevant(title, description):
            continue

        items.append(
            {
                "feed": feed_name,
                "title": title,
                "link": link,
                "description": description,
                "pub_date": pub_date,
            }
        )

    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="ตรวจสอบการเปลี่ยนแปลง Cloudflare ที่ส่งผลต่อ zeaz.dev")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="จำนวนวันที่ย้อนหลัง (default: 7)",
    )
    parser.add_argument(
        "--feed",
        type=str,
        choices=list(FEEDS.keys()) + ["all"],
        default="all",
        help="ระบุ feed เดียวหรือทั้งหมด (default: all)",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("  Cloudflare RSS Monitor — zeaz.dev Infrastructure")
    print(f"  ตรวจสอบย้อนหลัง {args.days} วัน — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)

    feeds_to_check = list(FEEDS.items()) if args.feed == "all" else [(args.feed, FEEDS[args.feed])]

    total_relevant = 0
    for feed_name, url in feeds_to_check:
        print(f"\n--- Feed: {feed_name} ({url}) ---")
        root = fetch_feed(url)
        if root is None:
            continue

        items = parse_feed(root, feed_name, args.days)
        total_relevant += len(items)

        if not items:
            print("  (ไม่มีรายการที่เกี่ยวข้องในช่วงเวลาที่กำหนด)")
            continue

        for item in items:
            print(f"  [{item['pub_date']}] {item['title']}")
            print(f"      {item['link']}")
            if item["description"]:
                desc = item["description"].strip()
                if len(desc) > 200:
                    desc = desc[:200] + "..."
                print(f"      {desc}")
            print()

    print("=" * 80)
    print(f"  รวมรายการที่เกี่ยวข้อง: {total_relevant} รายการ")
    print("=" * 80)

    if total_relevant > 0:
        print("\n  🔧 ขั้นตอนถัดไป:")
        print("      1. ตรวจสอบว่ารายการใดส่งผลต่อ terraform/cloudflare ของ zeaz.dev")
        print("      2. อัปเดตไฟล์ .tf ตามความจำเป็น (versions.tf, ssl.tf, waf.tf ฯลฯ)")
        print("      3. รัน terraform validate และ terraform plan ก่อน apply")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
