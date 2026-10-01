#!/usr/bin/env python3
"""중복 이벤트 재현 — 같은 요청이 두 번 왔을 때.

실제 형님 사건: 같은 답이 두 번 전송됐다(멱등성 부재).

시나리오: 큐에 들어온 이벤트를 처리해 ledger에 부수효과(보낸 횟수)를 기록한다.
  --dedupe off : request_id를 기억하지 않음 → 같은 id가 두 번 처리됨
  --dedupe on  : 처리한 request_id를 state.json에 기억 → 두 번째는 건너뜀

사용:
  python3 sim.py --dedupe off
  python3 sim.py --dedupe on
  python3 sim.py --dedupe off --replay   # 보존된 state를 그대로 두고 큐를 다시 유입
"""
import argparse
import json
import shutil
from pathlib import Path

WORKDIR = Path(__file__).parent / "_work"

EVENTS = [
    {"request_id": "m1", "text": "예약 확인 보내기"},
    {"request_id": "m2", "text": "영업시간 안내 보내기"},
    {"request_id": "m1", "text": "예약 확인 보내기"},   # 네트워크 재전송 흉내
    {"request_id": "m3", "text": "품절 안내 보내기"},
    {"request_id": "m1", "text": "예약 확인 보내기"},   # 타임아웃 후 재시도 흉내
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dedupe", choices=["on", "off"], default="off")
    ap.add_argument("--replay", action="store_true",
                    help="기존 state.json을 지우지 않고 큐를 다시 처리(보존된 상태 재유입 확인)")
    a = ap.parse_args()

    if not a.replay and WORKDIR.exists():
        shutil.rmtree(WORKDIR)
    WORKDIR.mkdir(exist_ok=True)
    state_path = WORKDIR / "state.json"
    ledger_path = WORKDIR / "ledger.jsonl"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"seen": []}
    sent = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
    if not isinstance(sent, list):
        sent = []

    for ev in EVENTS:
        rid = ev["request_id"]
        if a.dedupe == "on" and rid in state["seen"]:
            print(f"skip  {rid} — 이미 처리한 요청(저장된 state로 판별)")
            continue
        sent.append(rid)                       # 부수효과: '보냈다'를 기록
        state["seen"].append(rid)
        print(f"send  {rid} — {ev['text']}")

    state_path.write_text(json.dumps(state))
    ledger_path.write_text(json.dumps(sent))
    from collections import Counter
    print(f"\n보낸 기록: {dict(Counter(sent))}")
    print("판독: dedupe=off면 m1이 3번 기록된다 = 같은 답 중복 전송.")
    print("      --replay는 보존된 state.json을 그대로 두고 큐를 다시 유입한다 —")
    print("      state가 살아 있으면 재실행해도 skip이 유지됨을 확인할 뿐이다.")
    print("      주의: 이 명령은 상태 상실(state.json 유실·영속성 부재)을 재현하지")
    print("      않는다. dedupe 상태를 잃으면 다시 중복된다는 건 이 장치의 시연 범위 밖.")


if __name__ == "__main__":
    main()
