#!/usr/bin/env python3
"""DNS·연결·HTTP·timeout 오류 층 구별 재현.

실제 형님 사건: 502와 DNS 실패는 생긴 곳이 다르다 — 고치는 곳도 다르다.

모의 클라이언트가 모의 서버에 요청을 보낸다. --fail로 어느 층이 고장 났는지
정하고, '관찰되는 증상'만 보고 어느 층인지 분류해 본다.

사용:
  python3 sim.py --fail dns      # 이름 해석 실패
  python3 sim.py --fail refused  # TCP 연결 거부(서버가 안 들음)
  python3 sim.py --fail http502  # 게이트웨이가 upstream에서 무효 응답을 받음
  python3 sim.py --fail timeout  # 연결은 됐는데 응답이 안 옴
  python3 sim.py --fail none     # 정상
"""
import argparse

LAYER_INFO = {
    "dns":     ("DNS(이름 해석)", "도메인→주소 변환 실패. 서버에 닿기도 전이다.",
                "False — 이름이 틀렸거나 DNS가 죽었다. 서버 상태와 무관"),
    "refused": ("TCP 연결", "주소는 맞는데 포트에 받는 서버가 없다.",
                "False — 서버 프로세스 다운/포트 오류. 재시도는 소용없을 수 있다"),
    "http502": ("HTTP 게이트웨이",
                "앞단 게이트웨이가 뒤(upstream)에서 유효하지 않은 응답을 받았다는 뜻(502 Bad Gateway). "
                "원인 후보: upstream 다운·연결 불능·깨진 응답·설정 오류 — 502만으로 어느 쪽인지는 모른다.",
                "조건부 — 원인 확인 후 재시도하면 될 수 있지만 POST는 중복 주의"),
    "timeout": ("응답 지연", "연결은 됐고 서버가 처리 중이거나 응답이 길에서 죽었다.",
                "주의 — 작업이 이미 됐을 수 있다(응답 상실). 멱등 요청만 재시도"),
    "none":    ("정상", "요청→응답 왕복 완료.", "해당 없음"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fail", choices=list(LAYER_INFO), required=True)
    ap.add_argument("--reveal", action="store_true", help="층과 의미를 공개")
    a = ap.parse_args()

    # 먼저 '관찰 증상'만 보여준다 — 실제 장애 때 네가 보는 것과 같은 수준.
    print("[관찰되는 증상]")
    if a.fail == "dns":
        print("  lookup('api.example.test') → NameError: 이름을 찾을 수 없음")
        print("  HTTP 요청 자체가 나가지 않았다.")
    elif a.fail == "refused":
        print("  connect(203.0.113.7:443) → ConnectionRefused")
        print("  DNS는 성공했다. 상대가 문을 안 열었다.")
    elif a.fail == "http502":
        print("  connect 성공 → 요청 전송 → HTTP 502 Bad Gateway 수신")
        print("  내 요청은 앞단 서버까지는 도달했다.")
    elif a.fail == "timeout":
        print("  connect 성공 → 요청 전송 → 30초 동안 응답 없음 → timeout")
        print("  서버가 처리했는지 안 했는지 이 정보만으로는 알 수 없다.")
    else:
        print("  connect 성공 → 요청 전송 → HTTP 200 수신")

    if a.reveal:
        layer, meaning, retry = LAYER_INFO[a.fail]
        print(f"\n[층] {layer}")
        print(f"[의미] {meaning}")
        print(f"[재시도 안전?] {retry}")
    else:
        print("\n→ --reveal 없이 먼저 '어느 층에서 죽었나'를 적어 본 뒤 --reveal로 대조한다.")


if __name__ == "__main__":
    main()
