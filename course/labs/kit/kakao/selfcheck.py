#!/usr/bin/env python3
"""카카오 모의 어댑터 자체 점검 — 서버 없이 in-process + loopback 왕복.

검증하는 것: 요청 JSON → 어댑터 → 응답 JSON 형식, 응답 시간 기록,
에이전트 비정상 종료·깨진 JSON·응답 누락·잘못된 payload·계약 불량(ID불일치·status·빈답)의 제어된 error 변환.
검증하지 않는 것: 실제 카카오 서버 도달·계정·권한(네이티브 미검증).

사용: python3 labs/kit/kakao/selfcheck.py
"""
import json
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import urllib.request
from http.server import HTTPServer
from pathlib import Path

BASE = Path(__file__).parent
ROOT = BASE.parent.parent.parent  # labs/ 상위 = repo root... 아래에서 보정
KIT = BASE.parent
REPO = KIT.parent.parent

sys.path.insert(0, str(BASE))
from adapter import to_skill_response  # noqa: E402
from serve import handle, make_handler  # noqa: E402

AGENT = f"{sys.executable} {KIT}/agent/mock_agent.py"
DATA = KIT / "personas" / "materials"
FIXTURE = json.loads((BASE / "fixtures" / "skill-request.json").read_text())


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail and not cond else ""))
    return cond


def main():
    results = []
    outdir = Path(tempfile.mkdtemp(prefix="kakao-mock-"))

    # 1) 어댑터 형식 — 일반 응답
    resp = to_skill_response({"request_id": "x", "status": "ok", "answer": "테스트"})
    results.append(check("adapter shape",
                         resp.get("version") == "2.0" and
                         resp["template"]["outputs"][0]["simpleText"]["text"] == "테스트"))

    # 2) 어댑터 형식 — 콜백 첫 응답 (K07)
    cb = to_skill_response({"request_id": "x"}, callback=True)
    results.append(check("callback shape",
                         cb.get("useCallback") is True and "data" in cb))

    # 3) handle() 직접 호출 — 서버 없이 경로만 시험
    r = handle(FIXTURE, AGENT, str(DATA), str(outdir), budget=4.0)
    results.append(check("handle ok",
                         r["template"]["outputs"][0]["simpleText"]["text"].find("15:00") >= 0 and
                         r["_mock_meta"]["within_budget"] is True,
                         detail=json.dumps(r, ensure_ascii=False)[:200]))

    # 4) loopback 왕복 — 실제 HTTP를 로컬에서만
    srv = HTTPServer(("127.0.0.1", 0), make_handler(AGENT, str(DATA), str(outdir), 4.0))
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/skill",
            data=json.dumps(FIXTURE).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp_http:
            body = json.loads(resp_http.read().decode())
        results.append(check("loopback roundtrip",
                             body["version"] == "2.0" and
                             "simpleText" in body["template"]["outputs"][0]))
    finally:
        srv.shutdown()

    # 5) 시간 초과 경로 — 예산 0.001초는 어떤 작업도 못 끝내게 하는 학습 설정
    slow = handle(FIXTURE, AGENT, str(DATA), str(outdir), budget=0.001)
    txt = slow["template"]["outputs"][0]["simpleText"]["text"]
    results.append(check("timeout path",
                         slow["_mock_meta"]["within_budget"] is False or
                         "초과" in txt or "실패" in txt,
                         detail=txt[:120]))

    # ── 음성: handle()은 에이전트 실패를 제어된 error로 변환한다 ──
    # 악성 픽스처 에이전트는 공백이 있는 경로에 둔다 — shlex.split 계약도 같이 시험.
    bdir = Path(tempfile.mkdtemp(prefix="kakao-bad-")) / "dir with space"
    bdir.mkdir()

    def bad_agent(fname, body):
        p = bdir / fname
        p.write_text(body, encoding="utf-8")
        return f'"{sys.executable}" "{p}"'

    def text_of(r):
        return r["template"]["outputs"][0]["simpleText"]["text"]

    # 6) 응답 파일을 쓴 뒤 rc=7 — 정상 답으로 둔갑하면 안 된다
    a_rc7 = bad_agent("rc7.py", textwrap.dedent("""
        import json, sys
        from pathlib import Path
        a = sys.argv
        out = Path(a[a.index("--out") + 1]); out.mkdir(parents=True, exist_ok=True)
        rid = json.loads(Path(a[a.index("--request") + 1]).read_text())["request_id"]
        (out / f"{rid}.json").write_text(json.dumps(
            {"request_id": rid, "status": "ok", "answer": "15:00"}))
        sys.exit(7)
    """))
    r = handle(FIXTURE, a_rc7, str(DATA), str(outdir), budget=4.0)
    results.append(check("handle: rc!=0이면 출력 파일을 신뢰하지 않음",
                         "15:00" not in text_of(r) and "비정상" in text_of(r)
                         and r["_mock_meta"]["agent_rc"] == 7
                         and r["_mock_meta"]["internal_status"] == "error",
                         detail=text_of(r)[:160]))

    # 7) 응답 파일이 깨진 JSON — 예외가 밖으로 새면 안 된다
    a_badjson = bad_agent("badjson.py", textwrap.dedent("""
        import json, sys
        from pathlib import Path
        a = sys.argv
        out = Path(a[a.index("--out") + 1]); out.mkdir(parents=True, exist_ok=True)
        rid = json.loads(Path(a[a.index("--request") + 1]).read_text())["request_id"]
        (out / f"{rid}.json").write_text("{not json")
    """))
    try:
        r = handle(FIXTURE, a_badjson, str(DATA), str(outdir), budget=4.0)
        ok = "깨진 JSON" in text_of(r) \
            and r["_mock_meta"]["internal_status"] == "error"
    except Exception as e:
        ok, r = False, repr(e)
    results.append(check("handle: 깨진 JSON → 제어된 error(예외 전파 없음)",
                         ok, detail=str(r)[:160]))

    # 8) rc=0인데 응답 파일을 안 씀 — 누락은 error
    a_noout = bad_agent("noout.py", "import sys\nsys.exit(0)\n")
    r = handle(FIXTURE, a_noout, str(DATA), str(outdir), budget=4.0)
    results.append(check("handle: 응답 누락 → 제어된 error",
                         "쓰지 않았다" in text_of(r)
                         and r["_mock_meta"]["internal_status"] == "error",
                         detail=text_of(r)[:160]))

    # 9) 잘못된 스킬 payload — 에이전트 호출 전에 제어된 error
    for i, bad_payload in enumerate(("그냥 문자열", {"not": "skill"},
                                     {"userRequest": {"utterance": 42}})):
        try:
            r = handle(bad_payload, AGENT, str(DATA), str(outdir), budget=4.0)
            ok = "올바르지 않다" in text_of(r) \
                and r["_mock_meta"]["internal_status"] == "error"
        except Exception as e:
            ok, r = False, repr(e)
        results.append(check(f"handle: 잘못된 payload #{i} → 제어된 error",
                             ok, detail=str(r)[:160]))

    # 10) request_id 불일치 — 정상 답으로 변환되지 않고 제어된 error
    a_mismatch = bad_agent("mismatch_id.py", textwrap.dedent("""
        import json, sys
        from pathlib import Path
        a = sys.argv
        out = Path(a[a.index("--out") + 1]); out.mkdir(parents=True, exist_ok=True)
        rid = json.loads(Path(a[a.index("--request") + 1]).read_text())["request_id"]
        (out / f"{rid}.json").write_text(json.dumps(
            {"request_id": "OTHER-ID", "status": "ok", "answer": "15:00",
             "evidence": [], "duplicate": False, "notes": []}))
    """))
    r = handle(FIXTURE, a_mismatch, str(DATA), str(outdir), budget=4.0)
    results.append(check("handle: request_id 불일치 → 제어된 error",
                         r["_mock_meta"]["internal_status"] == "error" and
                         "사람 확인 필요" in text_of(r),
                         detail=text_of(r)[:160]))

    # 11) status 계약 밖 값 — 제어된 error
    a_badstatus = bad_agent("bad_status.py", textwrap.dedent("""
        import json, sys
        from pathlib import Path
        a = sys.argv
        out = Path(a[a.index("--out") + 1]); out.mkdir(parents=True, exist_ok=True)
        rid = json.loads(Path(a[a.index("--request") + 1]).read_text())["request_id"]
        (out / f"{rid}.json").write_text(json.dumps(
            {"request_id": rid, "status": "nonsense", "answer": "15:00",
             "evidence": [], "duplicate": False, "notes": []}))
    """))
    r = handle(FIXTURE, a_badstatus, str(DATA), str(outdir), budget=4.0)
    results.append(check("handle: status 계약 밖 값 → 제어된 error",
                         r["_mock_meta"]["internal_status"] == "error" and
                         "사람 확인 필요" in text_of(r),
                         detail=text_of(r)[:160]))

    # 12) answer 빈 문자열 — 제어된 error
    a_emptyans = bad_agent("empty_ans.py", textwrap.dedent("""
        import json, sys
        from pathlib import Path
        a = sys.argv
        out = Path(a[a.index("--out") + 1]); out.mkdir(parents=True, exist_ok=True)
        rid = json.loads(Path(a[a.index("--request") + 1]).read_text())["request_id"]
        (out / f"{rid}.json").write_text(json.dumps(
            {"request_id": rid, "status": "ok", "answer": "",
             "evidence": [], "duplicate": False, "notes": []}))
    """))
    r = handle(FIXTURE, a_emptyans, str(DATA), str(outdir), budget=4.0)
    results.append(check("handle: answer 빈 문자열 → 제어된 error",
                         r["_mock_meta"]["internal_status"] == "error" and
                         "사람 확인 필요" in text_of(r),
                         detail=text_of(r)[:160]))

    # 13) 필수 계약 필드 누락 — 제어된 error
    a_missingfields = bad_agent("missing_fields.py", textwrap.dedent("""
        import json, sys
        from pathlib import Path
        a = sys.argv
        out = Path(a[a.index("--out") + 1]); out.mkdir(parents=True, exist_ok=True)
        rid = json.loads(Path(a[a.index("--request") + 1]).read_text())["request_id"]
        (out / f"{rid}.json").write_text(json.dumps(
            {"request_id": rid, "status": "ok", "answer": "15:00"}))
    """))
    r = handle(FIXTURE, a_missingfields, str(DATA), str(outdir), budget=4.0)
    results.append(check("handle: 공통 계약 필드 누락 → 제어된 error",
                         r["_mock_meta"]["internal_status"] == "error" and
                         "사람 확인 필요" in text_of(r),
                         detail=text_of(r)[:160]))

    # 14) 응답이 JSON 배열 [] — 같은 handle 호출에서 rc0·실제 [] 파일·
    #     request ID·비객체 진단을 함께 확인한다. rc가 0이거나 일반 error가
    #     나오기만 해서는 PASS가 아니다(다른 실패 경로와 구별).
    def nonobject_probe(fname, body, expected_raw):
        """생성 stub을 전용 outdir에 붙여 실제 handle을 호출한다.
        합격(논리곱): agent_rc==0 ∧ 이 호출의 유일한 req-ID에 대응하는 응답
        파일이 존재 ∧ 파일 내용이 정확히 expected_raw ∧ JSON 파싱 값 일치 ∧
        internal_status==error ∧ 'JSON 객체가 아니다' 진단 ∧ 예외 전파 없음 ∧
        그 외 JSON 잔여 파일 없음."""
        agent = bad_agent(fname, body)
        o = Path(tempfile.mkdtemp(prefix="kakao-nonobj-"))
        obs = {}
        try:
            r = handle(FIXTURE, agent, str(DATA), str(o), budget=4.0)
            reqs = sorted(o.glob("req-*.json"))
            rid = json.loads(reqs[0].read_text(encoding="utf-8"))["request_id"] \
                if len(reqs) == 1 else None
            rfile = o / f"{rid}.json" if rid else None
            raw = rfile.read_text(encoding="utf-8") \
                if rfile is not None and rfile.exists() else None
            stray = sorted(f.name for f in o.glob("*.json")
                           if f != (reqs[0] if reqs else None) and f != rfile)
            meta = r["_mock_meta"]
            ok = (meta["agent_rc"] == 0 and rid is not None
                  and raw is not None and not stray
                  and raw.strip() == expected_raw
                  and json.loads(raw) == json.loads(expected_raw)
                  and meta["internal_status"] == "error"
                  and "사람 확인 필요" in text_of(r)
                  and "JSON 객체가 아니다" in text_of(r))
            obs = {"agent_rc": meta["agent_rc"], "rid": rid, "raw": raw,
                   "stray": stray, "text": text_of(r)[:120],
                   "request_file": str(reqs[0]) if len(reqs) == 1 else None,
                   "response_file": str(rfile) if rfile else None,
                   "agent_command": agent, "result": r}
        except Exception as e:
            ok, obs = False, {"exc": repr(e)}
        obs["accepted"] = ok
        (o / "observation.json").write_text(json.dumps(obs, ensure_ascii=False,
                                                     indent=2), encoding="utf-8")
        return ok, obs

    arr_body = textwrap.dedent("""
        import json, sys
        from pathlib import Path
        a = sys.argv
        out = Path(a[a.index("--out") + 1]); out.mkdir(parents=True, exist_ok=True)
        rid = json.loads(Path(a[a.index("--request") + 1]).read_text())["request_id"]
        (out / f"{rid}.json").write_text("[]", encoding="utf-8")
    """)
    ok, obs = nonobject_probe("array_resp.py", arr_body, "[]")
    results.append(check("handle: 응답이 배열 [] → 제어된 error(예외 없음)",
                         ok, detail=json.dumps(obs, ensure_ascii=False)))

    # 같은 검사가 다른 실패 경로를 배열 PASS로 세지 않는지(음성 대조).
    obj_body = arr_body.replace(
        '"[]"', 'json.dumps({"request_id": rid, "status": "ok", '
        '"answer": "15:00", "evidence": [], "duplicate": False, "notes": []})')
    for mname, mbody, why in (
            ("array_noimp", arr_body.replace("import json, sys", "import sys"),
             "import 누락 stub(rc1·출력 없음)"),
            ("array_rc1", arr_body + "sys.exit(1)\n", "[] 기록 후 rc1"),
            ("array_noout", "import sys\nsys.exit(0)\n", "rc0·출력 없음"),
            ("array_obj", obj_body, "정상 객체 응답")):
        ok_m, obs_m = nonobject_probe(f"{mname}.py", mbody, "[]")
        results.append(check(f"handle: {why}는 배열 검사를 통과하지 않음",
                             not ok_m,
                             detail=json.dumps(obs_m, ensure_ascii=False)[:160]))

    # 15) 응답이 JSON null / 숫자 / 불리언 등 비객체 원시타입 — 배열과 같은 결합 검사
    for kind, val_repr in (("null", "null"), ("number", "7"), ("boolean", "true")):
        prim_body = textwrap.dedent(f"""
            import json, sys
            from pathlib import Path
            a = sys.argv
            out = Path(a[a.index("--out") + 1]); out.mkdir(parents=True, exist_ok=True)
            rid = json.loads(Path(a[a.index("--request") + 1]).read_text())["request_id"]
            (out / f"{{rid}}.json").write_text("{val_repr}", encoding="utf-8")
        """)
        ok, obs = nonobject_probe(f"prim_{kind}.py", prim_body, val_repr)
        results.append(check(f"handle: 응답이 {kind}({val_repr}) → 제어된 error",
                             ok, detail=json.dumps(obs, ensure_ascii=False)[:160]))

    # 16) 외부 에이전트의 status=error 응답이지만 계약 필드 누락 — 제어된 error로 진단
    a_broken_err = bad_agent("broken_err.py", textwrap.dedent("""
        import json, sys
        from pathlib import Path
        a = sys.argv
        out = Path(a[a.index("--out") + 1]); out.mkdir(parents=True, exist_ok=True)
        rid = json.loads(Path(a[a.index("--request") + 1]).read_text())["request_id"]
        (out / f"{rid}.json").write_text(json.dumps({"status": "error"}))
    """))
    r = handle(FIXTURE, a_broken_err, str(DATA), str(outdir), budget=4.0)
    results.append(check("handle: 외부 불량 error 응답 → 스키마 검증 후 error 진단",
                         r["_mock_meta"]["internal_status"] == "error" and
                         "계약 위반" in text_of(r),
                         detail=text_of(r)[:160]))

    # 17) 모든 계약을 충족한 정상 제어된 error 응답 수용
    a_valid_err = bad_agent("valid_err.py", textwrap.dedent("""
        import json, sys
        from pathlib import Path
        a = sys.argv
        out = Path(a[a.index("--out") + 1]); out.mkdir(parents=True, exist_ok=True)
        rid = json.loads(Path(a[a.index("--request") + 1]).read_text())["request_id"]
        (out / f"{rid}.json").write_text(json.dumps({
            "request_id": rid, "status": "error", "answer": "제어된 오류 사유",
            "evidence": [], "duplicate": False, "notes": ["오류 메모"]
        }))
    """))
    r = handle(FIXTURE, a_valid_err, str(DATA), str(outdir), budget=4.0)
    results.append(check("handle: 정당한 error 계약 응답 → 정상 전달",
                         r["_mock_meta"]["internal_status"] == "error" and
                         "제어된 오류 사유" in text_of(r) and
                         "사람 확인 필요" in text_of(r),
                         detail=text_of(r)[:160]))

    print(f"\n{sum(results)}/{len(results)} 통과 — 모의(O) 수준. 네이티브(K) 미검증.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
