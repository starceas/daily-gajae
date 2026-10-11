#!/bin/bash
# tests/gate/run.sh [대상 루트] — tools/push_gate.py 회귀시험.
#
# 대상 루트(기본: 이 저장소)의 tools/와 .gitignore를 임시 저장소에 복사해 실행한다.
# 대상에 tools/push_gate.py가 있으면 관문을 직접 호출한다(gate 모드).
# 없으면(45445f2 대조) 대상의 tools/publish.sh를 실제 실행해 push 결과로 판정한다
# (e2e 모드 — 차단 기대 시나리오는 '원격 tip 불변', 통과 기대는 '원격에 파일 존재').
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SUBJECT="$(cd "${1:-$ROOT}" && pwd)"
GITIGNORE_SRC="${GITIGNORE_SRC:-$SUBJECT/.gitignore}"
PASS=0; FAILED=0
ok() { PASS=$((PASS + 1)); printf 'PASS %s\n' "$1"; }
no() { FAILED=$((FAILED + 1)); printf 'FAIL %s\n' "$1"; }
TERM="GAZZI-FAKE-NAME-777"

sandbox() {
  T=$(mktemp -d)
  WORK="$T/work"; REMOTE="$T/remote.git"
  NOTIFY="$T/notify.log"; : > "$NOTIFY"
  BL="$T/blocklist.txt"; printf '%s\n' "$TERM" > "$BL"
  STUB="$T/stub.py"
  cat > "$STUB" <<'PY'
import os, sys
with open(os.environ["NOTIFY_LOG"], "a") as f:
    f.write(" ".join(sys.argv[3:]) + "\n")
PY
  git init -q --bare "$REMOTE"
  git init -q "$WORK"
  git -C "$WORK" config user.name "test"
  at='@'; git -C "$WORK" config user.email "t${at}e.invalid"
  mkdir -p "$WORK/tools" "$WORK/posts" "$WORK/drafts"
  cp "$SUBJECT"/tools/*.py "$WORK/tools/" 2>/dev/null || true
  cp "$SUBJECT"/tools/publish*.sh "$WORK/tools/" 2>/dev/null || true
  cp "$SUBJECT"/tools/course-scan-allow.txt "$WORK/tools/" 2>/dev/null || true
  cp "$GITIGNORE_SRC" "$WORK/.gitignore"
  printf '# 시드 글\n\n본문입니다.\n' > "$WORK/posts/2026-10-01.md"
  (cd "$WORK" && python3 tools/build.py >/dev/null 2>&1)
  git -C "$WORK" add -A
  git -C "$WORK" commit -qm seed
  git -C "$WORK" remote add origin "$REMOTE"
  BR=$(git -C "$WORK" branch --show-current)
  git -C "$WORK" push -q -u origin "$BR"
  git --git-dir="$REMOTE" symbolic-ref HEAD "refs/heads/$BR"
  INIT=$(git -C "$WORK" rev-parse HEAD)
  TIP0=$INIT
  [ -f "$WORK/tools/push_gate.py" ] && GATE_MODE=1 || GATE_MODE=0
}

gate() { (cd "$WORK" && env DIARY_BLOCKLIST="$BL" python3 tools/push_gate.py >"$T/gate.out" 2>"$T/gate.err"); }
pub()  { (cd "$WORK" && env REPO="$WORK" POST="$STUB" CHANNEL=0 DIARY_BLOCKLIST="$BL" NOTIFY_LOG="$NOTIFY" bash tools/publish.sh >"$T/pub.log" 2>&1); }
remote_tip() { git --git-dir="$REMOTE" rev-parse "$BR"; }
remote_has() { git --git-dir="$REMOTE" ls-tree -r --name-only "$BR" | grep -qxF "$1"; }
mark_tip() { TIP0=$(remote_tip); }
draft() { printf '# %s\n\n본문입니다.\n' "$1" > "$WORK/drafts/$2.md"; }

# 차단 기대: 관문이 거부하거나(e2e) 발행이 실패하고 원격이 안 바뀐다.
expect_blocked() {
  if [ "$GATE_MODE" -eq 1 ]; then
    gate; [ $? -ne 0 ] && ok "$1" || no "$1"
  else
    draft "정상 글" 2026-10-09
    pub; local rc=$?
    if [ $rc -ne 0 ] && [ "$(remote_tip)" = "$TIP0" ]; then ok "$1"; else no "$1"; fi
  fi
}
# 통과 기대: 관문 READY 또는 e2e 발행 성공으로 원격에 $2가 생긴다.
expect_sent() {
  if [ "$GATE_MODE" -eq 1 ]; then
    gate; local rc=$?
    [ $rc -eq 0 ] && grep -qxF READY "$T/gate.out" && ok "$1" || no "$1"
  else
    draft "정상 글" 2026-10-09
    pub; local rc=$?
    [ $rc -eq 0 ] && remote_has "$2" && ok "$1" || no "$1"
  fi
}
commit_file() { # $1=path $2=content
  mkdir -p "$WORK/$(dirname "$1")"
  printf '%s\n' "$2" > "$WORK/$1"
  git -C "$WORK" add -f "$1"
  git -C "$WORK" commit -qm "add $1"
}

g1() { # 로컬==원격 → SYNC / e2e 성공 종료
  sandbox
  if [ "$GATE_MODE" -eq 1 ]; then
    gate; local rc=$?
    [ $rc -eq 0 ] && grep -qxF SYNC "$T/gate.out" && ok "g1 로컬==원격 SYNC" || no "g1 로컬==원격 SYNC"
  else
    pub; [ $? -eq 0 ] && ok "g1 로컬==원격 SYNC" || no "g1 로컬==원격 SYNC"
  fi
}

g2() { # 안전한 미전송 커밋 → 통과
  sandbox
  commit_file posts/2026-10-02.md "# 안전 글"
  expect_sent "g2 안전 미전송 커밋 통과" posts/2026-10-02.md
}

g3() { # 중간 커밋에서 금지 경로 추가 → 다음 커밋에서 삭제해도 거부
  sandbox
  commit_file private-note.txt "그냥 메모"
  git -C "$WORK" rm -q private-note.txt
  git -C "$WORK" commit -qm "delete private-note.txt"
  expect_blocked "g3 중간 커밋 금지 경로(추가 후 삭제) 거부"
}

g4() { # 허용 경로에 차단어 커밋 → 다음 커밋에서 안전하게 덮어써도 과거 blob 거부
  sandbox
  commit_file posts/2026-10-02.md "# 글 $TERM"
  commit_file posts/2026-10-02.md "# 글 안전 본문"
  expect_blocked "g4 과거 커밋의 차단어 blob 거부"
}

g5() { # merge 결과에서만 생긴 경로도 수집한다
  sandbox
  local base_br
  base_br=$(git -C "$WORK" branch --show-current)
  git -C "$WORK" checkout -qb side
  commit_file posts/2026-10-03.md "# 사이드 글"
  git -C "$WORK" checkout -q "$base_br"
  commit_file posts/2026-10-02.md "# 메인 글"
  if ! git -C "$WORK" merge --no-commit --no-ff side >/dev/null 2>&1; then
    no "g5 merge 결과 전용 경로 거부"; return
  fi
  printf '%s\n' "그냥 메모" > "$WORK/drafts/merge-only.txt"
  git -C "$WORK" add -f drafts/merge-only.txt
  git -C "$WORK" commit -qm merge
  expect_blocked "g5 merge 결과 전용 경로 거부"
}

g6() { # 작업 파일은 깨끗해도 커밋된 blob이 더러우면 거부
  sandbox
  commit_file posts/2099-01-01.md "# 글 $TERM"
  printf '# 글 안전 본문\n' > "$WORK/posts/2099-01-01.md"   # 미커밋 수정
  expect_blocked "g6 작업 파일과 다른 커밋 blob 거부"
}

g7() { # 허용 목록 항목이 나오는 blob은 통과
  sandbox
  f="$WORK/course/labs/kit/tests/selfcheck.py"
  mkdir -p "$(dirname "$f")"
  for i in $(seq 49); do echo "pad $i"; done > "$f"
  echo "# $TERM" >> "$f"
  git -C "$WORK" add -f course/labs/kit/tests/selfcheck.py
  git -C "$WORK" commit -qm "add selfcheck"
  expect_sent "g7 허용 목록 검출 통과" course/labs/kit/tests/selfcheck.py
}

g8() { # 한글·공백이 든 허용 경로는 정상 통과
  sandbox
  commit_file "course/한글 파일.md" "안전 본문"
  expect_sent "g8 한글·공백 파일명 통과" "course/한글 파일.md"
}

g9() { # 원격이 앞서면 거부(stamp 갱신 등 성공 처리 없음)
  sandbox
  git clone -q "$REMOTE" "$T/other"
  git -C "$T/other" config user.name t
  at='@'; git -C "$T/other" config user.email "t${at}e.invalid"
  echo "남의 변경" > "$T/other/elsewhere.txt"
  git -C "$T/other" add elsewhere.txt
  git -C "$T/other" commit -qm "remote ahead"
  git -C "$T/other" push -q origin "$BR"
  git -C "$WORK" fetch -q origin
  mark_tip
  expect_blocked "g9 원격이 앞선 상태 거부"
}

g10() { # 검사기 자체 오류(차단어 목록 부재)면 통과시키지 않는다
  sandbox
  commit_file posts/2026-10-02.md "# 안전 글"
  rm "$BL"
  expect_blocked "g10 차단어 목록 부재는 오류로 거부"
}

g11() { # 갈라진 상태도 거부
  sandbox
  commit_file posts/2026-10-02.md "# 안전 글"
  git clone -q "$REMOTE" "$T/other"
  git -C "$T/other" config user.name t
  at='@'; git -C "$T/other" config user.email "t${at}e.invalid"
  echo "남의 변경" > "$T/other/elsewhere.txt"
  git -C "$T/other" add elsewhere.txt
  git -C "$T/other" commit -qm "remote ahead"
  git -C "$T/other" push -q origin "$BR"
  git -C "$WORK" fetch -q origin
  mark_tip
  expect_blocked "g11 갈라진 상태 거부"
}

echo "subject: $SUBJECT"
g1; g2; g3; g4; g5; g6; g7; g8; g9; g10; g11
echo "== $PASS passed, $FAILED failed =="
[ "$FAILED" -eq 0 ]
