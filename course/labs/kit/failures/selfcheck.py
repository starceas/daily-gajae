#!/usr/bin/env python3
"""labs/kit/failures 시나리오 자체 점검.

각 시뮬레이션의 대표 명령을 돌려 기대 문자열이 나오는지 확인한다.
주의: 이 점검은 고정된 사례의 출력 subset 검사다 — 장치 정상·원리 동일성·
시나리오 전체 증명이 아니다. net 시뮬은 실제 네트워크를 진단하지 않는다.
사용: python3 labs/kit/failures/selfcheck.py
"""
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent

CHECKS = [
    ("race order A", "race/sim.py --mode order --events check,cancel,act",
     ["acted", "취소된 요청을 승인"]),
    ("race order B", "race/sim.py --mode order --events check,act,cancel",
     ["acted"]),  # act 후 cancel이므로 행동 자체는 같지만 순서 안전
    ("race counter lock on", "race/sim.py --mode counter --lock on",
     ["기대=400", "실제=400"]),
    ("dup off", "dup/sim.py --dedupe off", ["'m1': 3"]),
    ("dup on", "dup/sim.py --dedupe on", ["'m1': 1"]),
    ("timeout request", "timeout/sim.py --fail request --retry",
     ["요청이 도달하지 않았다", "'r1'"]),
    ("timeout response", "timeout/sim.py --fail response --retry",
     ["응답이 돌아오는 길에", "이미 됐다"]),
    ("config override", "config/sim.py --reset --set-global model=sol "
     "--set-channel ch1 model=ds --channel ch1 --set-model opus",
     ["model    = opus", "명령줄"]),
    ("config channel beats global", "config/sim.py --reset --set-global model=sol "
     "--set-channel ch1 model=ds --channel ch1",
     ["model    = ds", "channel-ch1.json"]),
    ("net dns", "net/sim.py --fail dns --reveal", ["DNS", "이름 해석"]),
    ("net http502", "net/sim.py --fail http502 --reveal", ["502", "게이트웨이"]),
    ("net timeout", "net/sim.py --fail timeout --reveal", ["응답 지연", "응답 상실"]),
    ("perms", "perms/sim.py", ["PermissionError", "권한을 되돌린 뒤"]),
    ("context no reinject", "context/sim.py --window 20", ["밀려남"]),
    ("context reinject", "context/sim.py --window 20 --reinject",
     ["규칙이 시야에 있었음"]),
]


def main():
    fails = []
    for name, cmd, needles in CHECKS:
        prog, *args = cmd.split()
        p = subprocess.run([sys.executable, str(BASE / prog), *args],
                           capture_output=True, text=True)
        out = p.stdout + p.stderr
        missing = [n for n in needles if n not in out]
        ok = p.returncode == 0 and not missing
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        for n in missing:
            print(f"      기대 문자열 없음: {n}")
        if p.returncode != 0:
            print(f"      종료코드 {p.returncode}: {p.stderr[:200]}")
        if not ok:
            fails.append(name)
    print(f"\n{len(CHECKS) - len(fails)}/{len(CHECKS)} 통과")
    print("주의: 고정 사례의 출력 문자열 subset 검사 — 장치 정상·원리 동일성·")
    print("      모든 시나리오의 증명이 아니다. net 항목은 실제 네트워크 진단 아님.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
