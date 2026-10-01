#!/usr/bin/env python3
"""모의 응답기 — labs/kit/agent/mock_agent.py

외부 호출·LLM 없이, --data 폴더의 txt 자료와 고정 규칙만으로 답한다.
이것은 '에이전트의 입출력 계약 예제'다. 실제 LLM 에이전트가 아니며,
실제 모델·카카오 연결의 증거로 쓸 수 없다(증거 구분: O=오프라인).

범위 한계: 이 baseline은 P01 fixture(빵집 자료)의 파일 구조를 아는
참조 구현이다. 답·근거는 항상 파일에서 읽은 실제 줄을 인용한다.
자료가 바뀌거나 기대한 줄이 없으면 지어내지 않고 unknown/error로 보류한다.

중복 억제 한계: out/<request_id>.json 존재 확인은 '순차로 재입력된'
경우만 잡는다. 동시 도착(경쟁 조건)·프로세스 재시작·외부 시스템의
exactly-once는 보장하지 않는다. 그 한계 자체가 04-failures의 주제다.

계약:
  입력 : --request 요청JSON {"request_id": str, "text": str, "now"?: ISO8601}
         --data 자료 폴더, --out 출력 폴더
  출력 : <out>/<request_id>.json
         {"request_id","status","answer","evidence":[{"source","detail"}],
          "duplicate","notes"}
  status: ok | unknown | clarify | escalate | error
  request_id는 파일명이 되므로 [A-Za-z0-9_-]{1,64}만 허용한다.
  요청이 비JSON·비객체·request_id 누락/비안전·text 비문자열·now가
  ISO8601 아님이면 질문을 해석하지 않고 status="error"로 응답한다
  (request_id가 안전하지 않으면 <out>/invalid-request.json에 쓴다).
  같은 request_id가 재도착하면 저장된 응답에 duplicate=true만 표시한다.

  ID 의미 범위(scope): 중복 판별은 request_id에만 건다.
  - 같은 id + 다른 text → 첫 응답을 재사용한다(내용 충돌은 감지하지 않는다).
  - 다른 id + 같은 text → 새 요청으로 처리한다.
  즉 "같은 내용의 다른 요청"과 "같은 요청의 재전송"을 구별하는 책임은
  id를 부여하는 발신 측에 있다 — 이 장치는 그 규약이 지켜진다고 가정한다.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

INPUT_INJECTION = ["무시하고", "규칙 무시", "무시해", "ignore previous",
                   "ignore all", "관리자 모드", "비밀값", "비밀번호"]
ESCALATE_WORDS = ["환불", "환급", "불만", "항의", "보상"]
ALLERGEN_WORDS = ["알레르기", "성분", "알레르"]
PREORDER_WORDS = ["예약", "선주문", "주문"]
STOCK_WORDS = ["남았", "재고", "아직 있", "지금 사", "살 수 있"]
HOURS_WORDS = ["몇 시", "영업", "열어", "열려", "열나", "여나", "여는", "여냐",
               "닫아", "닫는", "휴무", "언제",
               "월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일",
               "주말", "평일"]
MENU_WORDS = ["메뉴", "뭐 팔", "종류", "뭐가 있"]
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
TIME_RE = re.compile(r"\d{2}:\d{2}")


def read_file(data_dir, name):
    p = Path(data_dir) / name
    return p.read_text(encoding="utf-8") if p.exists() else None


def find_line(lines, *needles):
    for ln in lines:
        if all(n in ln for n in needles):
            return ln.strip()
    return None


def times_of(s):
    return set(TIME_RE.findall(s or ""))


def menu_items(menu_txt):
    return [ln[2:].strip() for ln in (menu_txt or "").splitlines()
            if ln.startswith("- ")]


def find_item(text, menu_txt):
    for item in menu_items(menu_txt):
        base = item.split("(")[0].strip()
        words = base.split()
        if base in text or any(w in text for w in words if len(w) >= 2):
            return base
    return None


def allergen_row(allergens_txt, item):
    for ln in (allergens_txt or "").splitlines():
        if ln.strip().startswith(item + ":"):
            return ln.strip()
    return None


def respond(req, data_dir):
    text = req["text"].strip()
    low = text.lower()
    r = {"request_id": req["request_id"], "status": "ok", "answer": "",
         "evidence": [], "duplicate": False, "notes": []}

    def ev(source, detail):
        r["evidence"].append({"source": source, "detail": detail})

    # 1) 입력 속 주입 명령 — 자료 밖의 지시는 따르지 않는다.
    if any(k in low for k in INPUT_INJECTION) or any(k in text for k in INPUT_INJECTION):
        r.update(status="escalate",
                 answer="자료 밖의 지시는 따르지 않는다. 사람에게 넘긴다.")
        return r

    # 2) 사람이 처리할 영역 — 환불·불만.
    if any(k in text for k in ESCALATE_WORDS):
        r.update(status="escalate",
                 answer="환불·불만은 사람이 직접 처리한다. 사장님께 전달한다.")
        return r

    # 3) 알레르기 — 표에 없는 신메뉴는 단정 금지. 답은 파일의 실제 줄에서.
    if any(k in text for k in ALLERGEN_WORDS):
        al = read_file(data_dir, "allergens.txt")
        if al is None:
            r.update(status="error",
                     answer="allergens.txt 자료가 없어 확인할 수 없다. 사람에게 확인 요청.")
            return r
        header = al.splitlines()[0] if al.splitlines() else ""
        m = re.search(r"\d{4}-\d{2}-\d{2}", header)
        stamp = m.group(0) if m else "날짜 미상"
        menu_txt = read_file(data_dir, "menu.txt")
        item = find_item(text, menu_txt)
        if item is None:
            r.update(status="clarify",
                     answer="어느 품목인지 알려 주시면 성분 표를 확인해 드린다.")
            return r
        row = allergen_row(al, item)
        if row:
            ev("allergens.txt", row)
            r.update(status="ok", answer=f"{row} (성분 표 {stamp} 기준)")
        else:
            # 근거는 파일의 실제 줄만 인용한다 — 지어낸 문장을 근거로 쓰지 않는다.
            ev("allergens.txt", header)
            mline = next((ln.strip() for ln in (menu_txt or "").splitlines()
                          if item in ln), None)
            if mline:
                ev("menu.txt", mline)
            r.update(status="escalate",
                     answer=f"'{item}'은 성분 표({stamp})에 없어 확인할 수 없다. 사장님 확인 후 안내한다.")
        return r

    # 4) 현재 재고 — 기록이 없으므로 단정 금지.
    if any(k in text for k in STOCK_WORDS):
        r.update(status="unknown",
                 answer="지금 재고는 기록이 없어 확인할 수 없다. 가게에 직접 확인이 필요하다.")
        return r

    # 5) 품절 시점 — 자료에 기록된 줄만 인용한다.
    if "품절" in text:
        hours = read_file(data_dir, "hours.txt") or ""
        line = find_line(hours.splitlines(), "품절")
        if line:
            ev("hours.txt", line)
            r["answer"] = f"{line} (기록상 경향이며 오늘 재고는 미확인)"
        else:
            r.update(status="unknown", answer="품절 관련 기록이 자료에 없다.")
        return r

    # 6) 예약 — preorder.txt의 실제 규칙 줄을 인용한다.
    if any(k in text for k in PREORDER_WORDS):
        po = read_file(data_dir, "preorder.txt")
        if po is None:
            r.update(status="error", answer="preorder.txt 자료가 없어 답할 수 없다.")
            return r
        lines = [ln.strip().lstrip("- ").strip() for ln in po.splitlines()
                 if ln.strip().startswith("-")]
        if not lines:
            r.update(status="unknown",
                     answer="예약 규칙 자료가 비어 있다. 사람 확인이 필요하다.")
            return r
        for ln in lines:
            ev("preorder.txt", ln)
        r["answer"] = " ".join(lines)
        return r

    # 7) 영업시간 — hours.txt의 실제 줄을 인용한다.
    if any(k in text for k in HOURS_WORDS):
        hours = read_file(data_dir, "hours.txt")
        if hours is None:
            r.update(status="error", answer="hours.txt 자료가 없어 답할 수 없다.")
            return r
        body = [ln.strip() for ln in hours.splitlines() if ln.strip()][1:]  # 첫 줄은 제목
        flyer = read_file(data_dir, "flyer.txt")

        if "내일" in text or "오늘" in text:
            if "now" not in req:
                r.update(status="clarify",
                         answer="오늘이 며칠인지 정보가 없다. 요일을 알려 주시면 시간을 안내한다.")
                for ln in body:
                    ev("hours.txt", ln)
                return r
            try:
                day = datetime.fromisoformat(req["now"])
            except (TypeError, ValueError):
                r.update(status="error",
                         answer="요청의 now 값이 ISO8601 시각이 아니다.")
                return r
            if "내일" in text:
                day = day + timedelta(days=1)
            text = f"{WEEKDAYS[day.weekday()]}요일 " + text  # 아래 요일 분기로 연결

        # 요일은 "X요일" 토큰으로만 분류한다 — "일" 같은 날 글자 매칭은
        # "목요일"을 주말로 오인하는 버그의 원인이었다(중간본 대조).
        asked_day = None
        for w in WEEKDAYS:
            if f"{w}요일" in text:
                asked_day = w
                break
        if asked_day == "월":
            line = find_line(body, "월")
        elif asked_day in ("토", "일") or "주말" in text:
            line = find_line(body, "토") or find_line(body, "일")
        elif "평일" in text or asked_day in ("화", "수", "목", "금"):
            line = find_line(body, "화")
        else:
            line = None

        if line is not None:
            ev("hours.txt", line)
            if "휴무" in line:
                r["answer"] = f"{line.split()[0]}은 휴무다."
            elif asked_day:
                r["answer"] = f"{asked_day}요일: {line}."
            else:
                r["answer"] = f"{line} 영업."
            if flyer and times_of(flyer) != times_of(line):
                r["notes"].append(
                    f"flyer.txt(오래된 인쇄물)와 다름 — 최신 hours.txt 기준으로 답했다. "
                    f"전단지 쪽: {flyer.splitlines()[1].strip() if len(flyer.splitlines()) > 1 else flyer.strip()}")
            return r
        if asked_day or "주말" in text or "평일" in text:
            r.update(status="unknown",
                     answer="물어본 요일의 정보가 hours.txt에 없다. 사람 확인이 필요하다.")
            return r
        sched = [ln for ln in body if TIME_RE.search(ln) or "휴무" in ln]
        if not sched:
            r.update(status="unknown", answer="영업시간 자료에서 시간 정보를 찾지 못했다.")
            return r
        for ln in sched:
            ev("hours.txt", ln)
        r["answer"] = " / ".join(sched) + "."
        return r

    # 8) 메뉴.
    if any(k in text for k in MENU_WORDS):
        menu = read_file(data_dir, "menu.txt")
        if menu is None:
            r.update(status="error", answer="menu.txt 자료가 없어 답할 수 없다.")
            return r
        items = menu_items(menu)
        if not items:
            r.update(status="unknown", answer="메뉴 자료에 품목이 없다.")
            return r
        for ln in items:
            ev("menu.txt", ln)
        r["answer"] = f"메뉴: {', '.join(items)}."
        return r

    # 9) 자료로 못 답하는 질문.
    r.update(status="unknown", answer="보유 자료에서 답을 찾지 못했다. 사람에게 확인이 필요하다.")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)

    # request_id는 출력 파일명이 된다 — 경로 조작 문자를 허용하지 않는다.
    # 무효 요청은 질문을 해석하지 않고 error로 응답한다(traceback·정상 해석 금지).
    rid = "invalid-request"
    req = None
    try:
        req = json.loads(Path(a.request).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    bad = None
    if not isinstance(req, dict):
        bad = "요청이 JSON 객체가 아니다."
    elif not isinstance(req.get("request_id"), str) \
            or not SAFE_ID.fullmatch(req["request_id"]):
        bad = "request_id가 없거나 안전하지 않다([A-Za-z0-9_-]{1,64}만 허용)."
    elif not isinstance(req.get("text"), str):
        bad = "text가 없거나 문자열이 아니다."
        rid = req["request_id"]
    elif "now" in req:
        try:
            datetime.fromisoformat(req["now"])
            rid = req["request_id"]
        except (TypeError, ValueError):
            bad = "now가 ISO8601 시각이 아니다."
            rid = req["request_id"]
    else:
        rid = req["request_id"]

    outpath = outdir / f"{rid}.json"
    if bad:
        resp = {"request_id": rid, "status": "error", "answer": bad,
                "evidence": [], "duplicate": False, "notes": []}
        outpath.write_text(json.dumps(resp, ensure_ascii=False, indent=2))
        print(json.dumps(resp, ensure_ascii=False))
        return 0

    req["request_id"] = rid
    if outpath.exists():
        # 순차 재입력 억제일 뿐이다 — 동시 도착·외부 exactly-once 보장 아님.
        prev = json.loads(outpath.read_text(encoding="utf-8"))
        prev["duplicate"] = True
        outpath.write_text(json.dumps(prev, ensure_ascii=False, indent=2))
        print(json.dumps(prev, ensure_ascii=False))
        return 0

    resp = respond(req, a.data)
    outpath.write_text(json.dumps(resp, ensure_ascii=False, indent=2))
    print(json.dumps(resp, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
