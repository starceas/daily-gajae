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
  git -C "$WORK" symbolic-ref HEAD refs/heads/main  # 운영 관문·발행기는 main 고정
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

  # 발행기 PR 흐름: 실제 GitHub 대신 gh 대역으로 로컬 bare 원격에 머지한다.
  GH_STUB="$ROOT/tests/diary/gh_stub.py"
  if [ -f "$GH_STUB" ]; then
    mkdir -p "$T/bin"
    printf '#!/bin/sh\nexec python3 %q "$@"\n' "$GH_STUB" > "$T/bin/gh"
    chmod +x "$T/bin/gh"
    GH_STATE="$T/gh-state.json"; : > "$GH_STATE"
    HAVE_GH_STUB=1
  else
    HAVE_GH_STUB=0
  fi
}

gate() { (cd "$WORK" && env DIARY_BLOCKLIST="$BL" python3 tools/push_gate.py >"$T/gate.out" 2>"$T/gate.err"); }
pub()  { (cd "$WORK" && env PATH="$T/bin:$PATH" REPO="$WORK" POST="$STUB" CHANNEL=0 DIARY_BLOCKLIST="$BL" NOTIFY_LOG="$NOTIFY" \
           GH_STUB_REMOTE="$REMOTE" GH_STUB_STATE="$GH_STATE" GH_STUB_CHECKS="${CHECKS_OVERRIDE:-pass}" \
           GH_STUB_LOG="$T/gh.log" bash tools/publish.sh >"$T/pub.log" 2>&1); }
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

g12() { # 같은 경로 안전→차단→다른 안전 3버전: 열거한 중간 blob도 실제로 검사돼야 거부
  sandbox
  commit_file posts/2026-10-02.md "# 글 첫 안전본"
  commit_file posts/2026-10-02.md "# 글 $TERM"
  commit_file posts/2026-10-02.md "# 글 다른 안전본"
  expect_blocked "g12 같은 경로 세 버전의 중간 차단 blob 거부"
}

g13() { # git cat-file -t 조회 실패는 blob 생략이 아니라 관문 오류(2)
  sandbox
  commit_file posts/2026-10-02.md "# 글 $TERM"
  mkdir -p "$T/bin"
  real_git=$(command -v git)
  cat > "$T/bin/git" <<EOF
#!/bin/bash
if [ "\$1" = "cat-file" ] && [ "\$2" = "-t" ]; then
  echo "synthetic object lookup failure" >&2
  exit 128
fi
exec "$real_git" "\$@"
EOF
  chmod +x "$T/bin/git"
  if [ "$GATE_MODE" -eq 1 ]; then
    (cd "$WORK" && env PATH="$T/bin:$PATH" DIARY_BLOCKLIST="$BL" \
      python3 tools/push_gate.py >"$T/gate.out" 2>"$T/gate.err")
    local rc=$?
    [ $rc -eq 2 ] && ok "g13 cat-file -t 조회 실패는 관문 오류" || no "g13 cat-file -t 조회 실패는 관문 오류"
  else
    draft "정상 글" 2026-10-09
    (cd "$WORK" && env PATH="$T/bin:$PATH" REPO="$WORK" POST="$STUB" CHANNEL=0 \
      DIARY_BLOCKLIST="$BL" NOTIFY_LOG="$NOTIFY" bash tools/publish.sh >"$T/pub.log" 2>&1)
    local rc=$?
    if [ $rc -ne 0 ] && [ "$(remote_tip)" = "$TIP0" ]; then
      ok "g13 cat-file -t 조회 실패는 관문 오류"
    else
      no "g13 cat-file -t 조회 실패는 관문 오류"
    fi
  fi
}

g14() { # 검사기 exit 1 + 빈 stdout은 위반 0건이 아니라 관문 오류(2)
  sandbox
  commit_file posts/2026-10-02.md "# 안전 글"
  cat > "$WORK/tools/scan.py" <<'PY'
import sys
sys.exit(1)
PY
  if [ "$GATE_MODE" -eq 1 ]; then
    gate; local rc=$?
    [ $rc -eq 2 ] && ok "g14 검사기 빈 출력·exit 1은 관문 오류" || no "g14 검사기 빈 출력·exit 1은 관문 오류"
  else
    draft "정상 글" 2026-10-09
    pub; local rc=$?
    if [ $rc -ne 0 ] && [ "$(remote_tip)" = "$TIP0" ]; then
      ok "g14 검사기 빈 출력·exit 1은 관문 오류"
    else
      no "g14 검사기 빈 출력·exit 1은 관문 오류"
    fi
  fi
}

g15() { # 다른 브랜치 체크아웃 + 로컬 main에 미감사 커밋 → 관문 오류(2)·발행 경유 원격 불변
  sandbox
  commit_file posts/2026-10-02.md "# 글 $TERM"      # 로컬 main의 미감사(차단어) 커밋
  git -C "$WORK" checkout -qb side 'HEAD^'
  commit_file posts/2026-10-03.md "# 안전 글"        # HEAD(감사 대상)는 안전하고 원격보다 앞섬
  if [ "$GATE_MODE" -eq 1 ]; then
    gate; local rc=$?
    [ $rc -eq 2 ] && [ -s "$T/gate.err" ] \
      && ok "g15 다른 브랜치 체크아웃 관문 오류" || no "g15 다른 브랜치 체크아웃 관문 오류"
  fi
  pub; local prc=$?
  if [ $prc -ne 0 ] && [ "$(remote_tip)" = "$TIP0" ]; then
    ok "g15 발행 경유 원격 불변"
  else
    no "g15 발행 경유 원격 불변"
  fi
}

g16() { # 분리된 HEAD → 관문 오류(2)·발행 경유 원격 불변
  sandbox
  commit_file posts/2026-10-02.md "# 안전 글"        # HEAD는 안전하고 원격보다 앞섬
  git -C "$WORK" checkout -q --detach HEAD
  if [ "$GATE_MODE" -eq 1 ]; then
    gate; local rc=$?
    [ $rc -eq 2 ] && [ -s "$T/gate.err" ] \
      && ok "g16 분리된 HEAD 관문 오류" || no "g16 분리된 HEAD 관문 오류"
  fi
  pub; local prc=$?
  if [ $prc -ne 0 ] && [ "$(remote_tip)" = "$TIP0" ]; then
    ok "g16 발행 경유 원격 불변"
  else
    no "g16 발행 경유 원격 불변"
  fi
}

g17() { # push.followTags=true → 두 발행기 각각 주석 태그를 동반 전송하지 않는다
  sandbox
  git -C "$WORK" config push.followTags true
  commit_file posts/2026-10-02.md "# 안전 글"
  tagname="g17-note"; tagmsg="note-$TERM"        # 태그·차단어 문구는 실행 시 조립
  git -C "$WORK" tag -a "$tagname" -m "$tagmsg"

  # 일기 발행기: 발행은 성공, 원격에는 refs/heads/main만 남아야 한다.
  pub; local prc=$?
  if [ $prc -eq 0 ] && \
     [ "$(git --git-dir="$REMOTE" for-each-ref --format='%(refname)')" = "refs/heads/main" ]; then
    ok "g17 일기 발행 태그 미전송"
  else
    no "g17 일기 발행 태그 미전송"
  fi

  # 강의 발행기: 합성 원본(DONE+payload)·빌드 스텁·stamp 픽스처로 실행한다.
  mkdir -p "$T/src/payload"
  printf '안전 본문\n' > "$T/src/payload/g17.md"
  touch "$T/src/DONE"
  cat > "$T/cbuild.sh" <<'SH'
#!/bin/bash
src="$1"
mkdir -p course
cp -R "$src/payload/." course/
SH
  chmod +x "$T/cbuild.sh"
  (cd "$WORK" && env REPO="$WORK" SRC="$T/src" STAMP="$T/course.stamp" \
    POST="$STUB" CHANNEL=0 DIARY_BLOCKLIST="$BL" NOTIFY_LOG="$NOTIFY" \
    COURSE_BUILD="$T/cbuild.sh" \
    bash tools/publish_course.sh >"$T/pubc.log" 2>&1)
  local crc=$?
  if [ $crc -eq 0 ] && [ -f "$T/course.stamp" ] && \
     [ "$(git --git-dir="$REMOTE" for-each-ref --format='%(refname)')" = "refs/heads/main" ]; then
    ok "g17 강의 발행 태그 미전송"
  else
    no "g17 강의 발행 태그 미전송"
  fi
}

echo "subject: $SUBJECT"
g1; g2; g3; g4; g5; g6; g7; g8; g9; g10; g11; g12; g13; g14; g15; g16; g17
echo "== $PASS passed, $FAILED failed =="
[ "$FAILED" -eq 0 ]
