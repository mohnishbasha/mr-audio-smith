#!/usr/bin/env python3
"""
Tailnet preflight helpers for deploy.sh. Reads `tailscale status --json` on stdin.

  tailscale status --json | deploy/tailnet.py status --home H --required "A B" --fleet "A B C"
  tailscale status --json | deploy/tailnet.py fingerprint UNIT
"""

import argparse
import base64
import hashlib
import json
import sys


def status(data: dict, home: str, required: set, fleet: list) -> int:
    if data.get("BackendState") != "Running":
        print(
            f"  tailscale is {data.get('BackendState')!r}, not Running: connect to the tailnet first",
            file=sys.stderr,
        )
        return 1
    print(f"  this machine: {data.get('Self', {}).get('HostName')} (tailnet up)")
    peers = {p.get("HostName"): p for p in (data.get("Peer") or {}).values()}
    missing = []
    for name in dict.fromkeys(fleet + sorted(required)):
        p = peers.get(name)
        if p is None:
            state = "not in tailnet"
        elif not p.get("Online"):
            state = "OFFLINE"
        elif p.get("CurAddr"):
            state = f"online, direct {p['CurAddr']}"
        else:
            state = f"online, idle (relay {p.get('Relay') or '-'})"
        role = "home" if name == home else ("platform" if name in required else "")
        print(f"  {name:22} {state:44} {role}")
        if name in required and (p is None or not p.get("Online")):
            missing.append(name)
    sys.stdout.flush()  # keep the table above the error line
    if missing:
        print(f"  required unit(s) not reachable on the tailnet: {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


def fingerprint(data: dict, unit: str) -> int:
    for p in (data.get("Peer") or {}).values():
        if p.get("HostName") != unit:
            continue
        for key in p.get("sshHostKeys") or []:
            kind, blob = key.split()[:2]
            if "ed25519" in kind:
                fp = base64.b64encode(hashlib.sha256(base64.b64decode(blob)).digest()).decode().rstrip("=")
                print(f"{kind} SHA256:{fp}")
                return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--home", required=True)
    s.add_argument("--required", required=True)
    s.add_argument("--fleet", default="")
    f = sub.add_parser("fingerprint")
    f.add_argument("unit")
    args = parser.parse_args()
    data = json.load(sys.stdin)
    if args.cmd == "status":
        return status(data, args.home, set(args.required.split()), args.fleet.split())
    return fingerprint(data, args.unit)


if __name__ == "__main__":
    sys.exit(main())
