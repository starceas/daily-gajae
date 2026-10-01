#!/usr/bin/env python3
"""경쟁 조건 재현 — 확인과 실행 사이에 끼어드는 사건.

실제 형님 사건: 자동 승인기가 '확인'과 '실행' 사이에 상태가 바뀌어
이미 취소된 요청을 승인했다(check-then-act).

모드:
  order  : 사건 순서 A/B를 직접 지정해 결과 차이를 본다(결정론적).
  counter: 두 작업이 공유 파일 카운터를 갱신 — 잠금 유무 비교.

사용:
  python3 sim.py --mode order --events check,cancel,act
  python3 sim.py --mode order --events check,act,cancel
  python3 sim.py --mode counter --lock off|on
"""
import argparse
import json
import tempfile
import threading
from pathlib import Path


def mode_order(events):
    state = {"pending": True, "result": None}
    checked = False
    for e in events:
        e = e.strip()
        if e == "check":
            checked = state["pending"]          # 상태를 읽어두기만 함
            print(f"check  → pending={state['pending']} (이 값을 메모)")
        elif e == "cancel":
            state["pending"] = False
            print("cancel → pending=False (요청 취소됨)")
        elif e == "act":
            # 예전에 읽은 checked 값으로 행동 — 지금 상태를 다시 안 읽음
            state["result"] = "acted" if checked else "skipped"
            print(f"act    → 예전 check={checked} 로 실행 → result={state['result']}")
    print(f"\n최종 상태: {json.dumps(state, ensure_ascii=False)}")
    print("판독: check와 act 사이에 cancel이 끼면, 취소된 요청을 승인한 셈이다.")
    print("사건 순서:", " → ".join(e.strip() for e in events))


def mode_counter(lock_on, rounds=200):
    tmp = Path(tempfile.mkdtemp(prefix="race-counter-"))
    cfile = tmp / "count.txt"
    cfile.write_text("0")
    import fcntl

    def bump():
        for _ in range(rounds):
            f = cfile.open("r+")
            if lock_on:
                fcntl.flock(f, fcntl.LOCK_EX)
            n = int(f.read().strip() or 0)
            f.seek(0)
            f.truncate()
            f.write(str(n + 1))
            f.close()

    threads = [threading.Thread(target=bump) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    final = int(cfile.read_text())
    expected = 2 * rounds
    print(f"lock={'on' if lock_on else 'off'}  기대={expected}  실제={final}  "
          f"{'✅' if final == expected else '⚠️ 유실 발생'}")
    print("판독: 잠금 없으면 read→write 사이에 상대가 끼어들어 덧셈이 유실될 수 있다.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["order", "counter"], required=True)
    ap.add_argument("--events", default="check,cancel,act")
    ap.add_argument("--lock", choices=["on", "off"], default="off")
    a = ap.parse_args()
    if a.mode == "order":
        mode_order(a.events.split(","))
    else:
        mode_counter(a.lock == "on")


if __name__ == "__main__":
    main()
