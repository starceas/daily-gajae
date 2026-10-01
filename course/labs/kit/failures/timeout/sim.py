#!/usr/bin/env python3
"""timeout과 '성공했으나 응답 상실'의 차이 재현.

실제 형님 사건 배경: 네트워크가 끊겼을 때 '작업이 안 됐다'와
'작업은 됐는데 응답만 못 받았다'는 전혀 다른 상태다.

서버는 요청을 받으면 ledger에 부수효과를 기록하고 응답을 돌린다.
  --fail request   : 요청이 서버에 도달하기 전 끊김 → 작업 안 됨
  --fail response  : 작업은 됐지만 응답이 상실 → 클라이언트는 실패로 인식
  --fail none      : 정상

그 뒤 --retry 로 같은 request_id를 재시도했을 때 무슨 일이 생기는지 본다.

사용:
  python3 sim.py --fail request --retry
  python3 sim.py --fail response --retry
"""
import argparse
import json
import shutil
from pathlib import Path

WORKDIR = Path(__file__).parent / "_work"


def server_process(req, fail):
    """부수효과를 ledger에 기록하고, 응답 '전달 여부'를 결정한다."""
    ledger = WORKDIR / "ledger.jsonl"
    done = json.loads(ledger.read_text()) if ledger.exists() else []
    client_sees = None
    if fail == "request":
        print("  [서버] 요청이 도달하지 않았다 — 아무 일도 안 함")
    else:
        if req["request_id"] not in done:      # 서버는 멱등하게 처리한다고 가정
            done.append(req["request_id"])
            ledger.write_text(json.dumps(done))
        if fail == "response":
            print("  [서버] 작업 완료·ledger 기록 → 응답이 돌아오는 길에 상실")
        else:
            client_sees = {"ok": True}
            print("  [서버] 작업 완료, 응답 정상 전달")
    return client_sees


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fail", choices=["request", "response", "none"], required=True)
    ap.add_argument("--retry", action="store_true")
    a = ap.parse_args()

    if WORKDIR.exists():
        shutil.rmtree(WORKDIR)
    WORKDIR.mkdir()
    req = {"request_id": "r1", "text": "예약 확정 보내기"}

    for attempt in range(2 if a.retry else 1):
        print(f"[클라이언트] 시도 {attempt + 1}: {req['request_id']} 전송")
        resp = server_process(req, a.fail if attempt == 0 else "none")
        if resp is None:
            print("[클라이언트] 응답 없음(timeout으로 인식)")
        else:
            print(f"[클라이언트] 응답 수신: {resp}")
            break

    ledger = WORKDIR / "ledger.jsonl"
    done = json.loads(ledger.read_text()) if ledger.exists() else []
    print(f"\n실제 부수효과 기록: {done}")
    if a.fail == "response":
        print("판독: 클라이언트는 실패로 봤지만 작업은 이미 됐다.")
        if a.retry:
            print("      --retry 후 최종 ledger는 요청 상실 쪽과 같은 [r1]이다 —")
            print("      다른 건 '첫 시도에서 이미 부수효과가 생겼다'는 점이다.")
            print("      (재시도 없는 첫 시도만 보면 요청 상실은 [], 응답 상실은 [r1].)")
        print("      재시도가 안전한 건 서버가 request_id로 중복을 막을 때뿐이다.")
    elif a.fail == "request":
        print("판독: 작업이 안 됐으니 재시도는 안전하다.")
        if a.retry:
            print("      --retry 후 최종 ledger는 응답 상실 쪽과 같은 [r1]이다 —")
            print("      다른 건 '첫 시도에 아무 일도 안 했다'는 점이다.")
        print("      문제는 클라이언트가 두 경우를 구별할 수 없다는 것이다.")


if __name__ == "__main__":
    main()
