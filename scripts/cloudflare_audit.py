import json
import os
import urllib.request

token = os.environ.get("CLOUDFLARE_API_TOKEN", "cfat_dummy_token_placeholder_redacted")
account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "dummy_account_id_placeholder")

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
}

print("=== AUSI PHASE 1: ACCOUNT & ZONE DISCOVERY ===")
req = urllib.request.Request(
    "https://api.cloudflare.com/client/v4/user/tokens/verify",
    headers=headers,
)
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        print("Token Verify:", data.get("success"), data.get("messages"))
except Exception as e:
    print("Token Verify Error:", e)

req = urllib.request.Request(
    "https://api.cloudflare.com/client/v4/zones",
    headers=headers,
)
zone_id = None
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        for zone in data.get("result", []):
            print(
                f"Zone: {zone['name']} (ID: {zone['id']}, Status: {zone['status']})"
            )
            if zone["name"] == "zeaz.dev":
                zone_id = zone["id"]
except Exception as e:
    print("Zones Error:", e)

if zone_id:
    print("\\n=== AUSI PHASE 2: DNS INVENTORY (zeaz.dev) ===")
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            for rec in data.get("result", []):
                print(
                    f"[{rec['type']}] {rec['name']} -> {rec['content']} "
                    f"(Proxied: {rec['proxied']})"
                )
    except Exception as e:
        print("DNS Records Error:", e)

print("\\n=== AUSI PHASE 3: CLOUDFLARE TUNNELS ===")
req = urllib.request.Request(
    f"https://api.cloudflare.com/client/v4/accounts/{account_id}/cfd_tunnel",
    headers=headers,
)
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        for tunnel in data.get("result", []):
            print(
                f"Tunnel: {tunnel['name']} (ID: {tunnel['id']}, "
                f"Status: {tunnel['status']}, Deleted: {tunnel.get('deleted_at')})"
            )
except Exception as e:
    print("Tunnels Error:", e)
