#!/usr/bin/env python3
"""시험 실행기 자체 점검 — labs/kit/tests/selfcheck.py

양성 검증:
  1. dev/verify 각각에 대해 N == 케이스 파일 수(새 케이스 추가하면 N이 따라가야 함)
  2. mock_agent로 P=N, U=0, B_auto=0, 종료코드 0
  3. 결과가 N=P+F+U로 분해되고 results.json에 F·U·B_manual 칸이 있다
  4. --responses 모드: 일부 응답만 있으면 U>0·exit=1 (미실행이 통과로 세어지지 않음)

음성 검증(책임자 nested-probe 반례 잠금):
  5. 무효 케이스(최상위 비객체·id 중복·id 경로이탈·expect 중첩 타입·missing_files
     절대경로/문자열/null/루트/NUL/디렉터리)는 복사·삭제·실행 전에 exit 2로 거절
  6. missing_files 절대경로가 자료 밖 파일을 unlink하지 않는다(격리 victim만 사용)
  7. 불량 응답(최상위 배열·detail 숫자·notes 숫자·source 비문자열/NUL경로·조작 근거)은
     traceback 없이 F로 기록되고 results.json이 쓰인다
  8. send_twice: 첫 시도 실패(오답·rc!=0)는 두 번째 성공이 가리지 못한다 — F 유지,
     두 시도의 요청/응답이 각각 보존된다
  9. mock_agent의 무효 요청(비JSON·비객체·id 이탈/누락·text 비문자열·now 불량)은
     정상 해석 없이 안전한 경로에 status=error 응답, traceback 없음

사용: python3 labs/kit/tests/selfcheck.py
"""
import json
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

KIT = Path(__file__).parent.parent
ROOT = KIT.parent.parent
RUN = ROOT / "labs" / "kit" / "tests" / "run.py"
AGENT = f"{sys.executable} {KIT}/agent/mock_agent.py"
DATA = KIT / "personas" / "materials"

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if not cond else ""))
    return cond


def run(args, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return command([sys.executable, str(RUN), *args], env=env)


def command(argv, env=None):
    try:
        return subprocess.run(argv, capture_output=True, text=True, env=env,
                              errors="backslashreplace", timeout=30)
    except subprocess.TimeoutExpired as exc:
        check("subprocess timeout", False, repr(argv))
        def decoded(value):
            return value.decode(errors="backslashreplace") if isinstance(value, bytes) else (value or "")
        return subprocess.CompletedProcess(argv, 124, decoded(exc.stdout),
                                           decoded(exc.stderr) + "\nselfcheck timeout")


def latest(outdir):
    dirs = sorted(Path(outdir).glob("run-*"))
    return dirs[-1] if dirs else None


def read_results(outdir):
    rdir = latest(outdir)
    try:
        if rdir is None:
            raise FileNotFoundError("run directory absent")
        obj = json.loads((rdir / "results.json").read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("results must be an object")
        return obj
    except (OSError, ValueError) as exc:
        check(f"results.json 누락/불량: {outdir}", False, str(exc))
        return {"N": -1, "P": 0, "F": 0, "U": 0, "B_auto": 0, "rows": [{}]}


def tree_state(root):
    """링크를 따라가지 않고 자기 fixture의 바이트/대상/mode를 대조한다."""
    state = {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(folder) / name
            mode = path.lstat().st_mode
            value = os.readlink(path) if stat.S_ISLNK(mode) else (
                hashlib.sha256(path.read_bytes()).hexdigest() if stat.S_ISREG(mode) else None)
            state[str(path.relative_to(root))] = (mode, value)
    return state


def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(obj if isinstance(obj, str)
                    else json.dumps(obj, ensure_ascii=True), encoding="utf-8")
    return path


def case_json(cid, **kw):
    c = {"id": cid, "category": "probe", "input": "질문",
         "expect": {"status": ["ok"], "must_contain": [], "forbidden": [],
                    "evidence": [], "notes_contain": []}}
    c.update(kw)
    return c


def resp_json(rid, **kw):
    r = {"request_id": rid, "status": "ok", "answer": "15:00",
         "evidence": [{"source": "hours.txt", "detail": "화~금 07:00-15:00"}],
         "duplicate": False, "notes": []}
    r.update(kw)
    return r


def neg_probe(name, args, want_exit, outdir=None, want=None,
              no_traceback=True, extra=None):
    """반례 재현: 종료코드·results 요약·traceback 부재를 함께 본다."""
    p = run(args)
    out = p.stdout + p.stderr
    ok = p.returncode == want_exit
    if no_traceback and "Traceback" in out:
        ok = False
    if want is not None:
        rj = read_results(outdir)
        for k, v in want.items():
            if rj.get(k) != v:
                ok = False
    if extra is not None:
        try:
            ok = bool(extra()) and ok
        except (OSError, ValueError, KeyError, IndexError) as exc:
            check(f"{name}: 추가 결과 누락/불량", False, str(exc))
            ok = False
    check(name, ok, f"exit={p.returncode} 기대={want_exit} tail={out[-160:]}")


def main():
    work = Path(tempfile.mkdtemp(prefix="tests-selfcheck-"))

    # ── 양성 ────────────────────────────────────────────────
    for suite in ("cases-dev", "cases-verify"):
        cdir = KIT / "tests" / suite
        n_files = len(list(cdir.glob("*.json")))
        p = run(["--cases", str(cdir), "--agent", AGENT,
                 "--data", str(DATA), "--out", str(work / suite)])
        rj = read_results(work / suite)
        check(f"{suite}: exit=0", p.returncode == 0, p.stdout[-200:])
        check(f"{suite}: N=파일수({n_files})", rj["N"] == n_files)
        check(f"{suite}: P=N, U=0, B_auto=0",
              rj["P"] == rj["N"] and rj["U"] == 0 and rj["B_auto"] == 0)
        check(f"{suite}: N=P+F+U 분해",
              rj["N"] == rj["P"] + rj["F"] + rj["U"] and
              "B_manual" in rj and "B_manual_note" in rj)

    resp_dir = work / "resp"
    write(resp_dir / "t01.json", resp_json("t01"))
    p = run(["--cases", str(KIT / "tests" / "cases-dev"),
             "--responses", str(resp_dir), "--data", str(DATA),
             "--out", str(work / "graded")])
    rj = read_results(work / "graded")
    check("responses 모드: exit=1(미실행 존재)", p.returncode == 1)
    check("responses 모드: U>0이고 P+F+U=N",
          rj["U"] > 0 and rj["N"] == rj["P"] + rj["F"] + rj["U"])

    # ── 음성: 무효 케이스 입력은 exit 2, 사본 밖 파일은 건드리지 않음 ──
    def cases_dir(name, files):
        d = work / name / "cases"
        for fn, obj in files.items():
            write(d / fn, obj)
        return d

    base_args = lambda d, out: ["--cases", str(d), "--agent", AGENT,
                                "--data", str(DATA), "--out", str(work / out)]

    neg_probe("입력: 케이스 최상위가 배열 → exit2",
              base_args(cases_dir("c-toparr", {"b.json": [1, 2]}), "o-toparr"), 2)
    neg_probe("입력: id 중복 → exit2",
              base_args(cases_dir("c-dup", {"a.json": case_json("x1"),
                                            "b.json": case_json("x1")}), "o-dup"), 2)
    neg_probe("입력: id 경로이탈(../x) → exit2",
              base_args(cases_dir("c-trav", {"a.json": case_json("../victim")}),
                        "o-trav"), 2)
    neg_probe("입력: expect.must_contain 숫자 → exit2",
              base_args(cases_dir("c-expnum", {"a.json": case_json(
                  "x1", expect={"status": ["ok"], "must_contain": 5})}),
                  "o-expnum"), 2)
    neg_probe("입력: expect.status 원소가 list(unhashable) → exit2",
              base_args(cases_dir("c-expst", {"a.json": case_json(
                  "x1", expect={"status": [["ok"]], "must_contain": [],
                                "forbidden": [], "evidence": [],
                                "notes_contain": []})}), "o-expst"), 2)
    neg_probe("입력: category 비문자열 → exit2",
              base_args(cases_dir("c-cat", {"a.json": case_json(
                  "x1", category=7)}), "o-cat"), 2)
    neg_probe("입력: now가 ISO8601 값 아님 → exit2",
              base_args(cases_dir("c-badnow", {"a.json": case_json(
                  "x1", now="어제 저녁쯤")}), "o-badnow"), 2)
    neg_probe("입력: missing_files가 문자열 → exit2",
              base_args(cases_dir("c-mfstr", {"a.json": case_json(
                  "x1", missing_files="hours.txt")}), "o-mfstr"), 2)
    neg_probe("입력: missing_files가 null → exit2",
              base_args(cases_dir("c-mfnull", {"a.json": case_json(
                  "x1", missing_files=None)}), "o-mfnull"), 2)
    neg_probe("입력: missing_files가 '.' (자료 루트) → exit2",
              base_args(cases_dir("c-mfdot", {"a.json": case_json(
                  "x1", missing_files=["."])}), "o-mfdot"), 2)
    neg_probe("입력: missing_files에 NUL 문자 → exit2",
              base_args(cases_dir("c-mfnul", {"a.json": case_json(
                  "x1", missing_files=["\u0000"])}), "o-mfnul"), 2)

    victim = write(work / "victim" / "keep.txt", "삭제되면 안 되는 파일")
    neg_probe("입력: missing_files 절대경로 → exit2 + 사본 밖 파일 보존",
              base_args(cases_dir("c-mfabs", {"a.json": case_json(
                  "x1", missing_files=[str(victim)])}), "o-mfabs"), 2,
              extra=lambda: victim.exists() and victim.read_text() == "삭제되면 안 되는 파일")

    # missing_files에 실제 디렉터리 경로 지정 시 exit2 반려 (격리 사본 안 폴더만 사용)
    test_data = work / "test-data"
    test_data.mkdir(parents=True, exist_ok=True)
    write(test_data / "sample.txt", "샘플")
    (test_data / "subfolder").mkdir(exist_ok=True)
    neg_probe("입력: missing_files가 실제 디렉터리 → exit2",
              ["--cases", str(cases_dir("c-mfdir", {"a.json": case_json(
                  "x1", missing_files=["subfolder"])})),
               "--agent", AGENT, "--data", str(test_data), "--out", str(work / "o-mfdir")], 2)
    neg_probe("입력: --responses 모드에서도 missing_files 디렉터리 → exit2",
              ["--cases", str(cases_dir("c-mfdir-resp", {"a.json": case_json(
                  "x1", missing_files=["subfolder"])})),
               "--responses", str(resp_dir), "--data", str(test_data), "--out", str(work / "o-mfdir-resp")], 2)

    # 대조군: 부재 파일명(missing_files=['nonexistent.txt'])은 기존 계약대로 허용(exit2 아님)
    p_absent = run(["--cases", str(cases_dir("c-mfabsent", {"a.json": case_json(
        "x1", input="몇 시까지 영업해요?", missing_files=["nonexistent.txt"],
        expect={"status": ["ok"], "must_contain": ["15:00"], "forbidden": [],
                "evidence": ["hours.txt"], "notes_contain": []})})),
        "--agent", AGENT, "--data", str(DATA), "--out", str(work / "o-mfabsent")])
    check("입력: missing_files 부재 파일명 허용(exit2 아님)", p_absent.returncode == 0)

    # ── 음성: missing_files 조회 실패는 진짜 부재와 구별해 사전 exit2 ──
    # ELOOP·EACCES·ENOTDIR·dangling·인코딩 불가는 조회 실패(반려)이고,
    # 진짜 부재·중간 부재·정상 내부 symlink만 허용된다. 반려 시 out/임시 자료
    # 사본·에이전트 실행 부수효과가 없어야 한다. fixture는 자기 tmp 안에서만
    # 만들고 권한은 finally에서 복원한다.
    def mf_case_dir(tag, mf):
        d = work / tag / "cases"
        write(d / "a.json", json.dumps(case_json(
            "x1", input="몇 시까지 영업해요?", missing_files=mf,
            expect={"status": ["ok"], "must_contain": ["15:00"],
                    "forbidden": [], "evidence": ["hours.txt"],
                    "notes_contain": []}), ensure_ascii=True))
        return d

    lookup_bad = (
        ("순환 symlink", ["loop-a"], "링크 해석 실패", "loop"),
        ("권한 없는 부모", ["locked/file.txt"], "Permission", "locked"),
        ("dangling symlink(최종)", ["dangle"], "dangling", "dangle"),
        ("dangling symlink(중간)", ["dangle/x.txt"], "dangling", "dangle"),
        ("중간 성분이 일반 파일(ENOTDIR)", ["menu.txt/sub"], "조회 실패", None),
        ("루트를 가리키는 링크", ["toroot"], "루트", "rootlink"),
        ("자료 밖 링크", ["outside"], "밖", "outside"),
        ("인코딩 불가 이름", ["\ud800"], "인코딩 불가", None),
        ("부재 prefix 뒤 인코딩 불가", ["nodir/\udfff"], "인코딩 불가", None),
        ("자료 root가 일반 파일", [], "디렉터리", "rootfile"),
        ("자료 root가 부재", [], "조회 실패", "rootabsent"))
    for i, (name, mf, needle, setup) in enumerate(lookup_bad):
        # 매 반례의 clean 사본에 해당 결함 하나만 만든다.
        l2data = work / f"mf-lookup-{i}" / "data"
        shutil.copytree(DATA, l2data)
        marker = l2data.parent / "agent-calls.txt"
        marked_agent = write(l2data.parent / "marked-agent.py", textwrap.dedent(f"""
            import subprocess, sys
            from pathlib import Path
            with Path({str(marker)!r}).open("a") as log:
                log.write("called\\n")
            sys.exit(subprocess.run([sys.executable, {str(KIT / 'agent/mock_agent.py')!r},
                                    *sys.argv[1:]], timeout=5).returncode)
        """))
        locked, old_mode = None, None
        if setup == "loop":
            (l2data / "loop-a").symlink_to("loop-b")
            (l2data / "loop-b").symlink_to("loop-a")
        elif setup == "dangle":
            (l2data / "dangle").symlink_to("no-such-target.txt")
        elif setup == "rootlink":
            (l2data / "toroot").symlink_to(".")
        elif setup == "outside":
            (l2data / "outside").symlink_to(str(work))
        elif setup == "locked":
            locked = l2data / "locked"
            locked.mkdir(mode=0o750)
            write(locked / "file.txt", "own fixture")
            old_mode = stat.S_IMODE(locked.stat().st_mode)
        original = tree_state(l2data)
        try:
            if locked is not None:
                locked.chmod(0)
            data_arg = l2data
            if setup == "rootfile":
                data_arg = l2data / "menu.txt"
            elif setup == "rootabsent":
                data_arg = l2data / "absent-root"
            outd = work / f"o-mflook-{i}"
            cdir = mf_case_dir(f"c-mflook-{i}", mf)
            # 정상 case가 먼저 있어도 전량 사전검증으로 호출 0이어야 한다.
            write(cdir / "0.json", case_json("first", input="몇 시까지 영업해요?"))
            before = tree_state(l2data)
            tmp0 = set(Path(tempfile.gettempdir()).glob("data-*"))
            p = run(["--cases", str(cdir), "--agent", f'"{sys.executable}" "{marked_agent}"',
                     "--data", str(data_arg), "--out", str(outd)])
            check(f"missing_files 조회 실패({name}) → 사전 exit2·부수효과0",
                  p.returncode == 2 and needle in p.stdout + p.stderr
                  and "Traceback" not in p.stdout + p.stderr
                  and not outd.exists() and not marker.exists()
                  and set(Path(tempfile.gettempdir()).glob("data-*")) == tmp0
                  and tree_state(l2data) == before,
                  f"exit={p.returncode} tail={(p.stdout + p.stderr)[-160:]}")
        finally:
            if locked is not None:
                locked.chmod(old_mode)
        check(f"missing_files {name}: 자료·원mode 복구", tree_state(l2data) == original)

    for i, (name, mf) in enumerate((
            ("생략", None), ("빈 목록", []), ("진짜 부재", ["absent.txt"]),
            ("중간 경로부터 진짜 부재", ["nodir/file.txt"]),
            ("정상 내부 symlink", ["inside-link"]),
            ("정상 일반 파일", ["menu.txt"]),
            ("내부 루트 링크 아래 파일", ["root-link/menu.txt"]),
            ("정상 내부 디렉터리 링크 아래 파일", ["dir-link/file.txt"]))):
        l2ok = work / f"mf-lookup-ok-{i}" / "data"
        shutil.copytree(DATA, l2ok)
        if mf == ["inside-link"]:
            (l2ok / "inside-link").symlink_to("menu.txt")
        elif mf == ["dir-link/file.txt"]:
            write(l2ok / "sub" / "file.txt", "own fixture")
            (l2ok / "dir-link").symlink_to("sub", target_is_directory=True)
        elif mf == ["root-link/menu.txt"]:
            (l2ok / "root-link").symlink_to(".", target_is_directory=True)
        cdir = mf_case_dir(f"c-mfok-{i}", mf if mf is not None else [])
        if mf is None:
            c = json.loads((cdir / "a.json").read_text())
            del c["missing_files"]
            write(cdir / "a.json", c)
        outd = work / f"o-mfok-{i}"
        mode_args = ["--agent", AGENT]
        if mf == ["root-link/menu.txt"]:
            # 루트 링크를 포함한 트리 전체 copytree는 순환한다. 이 대조는
            # --responses의 조회 경계만 검사하고 자료 복사 성공을 주장하지 않는다.
            rd = work / "mf-root-link-responses"
            write(rd / "x1.json", resp_json("x1"))
            mode_args = ["--responses", str(rd)]
        p = run(["--cases", str(cdir), *mode_args,
                 "--data", str(l2ok), "--out", str(outd)])
        rj = read_results(outd)
        check(f"missing_files {name} → 허용(exit0·N1P1)",
              p.returncode == 0 and rj.get("N") == 1 and rj.get("P") == 1,
              f"exit={p.returncode} tail={(p.stdout + p.stderr)[-160:]}")

    # ── 음성: 불량 응답은 traceback 없이 F·exit1, results.json 기록 ──
    def resp_probe(name, resp_obj):
        d = work / name / "cases"
        write(d / "t01.json", case_json("t01"))
        rd = work / name / "responses"
        write(rd / "t01.json", resp_obj)
        neg_probe(f"응답: {name} → exit1 F=1",
                  ["--cases", str(d), "--responses", str(rd),
                   "--data", str(DATA), "--out", str(work / f"o-{name}")],
                  1, work / f"o-{name}", want={"N": 1, "P": 0, "F": 1, "U": 0})

    resp_probe("최상위 배열", [1, 2])
    resp_probe("최상위 숫자", 42)
    resp_probe("notes 숫자 원소", resp_json("t01", notes=[123]))
    resp_probe("evidence source 비문자열",
               resp_json("t01", evidence=[{"source": ["x"], "detail": "y"}]))
    resp_probe("evidence detail 숫자",
               resp_json("t01", evidence=[{"source": "hours.txt", "detail": 5}]))
    resp_probe("조작 근거(detail이 원문에 없음)",
               resp_json("t01", evidence=[{"source": "hours.txt",
                                           "detail": "없는 내용을 지어냄"}]))
    resp_probe("없는 근거 파일",
               resp_json("t01", evidence=[{"source": "ghost.txt", "detail": "x"}]))
    resp_probe("빈 답", resp_json("t01", answer=""))
    resp_probe("evidence source에 NUL 문자",
               resp_json("t01", evidence=[{"source": "\u0000", "detail": "x"}]))
    resp_probe("evidence source 자료 밖 상대경로",
               resp_json("t01", evidence=[{"source": "../outside.txt", "detail": "x"}]))

    # 스키마 불량이어도 읽힌 answer의 금지 문구는 B_auto로 센다.
    d = work / "bhit" / "cases"
    write(d / "t01.json", case_json("t01", expect={
        "status": ["ok"], "must_contain": [], "forbidden": ["금지어"],
        "evidence": [], "notes_contain": []}))
    rd = work / "bhit" / "responses"
    write(rd / "t01.json", {"request_id": "t01", "answer": "금지어 포함"})  # 필드 누락
    neg_probe("B_auto: 스키마 불량 응답의 금지 문구도 관측",
              ["--cases", str(d), "--responses", str(rd),
               "--data", str(DATA), "--out", str(work / "o-bhit")],
              1, work / "o-bhit", want={"N": 1, "F": 1, "B_auto": 1})

    # 스키마는 정상인데 answer에 금지 문구 — B_auto 관측과 함께 F다(P로 안 셈).
    rd2 = work / "bhit2" / "responses"
    write(rd2 / "t01.json", resp_json("t01", answer="여기 금지어 포함"))
    neg_probe("B_auto: 금지 문구 응답은 PASS가 아니라 F",
              ["--cases", str(d), "--responses", str(rd2),
               "--data", str(DATA), "--out", str(work / "o-bhit2")],
              1, work / "o-bhit2",
              want={"N": 1, "P": 0, "F": 1, "B_auto": 1,
                    "B_covered_cases": 1, "B_uncovered_cases": 0},
              extra=lambda: read_results(work / "o-bhit2")["rows"][0]["b_auto_observable"] is True)

    # 응답 파싱 불능은 B_auto 미관측이다 — B_auto=0을 "관측했고 없음"과 구별.
    d2 = work / "unobs" / "cases"
    write(d2 / "t01.json", case_json("t01"))
    rd3 = work / "unobs" / "responses"
    write(rd3 / "t01.json", "{broken")
    neg_probe("B_auto: 파싱 불능 응답은 uncovered로 표시",
              ["--cases", str(d2), "--responses", str(rd3),
               "--data", str(DATA), "--out", str(work / "o-unobs")],
              1, work / "o-unobs",
              want={"N": 1, "F": 1, "B_auto": 0,
                    "B_covered_cases": 0, "B_uncovered_cases": 1},
              extra=lambda: read_results(work / "o-unobs")["rows"][0]["b_auto_observable"] is False)

    # ── LABS-01: 미짝 surrogate가 stdout·results.json 기록을 깨지 않음 ──
    # fixture 파일에는 ASCII JSON escape로 기록해 fixture 작성 자체는 안전하고,
    # 파서가 surrogate 문자열로 복원한다.
    scases = work / "surr" / "cases"
    sresp = work / "surr" / "responses"
    for cid in ("mix1", "mix2", "mix3"):
        write(scases / f"{cid}.json", json.dumps(case_json(
            cid, input="몇 시까지 영업해요?", expect={
                "status": ["ok"], "must_contain": ["15:00"], "forbidden": [],
                "evidence": ["hours.txt"], "notes_contain": []}),
            ensure_ascii=True))
        ev = [{"source": "hours.txt", "detail": "화~금 07:00-15:00"}]
        if cid == "mix2":
            ev.append({"source": "\ud800", "detail": "x"})
        write(sresp / f"{cid}.json",
              json.dumps(resp_json(cid, evidence=ev), ensure_ascii=True))
    outd = work / "o-surr"
    p = run(["--cases", str(scases), "--responses", str(sresp),
             "--data", str(DATA), "--out", str(outd)])
    rdir = list(outd.glob("run-*/results.json"))
    rj = read_results(outd)
    check("surrogate 응답: exit1·N3P2F1U0·PASS/FAIL/PASS·results 기록",
          p.returncode == 1 and "Traceback" not in p.stdout + p.stderr
          and rj.get("N") == 3 and rj.get("P") == 2 and rj.get("F") == 1
          and rj.get("U") == 0
          and [r.get("result") for r in rj.get("rows", [])]
          == ["PASS", "FAIL", "PASS"],
          f"exit={p.returncode} tail={(p.stdout + p.stderr)[-160:]}")
    # 같은 입력을 ASCII stdout에서 실행 — 집계·results는 동일해야 한다.
    outd = work / "o-surr-ascii"
    p = run(["--cases", str(scases), "--responses", str(sresp),
             "--data", str(DATA), "--out", str(outd)],
            env_extra={"PYTHONIOENCODING": "ascii"})
    rdir = list(outd.glob("run-*/results.json"))
    rj = read_results(outd)
    check("surrogate 응답: ASCII stdout에서도 완주·UTF-8 results 보존",
          p.returncode == 1 and "Traceback" not in p.stderr
          and rj.get("N") == 3 and rj.get("P") == 2 and rj.get("F") == 1
          and "근거" in (rdir[0].read_text() if rdir else ""),
          f"exit={p.returncode} tail={(p.stdout + p.stderr)[-160:]}")
    # 표시값(카테고리)만 surrogate이고 응답은 정상 → 판정을 바꾸지 않는다.
    scases2 = work / "surr-cat" / "cases"
    sresp2 = work / "surr-cat" / "responses"
    for cid in ("cat1", "cat2"):
        write(scases2 / f"{cid}.json", json.dumps(case_json(
            cid, category="분류\ud800", input="몇 시까지 영업해요?", expect={
                "status": ["ok"], "must_contain": ["15:00"], "forbidden": [],
                "evidence": ["hours.txt"], "notes_contain": []}),
            ensure_ascii=True))
        write(sresp2 / f"{cid}.json", resp_json(cid))
    outd = work / "o-surrcat"
    p = run(["--cases", str(scases2), "--responses", str(sresp2),
             "--data", str(DATA), "--out", str(outd)])
    rdir = list(outd.glob("run-*/results.json"))
    rj = read_results(outd)
    check("category만 surrogate: exit0·N2P2 (표시와 판정 분리)",
          p.returncode == 0 and "Traceback" not in p.stdout + p.stderr
          and rj.get("N") == 2 and rj.get("P") == 2 and rj.get("F") == 0,
          f"exit={p.returncode} tail={(p.stdout + p.stderr)[-160:]}")
    # DFFF/status 진단·literal escape·정상 한국어는 값을 바꾸지 않고 기록한다.
    for tag, change, want_exit, want_score in (
            ("dfff-source", {"evidence": [{"source": "\udfff", "detail": "x"}]},
             1, {"N": 1, "P": 0, "F": 1, "U": 0}),
            ("surrogate-status", {"status": "불량\ud800"},
             1, {"N": 1, "P": 0, "F": 1, "U": 0})):
        d = work / tag / "cases"
        rd = work / tag / "responses"
        write(d / "x1.json", case_json("x1", category="분류\udfff literal\\ud800"))
        rf = write(rd / "x1.json", resp_json("x1", **change))
        raw = rf.read_bytes()
        outd = work / f"o-{tag}"
        neg_probe(f"Unicode {tag}: 진단·집계 보존", ["--cases", str(d),
                  "--responses", str(rd), "--data", str(DATA), "--out", str(outd)],
                  want_exit, outd, want=want_score)
        rj = read_results(outd)
        check(f"Unicode {tag}: 원문·category 값 불변",
              rf.read_bytes() == raw and rj["rows"][0].get("category")
              == "분류\udfff literal\\ud800")
    for tag, change in (("expect", {"expect": {"status": ["\ud800"]}}),
                        ("now", {"now": "\udfff"}),
                        ("missing", {"missing_files": ["\ud800"]})):
        outd = work / f"o-unicode-invalid-{tag}"
        d = cases_dir(f"unicode-invalid-{tag}", {"x.json": case_json("x1", **change)})
        neg_probe(f"Unicode 무효 {tag}: 사전 exit2", base_args(d, f"o-unicode-invalid-{tag}"),
                  2, extra=lambda: not outd.exists())
    # 불량 응답의 answer에 forbidden이 있으면 surrogate와 무관하게 B_auto=1·F.
    d = work / "surrb" / "cases"
    write(d / "mix2.json", json.dumps(case_json(
        "mix2", input="몇 시까지 영업해요?", expect={
            "status": ["ok"], "must_contain": ["15:00"], "forbidden": ["금지어"],
            "evidence": ["hours.txt"], "notes_contain": []}), ensure_ascii=True))
    rd = work / "surrb" / "responses"
    write(rd / "mix2.json", json.dumps(resp_json(
        "mix2", answer="여기 금지어 포함 15:00",
        evidence=[{"source": "hours.txt", "detail": "화~금 07:00-15:00"},
                  {"source": "\ud800", "detail": "x"}]), ensure_ascii=True))
    neg_probe("B_auto: surrogate 응답의 금지 문구도 관측(F·B_auto=1)",
              ["--cases", str(d), "--responses", str(rd),
               "--data", str(DATA), "--out", str(work / "o-surrb")],
              1, work / "o-surrb",
              want={"N": 1, "P": 0, "F": 1, "U": 0, "B_auto": 1,
                    "B_covered_cases": 1})
    # 실제 surrogate와 literal backslash escape를 비교값에서 구별한다.
    d = work / "b-value" / "cases"
    rd = work / "b-value" / "responses"
    write(d / "x1.json", case_json("x1", expect={
        "forbidden": ["금지\udfff", "literal\\udfff"]}))
    rf = write(rd / "x1.json", resp_json("x1", status="불량\ud800",
               answer="금지\udfff literal\\udfff 한국어"))
    raw = rf.read_bytes()
    neg_probe("B_auto: surrogate/literal 원값 독립 집계", ["--cases", str(d),
              "--responses", str(rd), "--data", str(DATA), "--out", str(work / "o-b-value")],
              1, work / "o-b-value", want={"N": 1, "F": 1, "B_auto": 2},
              extra=lambda: rf.read_bytes() == raw)
    # send_twice 입력에 surrogate: 두 요청 원문이 request-1/2에 보존되고 exit0.
    fixed_agent = write(work / "agents" / "fixed_ok.py", textwrap.dedent("""
        import json, sys
        from pathlib import Path
        a = sys.argv
        out = Path(a[a.index("--out") + 1]); out.mkdir(parents=True, exist_ok=True)
        rid = json.loads(Path(a[a.index("--request") + 1]).read_text())["request_id"]
        p = out / f"{rid}.json"
        dup = p.exists()
        p.write_text(json.dumps({"request_id": rid, "status": "ok",
            "answer": "고정 답", "evidence": [], "duplicate": dup, "notes": []}))
    """))
    d = work / "surr-twice" / "cases"
    write(d / "st1.json", json.dumps(case_json(
        "st1", send_twice=True, input="본문\ud800첫째", input2="둘째\udfff",
        expect={"status": ["ok"], "must_contain": ["고정 답"], "forbidden": [],
                "evidence": [], "notes_contain": [], "duplicate_second": True}),
        ensure_ascii=True))
    outd = work / "o-surrtw"
    p = run(["--cases", str(d), "--agent", f"{sys.executable} {fixed_agent}",
             "--data", str(DATA), "--out", str(outd)])
    rdir = list(outd.glob("run-*"))
    reqs_ok = bool(rdir)
    for i, want in ((1, "본문\ud800첫째"), (2, "둘째\udfff")):
        try:
            if not rdir:
                raise FileNotFoundError("run directory absent")
            req = json.loads((rdir[-1] / "st1" / f"request-{i}.json").read_text())
            reqs_ok = isinstance(req, dict) and req.get("text") == want and reqs_ok
        except (OSError, ValueError) as exc:
            check(f"send_twice request-{i}.json 누락/불량", False, str(exc))
            reqs_ok = False
    check("send_twice surrogate 입력: 두 요청 원문 보존·exit0",
          p.returncode == 0 and reqs_ok,
          f"exit={p.returncode} tail={(p.stdout + p.stderr)[-160:]}")
    cdir = rdir[-1] / "st1" if rdir else None
    check("send_twice Unicode: results·두 attempt·응답 원문 보존",
          read_results(outd).get("P") == 1 and cdir is not None and all(
              (cdir / f"{stem}-{i}.{ext}").is_file()
              for i in (1, 2) for stem, ext in
              (("request", "json"), ("attempt", "json"), ("response", "json"),
               ("stdout", "txt"), ("stderr", "txt"))))

    # ── 음성: send_twice 첫 시도 실패는 두 번째가 못 가린다 ──
    bad_agent = write(work / "bad-agents" / "first_fail.py", textwrap.dedent("""
        import json, sys
        from pathlib import Path
        a = sys.argv
        out = Path(a[a.index("--out") + 1]); out.mkdir(parents=True, exist_ok=True)
        req = json.loads(Path(a[a.index("--request") + 1]).read_text())
        p = out / f"{req['request_id']}.json"
        if p.exists():  # 두 번째 시도: 겉보기엔 정답
            p.write_text(json.dumps({"request_id": req["request_id"], "status": "ok",
                "answer": "화~금 07:00-15:00", "evidence": [{"source": "hours.txt",
                "detail": "화~금 07:00-15:00"}], "duplicate": True, "notes": []}))
        else:  # 첫 시도: 틀린 답
            p.write_text(json.dumps({"request_id": req["request_id"], "status": "ok",
                "answer": "아무거나", "evidence": [], "duplicate": False, "notes": []}))
    """))
    rc7_agent = write(work / "bad-agents" / "first_rc7.py", textwrap.dedent("""
        import json, sys
        from pathlib import Path
        a = sys.argv
        out = Path(a[a.index("--out") + 1]); out.mkdir(parents=True, exist_ok=True)
        req = json.loads(Path(a[a.index("--request") + 1]).read_text())
        p = out / f"{req['request_id']}.json"
        if not p.exists():  # 첫 시도: 비정상 종료
            sys.exit(7)
        p.write_text(json.dumps({"request_id": req["request_id"], "status": "ok",
            "answer": "화~금 07:00-15:00", "evidence": [{"source": "hours.txt",
            "detail": "화~금 07:00-15:00"}], "duplicate": True, "notes": []}))
    """))
    dup_first = write(work / "bad-agents" / "dup_first.py", textwrap.dedent("""
        import json, sys
        from pathlib import Path
        a = sys.argv
        out = Path(a[a.index("--out") + 1]); out.mkdir(parents=True, exist_ok=True)
        req = json.loads(Path(a[a.index("--request") + 1]).read_text())
        (out / f"{req['request_id']}.json").write_text(json.dumps(
            {"request_id": req["request_id"], "status": "ok",
             "answer": "화~금 07:00-15:00", "evidence": [{"source": "hours.txt",
             "detail": "화~금 07:00-15:00"}], "duplicate": True, "notes": []}))
    """))
    st_case = case_json("st1", send_twice=True, expect={
        "status": ["ok"], "must_contain": ["15:00"], "forbidden": [],
        "evidence": [], "notes_contain": [], "duplicate_second": True})

    for name, agentfile, needle in (
            ("st-오답", bad_agent, "시도1"),
            ("st-rc7", rc7_agent, "rc=7"),
            ("st-첫duplicate", dup_first, "첫 도착에 중복 표시")):
        d = work / name / "cases"
        write(d / "st1.json", st_case)
        outdir = work / f"o-{name}"
        p = run(["--cases", str(d), "--agent", f"{sys.executable} {agentfile}",
                 "--data", str(DATA), "--out", str(outdir)])
        rdir = latest(outdir) if list(outdir.glob("run-*")) else None
        rj = read_results(outdir)
        row = (rj.get("rows") or [{}])[0]
        check(f"send_twice {name}: 첫 실패는 F로 남음(exit1)",
              p.returncode == 1 and rj.get("F") == 1 and rj.get("N") == 1,
              p.stdout[-200:])
        check(f"send_twice {name}: 두 시도가 보존되고 첫 실패가 기록됨",
              len(row.get("attempts", [])) == 2 and
              any(needle in str(f) for f in row.get("fails", [])))
        # 시도별 원문 로그 파일 보존: request/stdout/stderr/attempt 메타
        cdir = rdir / "st1" if rdir else None
        logs_ok = cdir is not None and all(
            (cdir / f"{stem}-{n}.{ext}").exists()
            for n in (1, 2) for stem, ext in
            (("request", "json"), ("stdout", "txt"),
             ("stderr", "txt"), ("attempt", "json")))
        if logs_ok and name != "st-첫duplicate":
            # rc7의 첫 시도는 응답 파일이 없다 — attempt 메타에 null 경로
            meta1 = json.loads((cdir / "attempt-1.json").read_text())
            logs_ok = meta1["request_file"].endswith("request-1.json") \
                and meta1["stdout_file"].endswith("stdout-1.txt")
        check(f"send_twice {name}: stdout/stderr/attempt 원문 파일 보존",
              logs_ok)

    # ── 양성: --agent는 shlex.split으로 파싱 — 공백 경로도 quoted로 실행 가능 ──
    spdir = work / "dir with space"
    spdir.mkdir()
    shutil.copy(KIT / "agent" / "mock_agent.py", spdir / "mock_agent.py")
    d = work / "quoted" / "cases"
    write(d / "t01.json", case_json(
        "t01", input="몇 시까지 영업해요?",
        expect={"status": ["ok"], "must_contain": ["15:00"], "forbidden": [],
                "evidence": ["hours.txt"], "notes_contain": []}))
    p = run(["--cases", str(d), "--agent",
             f'"{sys.executable}" "{spdir / "mock_agent.py"}"',
             "--data", str(DATA), "--out", str(work / "o-quoted")])
    check("quoted --agent(공백 경로) → exit0", p.returncode == 0,
          (p.stdout + p.stderr)[-200:])

    # ── 음성: mock_agent의 무효 요청은 정상 해석 없이 error 응답 ──
    def mock_probe(name, req_obj):
        reqf = write(work / f"req-{name}.json", req_obj)
        outd = work / f"out-{name}"
        p = command([sys.executable, str(KIT / "agent" / "mock_agent.py"),
                            "--request", str(reqf), "--data", str(DATA),
                            "--out", str(outd)])
        files = list(outd.glob("*.json")) if outd.exists() else []
        ok = (p.returncode == 0 and "Traceback" not in p.stdout + p.stderr
              and len(files) == 1)
        if ok:
            resp = json.loads(files[0].read_text())
            ok = resp.get("status") == "error" and resp.get("evidence") == []
        check(f"mock: {name} → 안전한 error 응답", ok,
              p.stderr[-160:] or str(files))

    mock_probe("비JSON", "{not json")
    mock_probe("최상위 비객체", [1, 2])
    mock_probe("id 경로이탈(../x)", {"request_id": "../x",
                                    "text": "몇 시까지 영업해요?"})
    mock_probe("request_id 누락", {"text": "몇 시까지 영업해요?"})
    mock_probe("text 비문자열", {"request_id": "t1", "text": 42})
    mock_probe("잘못된 now", {"request_id": "bn1",
                             "text": "오늘 몇 시까지 영업해요?",
                             "now": "어제 저녁쯤"})
    # 경로 이탈 id는 invalid-request.json으로만 써야 한다 — out 밖 생성 없음
    check("mock: 이탈 id가 out 밖에 파일을 만들지 않음",
          not (work / "x.json").exists() and not Path("/tmp/x.json").exists())

    print(f"\n{sum(RESULTS)}/{len(RESULTS)} 통과")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
