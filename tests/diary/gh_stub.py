#!/usr/bin/env python3
"""gh CLI 대역 — 발행기 PR 흐름을 로컬 bare 원격에서 검증하기 위한 시험용 스텁.

실제 GitHub을 부르지 않는다. 지원 범위는 publish.sh가 쓰는 호출뿐이다.
  gh pr list --head B --base main --state open --json number --jq ...
  gh pr create --base main --head B --title T --body B
  gh pr checks N [--json name --jq length]
  gh pr checks N --watch --interval S --fail-fast
  gh pr merge N --merge --delete-branch --match-head-commit SHA

환경:
  GH_STUB_REMOTE   bare 원격 경로(필수) — 머지는 이 원격의 main ref를 갱신한다
  GH_STUB_STATE    PR 번호 상태 파일(필수)
  GH_STUB_CHECKS   pass|fail|none  — 검사 결과(기본 pass). none이면 검사가 안 붙는다
  GH_STUB_LOG      호출 기록(선택)
"""
import json
import os
import subprocess
import sys

REMOTE = os.environ["GH_STUB_REMOTE"]
STATE = os.environ["GH_STUB_STATE"]
CHECKS = os.environ.get("GH_STUB_CHECKS", "pass")
LOG = os.environ.get("GH_STUB_LOG")


def log(argv):
    if not LOG:
        return
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(" ".join(argv) + "\n")


def load():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(state):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def git(*args, check=True):
    r = subprocess.run(["git", "--git-dir", REMOTE] + list(args),
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.stderr.write(r.stderr)
        sys.exit(1)
    return r


def arg(argv, name, default=None):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def main(argv):
    log(argv)
    if len(argv) < 2 or argv[0] != "pr":
        sys.stderr.write("gh stub: 지원하지 않는 호출\n")
        return 2
    sub = argv[1]
    state = load()

    if sub == "list":
        head = arg(argv, "--head")
        num = state.get(head)
        if num and arg(argv, "--json"):
            # publish.sh는 --jq '.[0].number // empty'로 숫자만 받는다.
            print(num)
        return 0

    if sub == "create":
        head = arg(argv, "--head")
        num = state.get(head)
        if not num:
            num = str(len(state) + 1)
            state[head] = num
            save(state)
        print("https://example.invalid/pr/%s" % num)
        return 0

    if sub == "checks":
        if CHECKS == "none":
            if arg(argv, "--json"):
                print("0" if arg(argv, "--jq") else "[]")
            return 0
        if arg(argv, "--json"):
            print("1" if arg(argv, "--jq") else
                  "[{\"name\":\"unittest\",\"state\":\"%s\"}]"
                  % ("FAILURE" if CHECKS == "fail" else "SUCCESS"))
            return 0
        if CHECKS == "fail":
            sys.stderr.write("unittest\tfail\n")
            return 1
        print("unittest\tpass")
        return 0

    if sub == "merge":
        num = argv[2] if len(argv) > 2 else ""
        head = next((b for b, n in state.items() if n == num), None)
        if head is None:
            sys.stderr.write("gh stub: 알 수 없는 PR %s\n" % num)
            return 1
        want = arg(argv, "--match-head-commit")
        sha = git("rev-parse", "refs/heads/" + head).stdout.strip()
        if want and want != sha:
            sys.stderr.write("gh stub: head 불일치 %s != %s\n" % (want, sha))
            return 1
        cur = git("rev-parse", "-q", "--verify", "refs/heads/main", check=False)
        base = cur.stdout.strip()
        if base and base != sha:
            # fast-forward만 허용(대역이므로 merge commit은 만들지 않는다).
            anc = subprocess.run(
                ["git", "--git-dir", REMOTE, "merge-base", "--is-ancestor", base, sha],
                capture_output=True)
            if anc.returncode != 0:
                sys.stderr.write("gh stub: fast-forward 아님\n")
                return 1
        git("update-ref", "refs/heads/main", sha)
        git("update-ref", "-d", "refs/heads/" + head, check=False)
        state.pop(head, None)
        save(state)
        return 0

    sys.stderr.write("gh stub: 지원하지 않는 하위명령 %s\n" % sub)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
