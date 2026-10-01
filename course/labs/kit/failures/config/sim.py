#!/usr/bin/env python3
"""설정 덮어쓰기(우선순위) 재현.

실제 형님 사건: 채널별 설정이 전역 설정을 덮어 모델 교체가 안 먹혔다.

규칙(이 학습 시뮬레이션의 가정): 명령줄 > 채널 > 전역 > 기본값.
한 값을 바꿨는데 왜 적용이 안 됐는지 '어떤 층이 이겼나'를 관찰한다.

사용:
  python3 sim.py                     # 전역만 둔 상태
  python3 sim.py --set-global model=sol        # 전역 바꿈
  python3 sim.py --set-channel ch1 model=ds    # 채널이 덮음
  python3 sim.py --channel ch1 --set-model opus   # 교체 시도 — 누가 이기나?
"""
import argparse
import json
import shutil
from pathlib import Path

WORKDIR = Path(__file__).parent / "_work"
DEFAULTS = {"model": "basic", "timeout": "30", "tone": "normal"}


def load(name):
    p = WORKDIR / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def save(name, cfg):
    WORKDIR.mkdir(exist_ok=True)
    (WORKDIR / f"{name}.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2))


def resolve(channel, override_key=None, override_val=None):
    """층별로 어디서 값이 왔는지 출처를 함께 표시한다."""
    g = load("global")
    c = load(f"channel-{channel}") if channel else {}
    cli = {override_key: override_val} if override_key else {}
    result = {}
    for key in sorted(set(DEFAULTS) | set(g) | set(c) | set(cli)):
        val, src = DEFAULTS.get(key), "기본값"
        if key in g:
            val, src = g[key], "global.json"
        if key in c:
            val, src = c[key], f"channel-{channel}.json"
        if key in cli:
            val, src = cli[key], "명령줄"
        result[key] = (val, src)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel")
    ap.add_argument("--set-global", action="append", default=[], metavar="k=v")
    ap.add_argument("--set-channel", nargs=2, action="append", default=[],
                    metavar=("채널", "k=v"))
    ap.add_argument("--set-model", metavar="모델")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()

    if a.reset and WORKDIR.exists():
        shutil.rmtree(WORKDIR)
    for kv in a.set_global:
        k, v = kv.split("=", 1)
        g = load("global")
        g[k] = v
        save("global", g)
        print(f"global.json에 {k}={v} 기록")
    for ch, kv in a.set_channel:
        k, v = kv.split("=", 1)
        c = load(f"channel-{ch}")
        c[k] = v
        save(f"channel-{ch}", c)
        print(f"channel-{ch}.json에 {k}={v} 기록")

    ov = ("model", a.set_model) if a.set_model else (None, None)
    print(f"\n해석 대상 채널: {a.channel or '(없음)'}")
    for k, (v, src) in resolve(a.channel, *ov).items():
        print(f"  {k:8} = {v:<8} ← {src}")
    print("\n판독: 바꾼 값이 적용되지 않으면, 더 높은 우선순위 층이 덮은 것이다.")
    print("      '안 먹는다'고 하기 전에 각 층의 파일과 우선순위 규칙부터 확인한다.")


if __name__ == "__main__":
    main()
