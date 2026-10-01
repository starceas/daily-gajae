#!/usr/bin/env python3
"""모의 스킬 서버에 요청 fixture를 POST한다(127.0.0.1 전용).

사용:
  python3 send.py --port 8787                        # fixture 그대로 전송
  python3 send.py --port 8787 --text "월요일 열어요?"  # utterance만 교체
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--text")
    ap.add_argument("--fixture",
                    default=str(Path(__file__).parent / "fixtures" / "skill-request.json"))
    a = ap.parse_args()
    payload = json.loads(Path(a.fixture).read_text(encoding="utf-8"))
    if a.text:
        payload["userRequest"]["utterance"] = a.text
    req = urllib.request.Request(
        f"http://127.0.0.1:{a.port}/skill",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        print(r.read().decode())


if __name__ == "__main__":
    sys.exit(main())
