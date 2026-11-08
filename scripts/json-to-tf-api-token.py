#!/usr/bin/env python3
"""
แปลง zeaz-cloudflare-policies.json เป็น Terraform HCL
สำหรับ resource cloudflare.api_token ที่ใช้ใน zedge Terraform

ใช้งาน:
    python3 scripts/json-to-tf-api-token.py \
        --input zeaz-cloudflare-policies.json \
        --output api_token_policies.tf
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def permission_groups_to_hcl(groups: list[dict], indent: int = 6) -> str:
    """แปลง permission_groups list เป็น HCL list of objects"""
    lines = []
    prefix = " " * indent
    lines.append(f"{prefix}permission_groups = [")
    for i, group in enumerate(groups):
        gid = group.get("id", "")
        lines.append(f"{prefix}  {{")
        lines.append(f'{prefix}    id = "{gid}"')
        lines.append(f"{prefix}  }}" + ("," if i < len(groups) - 1 else ""))
    lines.append(f"{prefix}]")
    return "\n".join(lines)


def resources_to_hcl(resources: dict, indent: int = 6) -> str:
    """แปลง resources map เป็น HCL string

    Cloudflare provider ต้องการ resources เป็น string type (เช่น \"*\").
    ถ้าทุกค่าใน map เป็น string ให้ใช้ค่าแรกเป็น string โดยตรง.
    """
    prefix = " " * indent
    values: list[str] = []

    def collect(value) -> None:
        if isinstance(value, dict):
            for v in value.values():
                collect(v)
        else:
            values.append(str(value))

    for scope in resources.values():
        collect(scope)

    if values:
        return f'{prefix}resources = "{values[0]}"'
    return f'{prefix}resources = "*"'


def policy_to_hcl(policy: dict, indent: int = 4) -> str:
    """แปลงหนึ่ง policy เป็น HCL object"""
    lines = []
    prefix = " " * indent
    effect = policy.get("effect", "allow")
    lines.append(f"{prefix}{{")
    lines.append(f'{prefix}  effect = "{effect}"')
    groups = policy.get("permission_groups", [])
    if groups:
        lines.append(permission_groups_to_hcl(groups, indent + 2))
    resources = policy.get("resources", {})
    if resources:
        lines.append(resources_to_hcl(resources, indent + 2))
    lines.append(f"{prefix}}}")
    return "\n".join(lines)


def generate_tf(
    data: dict, token_name: str = "zeaz-dev-api-token"
) -> str:  # nosec B107  # dev-script default token NAME, not a secret value
    """สร้าง HCL ไฟล์สำหรับ cloudflare_api_token"""
    policies = data.get("policies", [])
    lines = []
    lines.append('resource "cloudflare_api_token" "zeaz_dev_token" {')
    lines.append(f'  name = "{token_name}"')
    lines.append("")
    lines.append("  policies = [")
    for i, policy in enumerate(policies):
        lines.append(policy_to_hcl(policy, 4))
        if i < len(policies) - 1:
            lines[-1] += ","
    lines.append("  ]")
    lines.append("}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="แปลง Cloudflare API token policies JSON เป็น Terraform HCL")
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="เส้นทางไฟล์ zeaz-cloudflare-policies.json",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="เส้นทางไฟล์ Terraform HCL ที่จะสร้าง",
    )
    parser.add_argument(
        "--token-name",
        type=str,
        default="zeaz-dev-api-token",
        help="ชื่อของ API token",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: ไม่พบไฟล์ 입력: {input_path}", file=sys.stderr)
        return 1

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    hcl = generate_tf(data, args.token_name)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(hcl + "\n")

    print(f"สร้างไฟล์ Terraform HCL แล้ว: {output_path}")
    print(f"นโยบายที่แปลง: {len(data.get('policies', []))} นโยบาย")
    return 0


if __name__ == "__main__":
    sys.exit(main())
