#!/usr/bin/env python3
"""localhost 전용 모의 스킬 서버 — 카카오가 부르는 흉내를 낸다.

실제 카카오는 이 서버에 접근할 수 없다. K06이 요구하는 것은
공인 IP/공중망 도메인이며, localhost 성공은 카카오 접근 증거가 아니다.
이 서버는 '요청 JSON → 어댑터 → 응답 JSON' 경로와 응답 시간만 시험한다(증거: O).

사용:
  python3 serve.py --port 8787 \
      --agent "python3 labs/kit/agent/mock_agent.py" \
      --data labs/kit/personas/materials --out labs/kit/kakao/_work

실패 변환: 에이전트의 비정상 종료(rc!=0)·응답 파일 누락·깨진 JSON·
계약 필드 불량·timeout·잘못된 스킬 payload는 전부 제어된 error
simpleText로 변환한다 — traceback이 호출자에게 새지 않는다.
"""
import argparse
import json
import shlex
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from adapter import to_skill_response  # noqa: E402

STATUSES = {"ok", "unknown", "clarify", "escalate", "error"}
REQUIRED_FIELDS = {
    "request_id": str, "status": str, "answer": str,
    "evidence": list, "duplicate": bool, "notes": list
}


def handle(payload, agent_cmd, data_dir, outroot, budget):
    """스킬 요청 한 건을 처리한다. 서버 없이도 직접 호출해 시험할 수 있다."""
    start = time.monotonic()
    rid = f"k{int(start * 1000) % 10_000_000}"
    meta = {"agent_rc": None}

    def internal_error(msg):
        return {"request_id": rid, "status": "error", "answer": msg,
                "evidence": [], "duplicate": False, "notes": [msg]}

    if not isinstance(payload, dict) \
            or not isinstance(payload.get("userRequest"), dict) \
            or not isinstance(payload["userRequest"].get("utterance"), str):
        internal = internal_error("스킬 요청 형식이 올바르지 않다.")
    else:
        workdir = Path(outroot)
        workdir.mkdir(parents=True, exist_ok=True)
        reqpath = workdir / f"req-{rid}.json"
        reqpath.write_text(json.dumps(
            {"request_id": rid,
             "text": payload["userRequest"]["utterance"]},
            ensure_ascii=False), encoding="utf-8")
        cmd = shlex.split(agent_cmd) + ["--request", str(reqpath),
                                        "--data", str(data_dir),
                                        "--out", str(workdir)]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=budget)
            meta["agent_rc"] = p.returncode
        except subprocess.TimeoutExpired:
            p = None
            internal = internal_error(
                f"처리 시간 초과(예산 {budget}s) — 학습 설정값")
        if p is not None:
            rfile = workdir / f"{rid}.json"
            if p.returncode != 0:
                internal = internal_error(
                    f"에이전트 비정상 종료 rc={p.returncode} — 출력 파일을 신뢰하지 않는다")
            elif not rfile.exists():
                internal = internal_error("에이전트가 응답 파일을 쓰지 않았다")
            else:
                try:
                    content = rfile.read_text(encoding="utf-8")
                    raw_data = json.loads(content)
                except (OSError, UnicodeDecodeError):
                    internal = internal_error("에이전트 응답 파일 읽기 실패(조회/UTF-8 오류)")
                except json.JSONDecodeError:
                    internal = internal_error("에이전트 응답이 깨진 JSON이다")
                else:
                    if not isinstance(raw_data, dict):
                        internal = internal_error("에이전트 응답이 JSON 객체가 아니다")
                    else:
                        probs = []
                        for k, t in REQUIRED_FIELDS.items():
                            if k not in raw_data:
                                probs.append(f"필수 필드 '{k}' 없음")
                            elif not isinstance(raw_data[k], t):
                                probs.append(f"필드 '{k}' 타입 불량({t.__name__} 필요)")
                        if not probs:
                            if raw_data["request_id"] != rid:
                                probs.append(f"request_id 불일치({raw_data['request_id']} != {rid})")
                            if raw_data["status"] not in STATUSES:
                                probs.append(f"status '{raw_data['status']}'는 계약 밖 값")
                            if not raw_data["answer"].strip():
                                probs.append("answer가 비어 있거나 공백뿐임")
                            for idx, ev in enumerate(raw_data["evidence"]):
                                if not isinstance(ev, dict) or not isinstance(ev.get("source"), str) or not isinstance(ev.get("detail"), str):
                                    probs.append(f"evidence[{idx}] 계약 불량")
                            for idx, n in enumerate(raw_data["notes"]):
                                if not isinstance(n, str):
                                    probs.append(f"notes[{idx}] 타입 불량")
                        if probs:
                            internal = internal_error(f"에이전트 응답 계약 위반: {'; '.join(probs)}")
                        else:
                            internal = raw_data
    elapsed = time.monotonic() - start
    resp = to_skill_response(internal)
    meta.update({"elapsed_sec": round(elapsed, 3),
                 "internal_status": internal.get("status"),
                 # 시간 비교일 뿐 응답 품질·성공의 증거가 아니다.
                 "within_budget": elapsed <= budget})
    resp["_mock_meta"] = meta
    return resp


def make_handler(agent_cmd, data_dir, outroot, budget):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/skill":
                self.send_response(404)
                self.end_headers()
                return
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error":"bad json"}')
                return
            resp = handle(payload, agent_cmd, data_dir, outroot, budget)
            data = json.dumps(resp, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--budget", type=float, default=4.0,
                    help="학습용 응답 예산(초). K06 문서의 5초와 별개의 학습 설정.")
    a = ap.parse_args()
    print(f"모의 스킬 서버: http://127.0.0.1:{a.port}/skill  "
          f"(외부에서 접근 불가 — 카카오 연결 증거 아님)")
    HTTPServer(("127.0.0.1", a.port),
               make_handler(a.agent, a.data, a.out, a.budget)).serve_forever()


if __name__ == "__main__":
    main()
