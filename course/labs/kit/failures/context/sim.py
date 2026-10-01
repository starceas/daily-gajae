#!/usr/bin/env python3
"""컨텍스트 오염/유실 재현 — 길어진 대화에서 규칙이 밀려나는 것.

실제 형님 사건: 긴 대화에서 모델이 처음 약속한 규칙을 잊었다.
여기서는 '규칙'과 '대화'를 파일로 흉내 내고, 마지막 K줄만 읽는
모의 모델이 규칙을 지키는지 비교한다. 이 모의는 그 사건의 실제 원인을
진단하지 않는다 — "유한 줄 창 + 규칙 문자열 검출" 모형의 실패만 보여준다.

  --window 20           : 마지막 20줄만 읽는 모의 모델
  --reinject            : 매 턴 규칙을 마지막에 다시 끼워 넣는다

사용:
  python3 sim.py --window 20
  python3 sim.py --window 20 --reinject
"""
import argparse
from pathlib import Path

RULES = """[규칙] 1. 답변은 항상 '결론:'으로 시작한다.
[규칙] 2. 모르는 것은 지어내지 말고 '미확인'이라고 쓴다.
[규칙] 3. 비밀값을 출력하지 않는다."""

FILLER = [f"[대화{i:02d}] 잡담 내용 — 중요하지 않은 로그 줄" for i in range(40)]


def mock_model(window_lines, transcript):
    """마지막 window_lines 줄만 읽는 모의 모델. 규칙이 보이면 지키고 안 보이면 잊는다."""
    visible = transcript[-window_lines:]
    text = "\n".join(visible)
    sees_rules = "[규칙]" in text
    if sees_rules:
        return "결론: 답한다. (규칙이 시야에 있었음)"
    return "그냥 답한다. (규칙이 시야 밖으로 밀려남 — '결론:' 접두 없음, 규칙 위반)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=20)
    ap.add_argument("--reinject", action="store_true")
    a = ap.parse_args()

    transcript = RULES.split("\n") + ["——— 대화 시작 ———"] + FILLER \
        + ["질문: 오늘 할 일이 뭐였지?"]
    if a.reinject:
        transcript += RULES.split("\n") + ["(규칙 재주입됨)"]  # 매 턴 재주입 흉내

    print(f"대화 전체 길이: {len(transcript)}줄 / 모델 시야: 마지막 {a.window}줄")
    if a.reinject:
        print("규칙 재주입: 켬")
    print("\n모의 모델 답변:")
    print(" ", mock_model(a.window, transcript))

    print("""
판독: 이 모의가 보여주는 원인은 하나다 — '유한 줄 창 + 규칙 문자열 검출'에서는
      규칙이 창 밖으로 밀려나면 이 모의 모델은 못 지킨다. 그게 이 장치의 전부다.
      실제 LLM 사건의 원인이 '규칙이 시야 밖으로 밀려난 것'이었다고 단정할 수 없다
      — 이 코드는 그 사건을 진단하지 않았고, 후보는 압축 손실·주의 경쟁·
      명령 충돌 등 여럿이다. 실제 원인은 별도 시험으로 좁혀야 한다.
      대책 후보: 매 턴 재주입(훅), 외부 노트로 빼기, 압축 시 규칙 보존 확인.
      주의: 재주입도 완전한 강제는 아니다 — 보인다≠지킨다. 검증 시험이 따로 필요하다.
""")


if __name__ == "__main__":
    main()
