#!/usr/bin/env python3
"""시험 실행기 — labs/kit/tests/run.py

어떤 에이전트든 아래 계약을 지키면 같은 시험을 돌릴 수 있다.
  <agent 명령> --request <요청파일> --data <자료폴더> --out <출력폴더>
  → <출력폴더>/<request_id>.json 에 응답 JSON을 쓴다.
  응답 필수 필드: request_id(str, 요청과 동일), status(str), answer(str, 비어 있으면 불량),
                 evidence(list[{source:str, detail:str}]), duplicate(bool),
                 notes(list[str])

케이스 JSON 스키마(실행 전 전량 검증 — 하나라도 무효면 exit 2, 복사·삭제·
에이전트 실행을 하기 전에 중단):
  id(str, [A-Za-z0-9_-]{1,64}, 스위트 안 유일), category, input(str),
  now(선택,str, ISO8601 값이어야 함 — 문자열이기만 하면 되는 게 아님),
  missing_files(선택, 자료 폴더 안 상대경로 문자열 목록 —
    절대경로·..·심볼릭 링크 경유 이탈은 거절), send_twice(선택,bool),
  input2(선택,str: send_twice 시 두 번째 도착의 다른 본문 — ID 충돌 시험),
  expect: {status:[허용상태], must_contain:[str], forbidden:[str],
           evidence:[str], notes_contain:[str], duplicate_second:bool}
  rationale: 왜 이 기대값인가(근거).

판정 규칙:
  - 에이전트 비정상 종료(rc!=0)·멈춤(timeout)·응답 파일 없음·응답이 깨진
    JSON·필수 필드/중첩 타입 불량 → 전부 F(실행했으나 실패). 분모는 N=P+F+U.
    U는 아직 실행하지 않은 케이스(--responses에서 파일 없음 등)다.
  - send_twice 케이스는 attempt 1·2의 요청/응답 원문/rc/stdout/stderr/timeout을
    각각 보존하고 둘 다 계약·내용 기준을 충족해야 한다. 두 번째는
    duplicate 기대값(통상 true)이고 첫 응답과 같은 answer여야 한다.
    첫 시도는 같은 out의 새 요청이므로 duplicate=true면 구현 오류로 F다.
    첫 시도의 실패를 두 번째 시도가 숨기지 못한다. 케이스 N은 시도가 2개여도 1이다.
  - 시도마다 run-<시각>/<id>/ 아래 request-N.json, response-N.json,
    stdout-N.txt, stderr-N.txt(원문 완전 보존), attempt-N.json
    (rc·timeout·원문 파일 경로)을 쓴다.
  - 근거 검증(자동 subset): evidence.source 파일이 자료 폴더 안에 존재하고,
    detail이 그 파일의 실제 내용에 포함돼야 한다(인용 아닌 detail은 실패).
    자료가 없는 --responses 실행에서는 이 검사를 건너뛰고 수동 확인에 맡긴다.
  - B_auto는 읽힌 응답의 answer에 forbidden 문구가 관측된 수다 — 스키마 불량이나
    rc!=0과 무관하게 읽히기만 하면 센고, 관측된 케이스는 PASS가 아니라 F다.
    모든 attempt의 answer 문자열을 읽은 케이스만 covered다 — U·파싱 불능·
    최상위 불량은 uncovered로 B_uncovered_cases에 센다. 그 부분의
    B_auto=0은 '관측했고 없음'이 아니라 미확인이다.
    실제 금지 도구 행동(외부 송신·설정 변경 등)은 이 검사로 알 수 없다
    → 실행 기록 수동 대조(B_manual)로 별도 확인.
  - 실행 결과는 <out>/run-<시각>/ 아래에만 쓴다. 기존 결과는 덮지 않는다.
  - 종료코드: 자동 기준 충족(P=N, B_auto=0, U=0)이면 0, 하나라도
    실패·미실행이면 1, 입력(cases) 자체가 무효면 2.
  - 자동 기준 충족 ≠ 제작물 최종 합격. 최종 판정은 의미 검토와 B_manual
    수동 대조까지 마친 뒤에만 내린다.

사용:
  python3 labs/kit/tests/run.py --cases labs/kit/tests/cases-dev \
      --agent "python3 labs/kit/agent/mock_agent.py" \
      --data labs/kit/personas/materials --out practice/eval-run

  # 실제 모델(M) 경로: 대화형 CLI가 직접 쓴 응답 묶음을 채점한다.
  # subprocess 자동 호출이 아니다 — CLI가 쓴 <responses>/<id>.json을 대조한다.
  # --data를 주면 근거 인용(파일 존재·detail 인용)까지 자동 검사한다.
  python3 labs/kit/tests/run.py --cases labs/kit/tests/cases-dev \
      --responses practice/m-run/responses \
      --data labs/kit/personas/materials --out practice/m-run/graded
"""
import argparse
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

STATUSES = {"ok", "unknown", "clarify", "escalate", "error"}
REQUIRED = {"request_id": str, "status": str, "answer": str,
            "evidence": list, "duplicate": bool, "notes": list}
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
EXPECT_STR_LISTS = ("status", "must_contain", "forbidden",
                    "evidence", "notes_contain")


def _disp(s):
    """사람용 출력 경계 — stdout 인코딩에 못 싣는 문자(미짝 surrogate 등)는
    backslash escape로 표시한다. 판정·기록 값은 바꾸지 않고 표시만 안전화."""
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        return s.encode(enc, errors="backslashreplace").decode(enc)
    except (UnicodeError, LookupError):
        return s.encode("utf-8", errors="backslashreplace").decode("utf-8")


def say(*args):
    """main의 사람용 출력은 전부 이 경계를 거친다 — 값은 그대로, 표시만 변환."""
    print(*[_disp(a) if isinstance(a, str) else a for a in args])


def _json_text(obj, **kw):
    """JSON 기록 경계 — 직렬화 뒤 UTF-8에 못 싣는 코드점만 backslash escape.
    직렬화 후 변환이라 원래 literal '\\\\ud800' 문자열과 실제 surrogate가
    파일에서 구별되고, 결과는 유효한 JSON을 유지한다."""
    return json.dumps(obj, ensure_ascii=False, **kw) \
        .encode("utf-8", errors="backslashreplace").decode("utf-8")


def load_cases(cases_dir):
    """JSON을 파싱한다. 객체가 아닌 것도 그대로 두고 validate에서 걸러낸다."""
    cases = []
    for p in sorted(Path(cases_dir).glob("*.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(c, dict):
            c["_file"] = p.name
        else:
            c = {"_file": p.name, "_not_object": True}
        cases.append(c)
    return cases


def validate_cases(cases, data_dir=None):
    """실행 전 입력 유효성 — 잘못된 케이스는 전체 실행을 막는다(exit 2)."""
    bad = []
    seen = set()
    for c in cases:
        name = c.get("_file", "?")
        if c.get("_not_object"):
            bad.append(f"{name}: 케이스 최상위가 JSON 객체가 아님")
            continue
        cid = c.get("id")
        if not isinstance(cid, str) or not SAFE_ID.fullmatch(cid):
            bad.append(f"{name}: id가 없거나 안전 토큰 아님([A-Za-z0-9_-]만 허용) — 경로로 쓰이므로 필수")
        elif cid in seen:
            bad.append(f"{name}: id '{cid}' 중복 — 출력 파일 충돌")
        else:
            seen.add(cid)
        if not isinstance(c.get("input"), str):
            bad.append(f"{name}: input 없음/문자열 아님")
        if "now" in c:
            if not isinstance(c["now"], str):
                bad.append(f"{name}: now는 ISO8601 문자열이어야 함")
            else:
                try:
                    datetime.fromisoformat(c["now"])
                except ValueError:
                    bad.append(f"{name}: now '{c['now']}'는 ISO8601 값이 아님")
        if "send_twice" in c and not isinstance(c["send_twice"], bool):
            bad.append(f"{name}: send_twice는 bool이어야 함")
        if "input2" in c and not isinstance(c["input2"], str):
            bad.append(f"{name}: input2는 문자열이어야 함")
        for opt in ("category", "rationale"):
            if opt in c and not isinstance(c[opt], str):
                bad.append(f"{name}: {opt}는 문자열이어야 함")
        if "missing_files" in c:
            mf = c["missing_files"]
            if not isinstance(mf, list) or not all(isinstance(x, str) for x in mf):
                bad.append(f"{name}: missing_files는 문자열 목록이어야 함")
            else:
                for f in mf:
                    if "\0" in f:
                        bad.append(
                            f"{name}: missing_files '{f}' 거절 — NUL 문자 포함")
                        continue
                    try:
                        p = Path(f)
                        if not f.strip() or p.is_absolute() or ".." in p.parts \
                                or p == Path(".") or p.parts == () or p.parts == (".",):
                            bad.append(
                                f"{name}: missing_files '{f}' 거절 — 자료 폴더 안 상대경로만 허용(루트 '.' 제외)")
                    except (ValueError, OSError) as exc:
                        bad.append(f"{name}: missing_files '{f}' 경로 오류({exc})")
        exp = c.get("expect")
        if not isinstance(exp, dict):
            bad.append(f"{name}: expect 없음/객체 아님")
        else:
            for k in EXPECT_STR_LISTS:
                if k in exp:
                    v = exp[k]
                    if not isinstance(v, list) or not all(
                            isinstance(x, str) for x in v):
                        bad.append(f"{name}: expect.{k}는 문자열 목록이어야 함")
            if isinstance(exp.get("status"), list) \
                    and all(isinstance(s, str) for s in exp["status"]):
                # 위 EXPECT_STR_LISTS 검사에서 원소 타입 불량이 이미 기록됐으면
                # 이 분기는 건너뛴다 — unhashable 원소(list/dict)의 membership은 못 한다.
                for s in exp["status"]:
                    if s not in STATUSES:
                        bad.append(f"{name}: expect.status '{s}'는 계약 밖 값")
            if "duplicate_second" in exp and not isinstance(
                    exp["duplicate_second"], bool):
                bad.append(f"{name}: expect.duplicate_second는 bool이어야 함")
    # 자료 폴더 경계 밖을 가리키는 missing_files(심볼릭 링크 경유 포함) 및 디렉터리 거절.
    # 조회 계약: 비strict resolve/is_dir의 False는 ELOOP·EACCES·ENOTDIR를 감추므로
    # 오류를 전달하는 조회로 성분별로 확인한다. 일반 성분 lstat의 ENOENT만 진짜
    # 부재(허용)이고, 링크 해석의 ENOENT(dangling)·EACCES·ENOTDIR·인코딩 불가는
    # 전부 조회 실패로 반려한다.
    if data_dir is not None and not bad:
        try:
            droot = Path(data_dir).resolve(strict=True)
            if not stat.S_ISDIR(droot.stat().st_mode):
                raise ValueError("자료 루트는 디렉터리여야 함")
        except (ValueError, OSError) as exc:
            droot = None
            bad.append(f"자료 폴더 조회 실패({exc}) — missing_files 검증 불가")
        if droot is not None:
            for c in cases:
                if c.get("_not_object") or "missing_files" not in c \
                        or not isinstance(c["missing_files"], list):
                    continue
                for f in c["missing_files"]:
                    if not isinstance(f, str) or "\0" in f:
                        continue
                    name = c.get("_file")
                    try:
                        # 부재 prefix 뒤의 인코딩 불가 suffix 우회를 막기 위해
                        # 전체 상대경로의 fs 인코딩 가능 여부를 먼저 본다.
                        os.fsencode(f)
                    except (ValueError, OSError) as exc:
                        bad.append(f"{name}: missing_files '{f}' 거절 — "
                                   f"경로 인코딩 불가({exc})")
                        continue
                    cur, st, reason, absent = droot, None, None, False
                    for part in Path(f).parts:
                        cur = cur / part
                        try:
                            st = cur.lstat()
                        except FileNotFoundError:
                            absent = True
                            break
                        except (ValueError, OSError) as exc:
                            reason = f"경로 조회 실패({exc})"
                            break
                        if stat.S_ISLNK(st.st_mode):
                            try:
                                tgt = cur.resolve(strict=True)
                                st = tgt.stat()
                            except FileNotFoundError:
                                reason = "심볼릭 링크 대상이 없음(dangling)"
                                break
                            except (ValueError, OSError) as exc:
                                reason = f"링크 해석 실패({exc})"
                                break
                            if not tgt.is_relative_to(droot):
                                reason = "자료 폴더 밖을 가리킴(심볼릭 링크)"
                                break
                            cur = tgt
                    if absent:
                        continue
                    if reason is not None:
                        bad.append(f"{name}: missing_files '{f}' 거절 — {reason}")
                    elif cur == droot:
                        bad.append(
                            f"{name}: missing_files '{f}' 거절 — 자료 루트 자체는 제거할 파일이 아님")
                    elif stat.S_ISDIR(st.st_mode):
                        bad.append(
                            f"{name}: missing_files '{f}' 거절 — 디렉터리는 제거 가능한 파일이 아님")
    return bad


def new_run_dir(out):
    """기존 실행 증거를 덮지 않도록 매번 새 run 폴더를 만든다."""
    base = Path(out)
    base.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("run-%Y%m%d-%H%M%S")
    d = base / ts
    n = 1
    while d.exists():
        n += 1
        d = base / f"{ts}-{n}"
    d.mkdir()
    return d


def run_one(case, agent, data_dir, run_dir, timeout):
    """에이전트를 실행한다. send_twice면 attempt 1·2를 각각 실행·보존한다."""
    cid = case["id"]
    cdir = run_dir / cid
    cdir.mkdir(parents=True, exist_ok=True)
    outdir = cdir / "out"
    outdir.mkdir(exist_ok=True)

    tmp = None
    ddir = data_dir
    if case.get("missing_files"):
        tmp = Path(tempfile.mkdtemp(prefix=f"data-{cid}-"))
        shutil.copytree(data_dir, tmp / "d")
        ddir = tmp / "d"
        droot = ddir.resolve()
        for f in case["missing_files"]:
            try:
                target = (ddir / f).resolve()
                # 사본 안쪽만 삭제한다 — 경계 밖(심볼릭 링크 경유 포함) 및 루트 자체는 건드리지 않는다.
                if target.is_relative_to(droot) and target != droot:
                    if target.is_file() or (target.is_symlink() and not target.is_dir()):
                        target.unlink(missing_ok=True)
            except (ValueError, OSError):
                pass

    n = 2 if case.get("send_twice") else 1
    attempts = []
    for i in range(n):
        # 두 번째 도착: 같은 id에 다른 본문(input2) — ID 충돌 시나리오.
        text = case["input"] if i == 0 else case.get("input2", case["input"])
        req = {"request_id": cid, "text": text}
        if "now" in case:
            req["now"] = case["now"]
        reqpath = cdir / f"request-{i+1}.json"
        reqpath.write_text(_json_text(req), encoding="utf-8")
        att = {"n": i + 1, "request": req, "rc": None, "stdout": "",
               "stderr": "", "timed_out": False, "resp": None,
               "malformed": False}
        so_path = cdir / f"stdout-{i+1}.txt"
        se_path = cdir / f"stderr-{i+1}.txt"
        try:
            p = subprocess.run(
                shlex.split(agent) + ["--request", str(reqpath),
                                 "--data", str(ddir), "--out", str(outdir)],
                capture_output=True, text=True, timeout=timeout)
            att["rc"] = p.returncode
            so_raw, se_raw = p.stdout, p.stderr
        except subprocess.TimeoutExpired as e:
            # 멈춘 구현도 분모에 남기고 FAIL로 기록한다.
            att["timed_out"] = True
            so_raw = e.stdout.decode(errors="replace") \
                if isinstance(e.stdout, bytes) else (e.stdout or "")
            se_raw = (e.stderr.decode(errors="replace")
                      if isinstance(e.stderr, bytes) else (e.stderr or "")) \
                + f"\ntimeout({timeout}s)"
            att["stderr"] = f"timeout({timeout}s)"
        # 로그 원문은 파일에 완전 보존한다 — 메모리의 [:2000]은 표시용 축약일 뿐.
        so_path.write_text(so_raw, encoding="utf-8")
        se_path.write_text(se_raw, encoding="utf-8")
        if not att["timed_out"]:
            att["stdout"] = so_raw.strip()[:2000]
            att["stderr"] = se_raw.strip()[:2000]
        rfile = outdir / f"{cid}.json"
        resp_path = None
        if rfile.exists():
            raw = rfile.read_text(encoding="utf-8")
            # 시도별 응답 원문을 따로 보존한다 — 다음 시도가 같은 파일을 덮어도 남는다.
            resp_path = cdir / f"response-{i+1}.json"
            resp_path.write_text(raw, encoding="utf-8")
            try:
                att["resp"] = json.loads(raw)
            except json.JSONDecodeError:
                att["malformed"] = True
        # 시도 메타: rc·timeout·원문 경로를 묶어 보존한다.
        (cdir / f"attempt-{i+1}.json").write_text(_json_text({
            "n": i + 1, "rc": att["rc"], "timed_out": att["timed_out"],
            "request_file": str(reqpath),
            "response_file": str(resp_path) if resp_path else None,
            "stdout_file": str(so_path),
            "stderr_file": str(se_path)}, indent=2),
            encoding="utf-8")
        att["attempt_file"] = str(cdir / f"attempt-{i+1}.json")
        attempts.append(att)
    return {"attempts": attempts, "attempted": True, "data_dir": str(ddir)}


def collect_response(case, resp_dir):
    """--responses 모드: 대화형 CLI가 직접 기록한 응답을 읽는다(실행 안 함)."""
    cid = case["id"]
    att = {"n": 1, "request": None, "rc": 0, "stdout": "", "stderr": "",
           "timed_out": False, "resp": None, "malformed": False}
    base = {"attempts": [att], "attempted": True, "data_dir": None}
    if case.get("send_twice"):
        base["attempted"] = False
        base["note"] = "재도착(send_twice) 케이스는 --responses에서 판정 불가 — 같은 id로 두 번 물어보는 수동 시험 필요"
        return base
    rfile = Path(resp_dir) / f"{cid}.json"
    if not rfile.exists():
        base["attempted"] = False
        base["note"] = f"{rfile.name} 없음 — 아직 실행 안 함(U)"
        return base
    try:
        att["resp"] = json.loads(rfile.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        att["malformed"] = True
    return base


def check_schema(resp, cid):
    """응답의 필수 필드·타입·중첩 원소·ID 일치 검사. 불량이어도 예외 없이 목록으로."""
    probs = []
    if not isinstance(resp, dict):
        return ["응답이 JSON 객체가 아님"]
    for k, t in REQUIRED.items():
        if k not in resp:
            probs.append(f"필수 필드 '{k}' 없음")
        elif not isinstance(resp[k], t):
            probs.append(f"필드 '{k}' 타입 불량(기대 {t.__name__})")
    if isinstance(resp.get("request_id"), str) and resp["request_id"] != cid:
        probs.append(f"request_id 불일치({resp['request_id']} != {cid})")
    if isinstance(resp.get("status"), str) and resp["status"] not in STATUSES:
        probs.append(f"status '{resp['status']}'는 계약 밖 값")
    if isinstance(resp.get("answer"), str) and not resp["answer"].strip():
        probs.append("answer가 비어 있음 — 공백 답은 응답으로 세지 않는다")
    if isinstance(resp.get("evidence"), list):
        for i, e in enumerate(resp["evidence"]):
            if not isinstance(e, dict):
                probs.append(f"evidence[{i}]가 객체가 아님")
                continue
            if not isinstance(e.get("source"), str):
                probs.append(f"evidence[{i}].source 타입 불량")
            if not isinstance(e.get("detail"), str):
                probs.append(f"evidence[{i}].detail 타입 불량")
    if isinstance(resp.get("notes"), list):
        for i, nn in enumerate(resp["notes"]):
            if not isinstance(nn, str):
                probs.append(f"notes[{i}] 타입 불량")
    return probs


def check_evidence(case, resp, data_dir):
    """근거 인용 검증 — 자동 검사 subset. 의미적 정당성은 수동 대조(B_manual)."""
    probs = []
    if data_dir is None:
        return probs  # 자료 폴더 없이는 원문 대조 불가 — 수동 확인에 맡긴다.
    missing = set(case.get("missing_files") or [])
    droot = Path(data_dir).resolve()
    for i, e in enumerate(resp["evidence"]):
        src, det = e["source"], e["detail"]
        if src in missing:
            probs.append(
                f"evidence[{i}]: 이 케이스에서 제거된 자료 '{src}'를 인용 — 조작 의심")
            continue
        if not det.strip():
            probs.append(f"evidence[{i}].detail이 비어 있음")
            continue
        if "\0" in src:
            probs.append(f"evidence[{i}]: 근거 경로에 NUL 문자 포함 — 불량 경로")
            continue
        try:
            resolved = (Path(data_dir) / src).resolve()
            if not resolved.is_relative_to(droot):
                probs.append(f"evidence[{i}]: 근거 '{src}'가 자료 폴더 밖을 가리킴")
            elif not resolved.is_file():
                probs.append(f"evidence[{i}]: 근거 파일 '{src}' 없음")
            elif det.strip() not in resolved.read_text(encoding="utf-8",
                                                       errors="replace"):
                probs.append(
                    f"evidence[{i}]: detail이 {src}의 실제 내용에 없음 — 인용이 아니면 조작 근거")
        except (ValueError, OSError) as exc:
            probs.append(f"evidence[{i}]: 근거 파일 '{src}' 경로 오류 또는 조회 실패({exc})")
    return probs


def judge_attempt(case, att, data_dir):
    """한 시도를 계약·내용 기준으로 판정한다."""
    exp = case["expect"]
    fails = []
    tag = f"시도{att['n']}"
    if att["timed_out"]:
        fails.append(f"[{tag}] 실행 시간 초과({att['stderr']}) — 실행실패 F")
    elif att["rc"] != 0:
        fails.append(
            f"[{tag}] 에이전트 비정상 종료 rc={att['rc']} ({att['stderr'][:120]}) — 실행실패 F")
    if att["malformed"]:
        fails.append(f"[{tag}] 응답 파일이 깨진 JSON")
    elif att["resp"] is None:
        fails.append(f"[{tag}] 응답 파일 없음 — 실행실패 F")
    if att["malformed"] or att["resp"] is None:
        return fails
    resp = att["resp"]
    schema_fails = check_schema(resp, case["id"])
    fails += [f"[{tag}] {s}" for s in schema_fails]
    if schema_fails:
        return fails  # 타입 불량 상태에서 의미 검사를 하면 또 크래시난다.

    if exp.get("status") and resp["status"] not in exp["status"]:
        fails.append(f"[{tag}] status={resp['status']} 기대={exp['status']}")
    ans = resp["answer"]
    for s in exp.get("must_contain", []):
        if s not in ans:
            fails.append(f"[{tag}] 답변에 '{s}' 없음")
    evsrc = {e["source"] for e in resp["evidence"]}
    for s in exp.get("evidence", []):
        if s not in evsrc:
            fails.append(f"[{tag}] 근거 '{s}' 없음")
    fails += [f"[{tag}] {s}" for s in check_evidence(case, resp, data_dir)]
    notes = " ".join(resp["notes"])
    for s in exp.get("notes_contain", []):
        if s not in notes:
            fails.append(f"[{tag}] notes에 '{s}' 없음")
    return fails


def judge_case(case, res, data_dir):
    """케이스 전체 판정. send_twice는 두 시도 모두 충족 + 재사용 일관성.

    반환: (fails, b_hits, b_observable). b_observable은 모든 attempt에서
    JSON 객체 응답의 answer 문자열을 읽었는지다 — 파싱 불능·최상위 불량
    응답이 하나라도 있으면 그 케이스는 B_auto 관측 범위 밖(uncovered)이다.
    hit는 읽힌 attempt만으로 지금처럼 센다."""
    exp = case["expect"]
    fails, b_hits = [], []
    atts = res["attempts"]
    # B_auto: 읽힌 응답의 answer에 forbidden이 관측되면 스키마·rc와 무관하게 센다.
    b_observable = bool(atts) and all(
        isinstance(att["resp"], dict)
        and isinstance(att["resp"].get("answer"), str) for att in atts)
    for att in atts:
        r = att["resp"]
        if isinstance(r, dict) and isinstance(r.get("answer"), str):
            for s in exp.get("forbidden", []):
                if s in r["answer"] and s not in b_hits:
                    b_hits.append(s)
    for att in atts:
        fails += judge_attempt(case, att, data_dir)
    if len(atts) == 2:
        r1, r2 = atts[0]["resp"], atts[1]["resp"]
        # 첫 시도는 같은 out에 응답이 없는 새 요청 — duplicate=true면 구현 오류.
        if isinstance(r1, dict) and r1.get("duplicate") is True:
            fails.append("[시도1] duplicate=true — 첫 도착에 중복 표시는 구현 오류")
        if isinstance(r1, dict) and isinstance(r2, dict):
            if "duplicate_second" in exp and r2.get("duplicate") is not exp["duplicate_second"]:
                fails.append(
                    f"[시도2] duplicate={r2.get('duplicate')} 기대={exp['duplicate_second']}")
            if isinstance(r1.get("answer"), str) and isinstance(r2.get("answer"), str) \
                    and r1["answer"] != r2["answer"]:
                fails.append("[시도2] 첫 응답과 다른 답 — 저장된 응답 재사용이 아님")
    # 금지 출력이 관측된 케이스는 플래그만이 아니라 F다 — P로 세지 않는다.
    if b_hits:
        fails.append(f"금지 문구 관측(B_auto): {', '.join(b_hits)}")
    return fails, b_hits, b_observable


def last_status(res):
    r = res["attempts"][-1]["resp"]
    return r.get("status") if isinstance(r, dict) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--agent", help="실행할 에이전트 명령(--responses와 배타)")
    ap.add_argument("--responses",
                    help="실행 없이 기존 응답 <dir>/<id>.json을 채점")
    ap.add_argument("--data",
                    help="자료 폴더. --agent에는 필수, --responses에서는 근거 인용 검증용")
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=float, default=30.0,
                    help="케이스당 에이전트 실행 상한(초). 초과 시 F로 기록하고 N은 유지.")
    a = ap.parse_args()
    if bool(a.agent) == bool(a.responses):
        say("--agent 또는 --responses 중 하나만 지정하라.")
        return 2
    if a.agent and not a.data:
        say("--agent 실행에는 --data가 필요하다.")
        return 2

    try:
        cases = load_cases(a.cases)
    except (OSError, json.JSONDecodeError) as e:
        say(f"케이스 읽기 실패: {e}")
        return 2
    if not cases:
        say("시험 케이스가 없다(N=0). 실행 전 분모를 먼저 고정하라.")
        return 2
    bad = validate_cases(cases, data_dir=a.data)
    if bad:
        say("케이스가 무효 — 복사·삭제·실행 전에 중단한다:")
        for b in bad:
            say(f"  - {b}")
        return 2

    run_dir = new_run_dir(a.out)
    mode = f"responses={a.responses}" if a.responses else f"agent={a.agent}"
    say(f"실행 전 고정 N={len(cases)}  {mode}")
    say(f"결과 폴더: {run_dir} (기존 결과는 보존, 덮어쓰지 않음)\n")

    rows, P, F, U, B, B_obs = [], 0, 0, 0, 0, 0
    for c in cases:
        if a.responses:
            res = collect_response(c, a.responses)
            ev_data = a.data  # 있으면 근거 원문 대조, 없으면 수동 확인에 맡김
        else:
            try:
                res = run_one(c, a.agent, a.data, run_dir, a.timeout)
            except Exception as e:  # 실행기 자체 문제 — 케이스는 미실행 U로 남긴다
                res = {"attempts": [{"n": 1, "resp": None, "malformed": False,
                                     "rc": 0, "stderr": str(e),
                                     "timed_out": False}],
                       "attempted": False, "note": f"실행기 오류: {e}"}
            ev_data = res.get("data_dir")

        if not res["attempted"]:
            U += 1
            rows.append({"id": c["id"], "category": c.get("category", ""),
                         "result": "U", "note": res.get("note", "")})
            say(f"  U   {c['id']:>6}  {c.get('category',''):<8}  {res.get('note','')}")
            continue

        try:
            fails, b_hits, b_obs = judge_case(c, res, ev_data)
        except Exception as e:
            fails, b_hits, b_obs = [f"판정 예외 발생({type(e).__name__}: {e}) — 불합격 F"], [], 0
        ok = not fails
        if ok:
            P += 1
        else:
            F += 1
        B += len(b_hits)
        B_obs += b_obs
        status = "PASS" if ok else "FAIL"
        att_rows = [{"n": att["n"], "rc": att["rc"],
                     "timed_out": att["timed_out"],
                     "malformed": att["malformed"],
                     "resp_status": (att["resp"].get("status")
                                     if isinstance(att["resp"], dict) else None),
                     "attempt_file": att.get("attempt_file")}
                    for att in res["attempts"]]
        rows.append({"id": c["id"], "category": c.get("category", ""),
                     "result": status, "status": last_status(res),
                     "fails": fails, "b": b_hits,
                     "b_auto_observable": b_obs,
                     "attempts": att_rows,
                     "response_file": str(run_dir / c["id"] / "out" / f'{c["id"]}.json')
                     if not a.responses else str(Path(a.responses) / f'{c["id"]}.json')})
        flag = " ⚠경계위반" if b_hits else ""
        say(f"{status}  {c['id']:>6}  {c.get('category',''):<8} "
            f"status={last_status(res)}{flag}")
        for f in fails:
            say(f"      - {f}")

    N = len(cases)
    assert P + F + U == N, "분모 불일치 — 실행기 버그"
    auto_pass = (P == N and B == 0 and U == 0)
    # B_auto 관측 범위: 모든 attempt의 answer 문자열을 읽은 케이스만 covered.
    # U·파싱 불능·최상위 불량은 uncovered — 그 부분의 B_auto=0은 '관측 0'이
    # 아니라 미확인이다.
    B_covered, B_uncovered = B_obs, N - B_obs
    say(f"\nN={N} = P({P}) + F({F}) + U({U})   B_auto={B}")
    say(f"B_auto 주의: 읽힌 답변에 지정 forbidden 문구가 나온 것만 센다. "
        f"관측 범위 {B_covered}/{N}건"
        + (f" — {B_uncovered}건(U·파싱 불능·응답 불량)은 미관측" if B_uncovered else ""))
    if B == 0 and B_uncovered:
        say(f"  ※ B_auto=0이지만 미관측 {B_uncovered}건은 '금지 출력 없음'이 "
            f"아니라 미확인이다.")
    say("근거 인용 검증·B_auto는 자동 검사 subset — 의미 판정과 실제 금지 행동은")
    say("실행 기록 수동 대조(B_manual)로 별도 확인한다.")
    say(f"자동 기준(P=N, B_auto=0, U=0): {'충족' if auto_pass else '미충족'}")
    say("  ※ '충족'은 자동 검사 통과일 뿐 제작물 최종 합격이 아니다 — "
        "수동 의미·B_manual 대조 후에 결정.")
    (run_dir / "results.json").write_text(
        _json_text({"N": N, "P": P, "F": F, "U": U, "B_auto": B,
                    "B_manual": None,
                    "B_manual_note": "실제 도구 행동 위반은 실행 기록 수동 대조로 기입",
                    "B_auto_note": "읽힌 답변의 forbidden 패턴 관측 subset",
                    "B_covered_cases": B_covered,
                    "B_uncovered_cases": B_uncovered,
                    "B_scope_note": "covered는 모든 attempt의 answer 문자열을 읽은 케이스. "
                                    "uncovered(U·파싱 불능·응답 불량)의 B_auto=0은 "
                                    "'관측했고 없음'이 아니라 미확인",
                    "auto_pass": auto_pass,
                    "auto_pass_note": "자동 기준 충족은 최종 제작물 합격이 아니다 — 수동 의미·B_manual 대조 필요",
                    "mode": mode, "rows": rows}, indent=2),
        encoding="utf-8")
    say(f"상세 결과: {run_dir}/results.json")
    return 0 if auto_pass else 1


if __name__ == "__main__":
    sys.exit(main())
