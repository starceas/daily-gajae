#!/usr/bin/env python3
"""push 관문: 원격으로 새로 나가는 모든 커밋의 (경로, blob)을 검사한다.

대상 집합 Q = reachable(HEAD) - reachable(origin/main). Q의 각 커밋(merge 포함,
부모별로 분해)이 새로 공개하는 파일 버전을 빠짐없이 모은다.
- 경로는 허용 집합(course/**, index.html, posts/YYYY-MM-DD.md|html) 안이어야 한다.
  허용 밖 경로의 추가·변경·삭제는 거부한다.
- 새로 공개되는 각 blob의 커밋된 바이트를 scan.py로 검사한다(작업 파일이 아니다).
  허용 목록 tools/course-scan-allow.txt(저장소 상대경로:줄: 종류)를 같은 방식으로 적용한다.
- 로컬이 원격과 같으면 SYNC, 앞서 있고 검사를 통과하면 READY,
  원격이 앞서거나 갈라졌으면 거부한다.

출력(종료 상태): SYNC/READY(0), 위반 목록(1), 오류(2, 사유는 stderr).
출력에는 경로·줄·종류만 담고 파일 내용·차단어를 싣지 않는다.
"""
import os
import re
import subprocess
import sys
import tempfile

ALLOWED_PATH = re.compile(r"^(course/.+|index\.html|posts/\d{4}-\d{2}-\d{2}\.(md|html))$")
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def git(*args, text=False):
    r = subprocess.run(["git"] + list(args), capture_output=True, text=text)
    if r.returncode != 0:
        err = (r.stderr if text else r.stderr.decode("utf-8", "replace")).strip()
        raise RuntimeError(f"git {' '.join(args[:1])} failed: {err}")
    return r.stdout


def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)


def main():
    try:
        root = git("rev-parse", "--show-toplevel", text=True).strip()
        head = git("rev-parse", "HEAD", text=True).strip()
        base_r = subprocess.run(
            ["git", "rev-parse", "--verify", "-q", "refs/remotes/origin/main"],
            capture_output=True, text=True)
        base = base_r.stdout.strip() if base_r.returncode == 0 else ""
    except RuntimeError as e:
        fail(str(e))

    if base:
        if head == base:
            print("SYNC")
            return
        behind = subprocess.run(
            ["git", "merge-base", "--is-ancestor", head, base]).returncode == 0
        ahead = subprocess.run(
            ["git", "merge-base", "--is-ancestor", base, head]).returncode == 0
        if behind or not ahead:
            print("sync: 원격이 앞서 있거나 갈라져 있습니다")
            sys.exit(1)
        rev_range = f"{base}..{head}"
    else:
        rev_range = head

    # Q의 커밋 전부와 각 커밋이 새로 공개하는 (경로, blob)을 모은다.
    try:
        commits = git("rev-list", rev_range, text=True).split()
        changes = {}  # (path, dst_blob) -> None (순서 무관, 중복 제거)
        for c in commits:
            parents = git("rev-list", "--parents", "-n", "1", c, text=True).split()
            for p in parents[1:] or [EMPTY_TREE]:
                out = git("diff", "--raw", "-r", "--no-renames", "-z", p, c)
                recs = out.split(b"\x00")
                i = 0
                while i < len(recs):
                    meta, path = recs[i], recs[i + 1] if i + 1 < len(recs) else b""
                    if not meta.startswith(b":"):
                        break
                    # --no-renames 이므로 경로는 하나. dst blob은 마지막 sha.
                    fields = meta.split()
                    changes[(os.fsdecode(path), fields[-2].decode())] = None
                    i += 2
    except RuntimeError as e:
        fail(str(e))

    violations = []
    for path, _ in changes:
        if not ALLOWED_PATH.match(path):
            violations.append(f"{path}: 비허용 경로")

    # 새로 공개되는 blob 바이트를 임시 tree에 실제 상대경로로 풀어 scan한다.
    blob_paths = {}
    for path, sha in changes:
        if not sha.startswith("0000000"):
            blob_paths.setdefault(sha, []).append(path)
    if blob_paths:
        with tempfile.TemporaryDirectory() as tmp:
            args = []
            for sha, paths in blob_paths.items():
                if subprocess.run(
                        ["git", "cat-file", "-t", sha],
                        capture_output=True, text=True).stdout.strip() != "blob":
                    continue
                rel = paths[0]
                dest = os.path.join(tmp, "tree", rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                data = git("cat-file", "blob", sha)
                with open(dest, "wb") as f:
                    f.write(data)
                args.append(rel)
            if args:
                scan = subprocess.run(
                    [sys.executable, os.path.join(root, "tools", "scan.py")] + sorted(args),
                    cwd=os.path.join(tmp, "tree"), capture_output=True, text=True)
                if scan.returncode == 1:
                    try:
                        with open(os.path.join(root, "tools", "course-scan-allow.txt"),
                                  encoding="utf-8") as f:
                            allow = {l.strip() for l in f
                                     if l.strip() and not l.lstrip().startswith("#")}
                    except OSError:
                        allow = set()
                    sha_of_path = {p: s for s, ps in blob_paths.items() for p in ps}
                    for line in scan.stdout.splitlines():
                        front, _, kind = line.rpartition(": ")
                        hit_path, _, no = front.rpartition(":")
                        for p in blob_paths.get(sha_of_path.get(hit_path, ""), [hit_path]):
                            cand = f"{p}:{no}: {kind}"
                            if cand not in allow:
                                violations.append(cand)
                elif scan.returncode != 0:
                    fail(f"scan.py 오류(rc={scan.returncode}): {scan.stderr.strip()}")

    if violations:
        for v in sorted(set(violations)):
            print(v)
        sys.exit(1)
    print("READY")


if __name__ == "__main__":
    main()
