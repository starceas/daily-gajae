#!/usr/bin/env python3
"""내부 응답 → 카카오 스킬 응답 형식 변환 어댑터(모의).

이 파일이 만드는 건 '형식이 맞는 JSON'일 뿐이다. 카카오 서버와 주고받은
것이 아니므로 네이티브 연결 증거로 쓸 수 없다(증거 구분: O).

근거 형식: K06 스킬 응답(SkillResponse, version "2.0", template.outputs),
K07 콜백(useCallback: true + data). 자세한 문서 주소는 labs/05-kakao.md에 있다.

사용:
  python3 adapter.py --internal <응답JSON파일>          # 일반 응답
  python3 adapter.py --internal <응답JSON파일> --callback  # 콜백 첫 응답
"""
import argparse
import json
import sys
from pathlib import Path

MAX_TEXT = 1000  # simpleText 실제 길이 제한은 문서 재확인 필요(미확인). 학습용 보수값.


def to_skill_response(internal, callback=False):
    status = internal.get("status", "error")
    answer = (internal.get("answer") or "").strip() or "응답을 만들지 못했다."
    if status in ("escalate", "error", "unknown"):
        answer = f"[사람 확인 필요] {answer}"
    answer = answer[:MAX_TEXT]
    if callback:
        # K07: 첫 응답에 useCallback=true 와 data를 담아 늦게 답을 준비한다고 알린다.
        return {"version": "2.0", "useCallback": True,
                "data": {"request_id": internal.get("request_id")}}
    return {"version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": answer}}]}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--internal", required=True)
    ap.add_argument("--callback", action="store_true")
    a = ap.parse_args()
    internal = json.loads(Path(a.internal).read_text(encoding="utf-8"))
    print(json.dumps(to_skill_response(internal, a.callback),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
