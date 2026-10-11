#!/bin/bash
# tests/course/run.sh [대상 루트] — scan.py·publish_course.sh 회귀시험.
# 대상 루트(기본: 이 저장소)의 tools/를 임시 픽스처 저장소에 복사해 실행한다.
# 구버전은 REPO·SRC·STAMP·POST가 $HOME 기준 하드코딩이라, 픽스처를 가짜 $HOME
# 구조로 만들어 신·구버전이 같은 경로를 쓰게 한다. 운영 ~/daily-gajae는 건드리지 않는다.
set -u
DEFAULT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SUBJECT="$(cd "${1:-$DEFAULT_ROOT}" && pwd)"
PASS=0
FAILED=0

ok() { PASS=$((PASS + 1)); printf 'PASS %s\n' "$1"; }
no() { FAILED=$((FAILED + 1)); printf 'FAIL %s — %s\n' "$1" "$2"; }

# 합성 차단어(실명 아님). 검출 시험에 쓴다.
TERM="GAZZI-NAME-XXXX-001"

setup_fixture() {
  T=$(mktemp -d "${TMPDIR:-/tmp}/coursepub.XXXXXX")
  H="$T/home"                      # 가짜 $HOME
  REPO_T="$H/daily-gajae"          # 구버전 하드코딩 경로와 일치
  SRC_T="$H/ai-eng-curriculum-20261001"
  STAMP_T="$H/gajaeway/state/diary/course-published.stamp"
  BARE="$T/origin.git"
  mkdir -p "$REPO_T" "$SRC_T/payload" "$H/gajaeway/state/diary" "$H/gajaeway/ops/notify" "$T/bin"

  git init -q --bare "$BARE"
  git init -q "$REPO_T"
  git -C "$REPO_T" symbolic-ref HEAD refs/heads/main
  cp -R "$SUBJECT/tools" "$REPO_T/tools"
  mkdir -p "$REPO_T/posts"
  git -C "$REPO_T" config user.name "시험"
  u="test"; d="example.invalid"
  git -C "$REPO_T" config user.email "$u@$d"

  # 알림 스텁: 실제 전송 없이 메시지를 로그에 남긴다.
  cat > "$H/gajaeway/ops/notify/post.py" <<'PY'
import os, sys
with open(os.environ["NOTIFY_LOG"], "a") as f:
    f.write(sys.argv[3] + "\n")
PY

  # 시험용 강의 빌드: SRC/payload/* 를 course/ 로 옮긴다.
  cat > "$T/build-stub.sh" <<'SH'
#!/bin/bash
set -u
src="$1"
rm -rf course
mkdir -p course
if [ -d "$src/payload" ]; then cp -R "$src/payload/." course/; fi
SH
  chmod +x "$T/build-stub.sh"

  # 구버전은 빌드 명령이 하드코딩이라 uv 스텁으로 가로챈다(마지막 인자가 SRC).
  cat > "$T/bin/uv" <<'SH'
#!/bin/bash
eval "src=\${$#}"
exec "$BUILD_STUB" "$src"
SH
  chmod +x "$T/bin/uv"

  printf '# 시험용 합성 차단어 — 실명 아님\n%s\n' "$TERM" > "$T/blocklist.txt"

  git -C "$REPO_T" add -A
  git -C "$REPO_T" commit -qm init
  git -C "$REPO_T" push -q "$BARE" main
  git -C "$REPO_T" remote add origin "$BARE"
  git -C "$REPO_T" fetch -q origin
  git -C "$REPO_T" branch --set-upstream-to=origin/main main -q 2>/dev/null || true
  INIT_SHA=$(git -C "$REPO_T" rev-parse HEAD)
}

teardown() { rm -rf "$T"; }

run_publish() {
  env -i \
    PATH="$T/bin:$PATH" \
    HOME="$H" \
    NOTIFY_LOG="$T/notify.log" \
    BUILD_STUB="$T/build-stub.sh" \
    REPO="$REPO_T" \
    SRC="$SRC_T" \
    STAMP="$STAMP_T" \
    POST="$H/gajaeway/ops/notify/post.py" \
    CHANNEL="000" \
    DIARY_BLOCKLIST="$T/blocklist.txt" \
    COURSE_BUILD="$T/build-stub.sh" \
    bash "$SUBJECT/tools/publish_course.sh" >> "$T/publish.out" 2>&1
}

remote_files() { git -C "$REPO_T" ls-tree -r --name-only origin/main 2>/dev/null; }
remote_has() { remote_files | grep -qF "$1"; }

# ① 차단어 목록 없음(검사 오류) → 진행 안 함·stamp 불변
t1() {
  setup_fixture
  rm "$T/blocklist.txt"
  echo "본문" > "$SRC_T/payload/ok.md"
  touch "$SRC_T/DONE"
  run_publish; rc=$?
  if [ "$rc" -ne 0 ] && [ ! -f "$STAMP_T" ] && ! remote_has "course/ok.md"; then
    ok "①차단어 목록 없음 → 미진행·stamp 없음"
  else
    no "①차단어 목록 없음" "rc=$rc stamp=$([ -f "$STAMP_T" ] && echo 있음 || echo 없음) remote=$(remote_files | tr '\n' ' ')"
  fi
  teardown
}

# ② 비UTF-8 파일(읽기 오류) → 진행 안 함
t2() {
  setup_fixture
  printf '\xff\xfe\x00\n' > "$SRC_T/payload/bad.bin"
  touch "$SRC_T/DONE"
  run_publish; rc=$?
  if [ "$rc" -ne 0 ] && [ ! -f "$STAMP_T" ] && ! remote_has "course/bad.bin"; then
    ok "②비UTF-8 파일 → 미진행·stamp 없음"
  else
    no "②비UTF-8 파일" "rc=$rc remote=$(remote_files | tr '\n' ' ')"
  fi
  teardown
}

# ③ 공백이 든 파일명이 스캔됨
t3() {
  setup_fixture
  mkdir -p "$SRC_T/payload/course"
  printf '%s 포함\n' "$TERM" > "$SRC_T/payload/course/file name.md"
  touch "$SRC_T/DONE"
  run_publish; rc=$?
  if [ "$rc" -ne 0 ] && ! remote_has "course/file name.md" && [ ! -f "$STAMP_T" ] && [ -s "$T/notify.log" ]; then
    ok "③공백 파일명 검출 → 차단"
  else
    no "③공백 파일명" "rc=$rc remote=$(remote_files | tr '\n' ' ')"
  fi
  teardown
}

# ④ 다른 디렉터리의 동명 파일 검출이 허용 목록 항목에 가려지지 않음
t4() {
  setup_fixture
  f="$SRC_T/payload/other/selfcheck.py"
  mkdir -p "$(dirname "$f")"
  for i in $(seq 49); do echo "pad $i"; done > "$f"
  echo "# $TERM" >> "$f"
  touch "$SRC_T/DONE"
  run_publish; rc=$?
  if [ "$rc" -ne 0 ] && ! remote_has "course/other/selfcheck.py" && [ ! -f "$STAMP_T" ]; then
    ok "④동명 다른 디렉터리 검출 → 차단"
  else
    no "④동명 다른 디렉터리" "rc=$rc remote=$(remote_files | tr '\n' ' ')"
  fi
  teardown
}

# ⑤ 허용 목록의 정확한 항목만 통과 → 정상 발행
t5() {
  setup_fixture
  f="$SRC_T/payload/labs/kit/tests/selfcheck.py"
  mkdir -p "$(dirname "$f")"
  {
    for i in $(seq 49); do echo "pad $i"; done
    echo "# $TERM"
    for i in $(seq 51 707); do echo "pad $i"; done
    echo "p = open('/tmp/x').read()"
  } > "$f"
  mkdir -p "$SRC_T/payload/course"
  { for i in $(seq 98); do echo "<p>pad $i</p>"; done; echo "<p>재시도하면 2장으로</p>"; } > "$SRC_T/payload/course/02-principles.html"
  { for i in $(seq 118); do echo "pad $i"; done; echo "재시도하면 2장으로"; } > "$SRC_T/payload/course/02-principles.md"
  touch "$SRC_T/DONE"
  run_publish; rc=$?
  if [ "$rc" -eq 0 ] && remote_has "course/labs/kit/tests/selfcheck.py" && [ -f "$STAMP_T" ]; then
    ok "⑤정확한 허용 항목만 → 정상 발행"
  else
    no "⑤정확한 허용 항목" "rc=$rc remote=$(remote_files | tr '\n' ' ')"
  fi
  teardown
}

# ⑥ 커밋 실패 → stamp 불변
t6() {
  setup_fixture
  printf '#!/bin/bash\nexit 1\n' > "$REPO_T/.git/hooks/pre-commit"
  chmod +x "$REPO_T/.git/hooks/pre-commit"
  echo "본문" > "$SRC_T/payload/ok.md"
  touch "$SRC_T/DONE"
  run_publish; rc=$?
  if [ "$rc" -ne 0 ] && [ ! -f "$STAMP_T" ] && [ "$(git -C "$REPO_T" rev-parse HEAD)" = "$INIT_SHA" ]; then
    ok "⑥커밋 실패 → stamp 없음·커밋 없음"
  else
    no "⑥커밋 실패" "rc=$rc stamp=$([ -f "$STAMP_T" ] && echo 있음 || echo 없음)"
  fi
  teardown
}

# ⑦ push 실패 → stamp 불변, 재실행에서 전송
t7() {
  setup_fixture
  echo "본문" > "$SRC_T/payload/ok.md"
  touch "$SRC_T/DONE"
  git -C "$REPO_T" remote set-url origin "$T/gone.git"
  run_publish; rc1=$?
  git -C "$REPO_T" remote set-url origin "$BARE"
  run_publish; rc2=$?
  if [ "$rc1" -ne 0 ] && [ "$rc2" -eq 0 ] && remote_has "course/ok.md" && [ -f "$STAMP_T" ]; then
    ok "⑦push 실패·재실행 전송"
  else
    no "⑦push 실패·재실행" "rc1=$rc1 rc2=$rc2 stamp=$([ -f "$STAMP_T" ] && echo 있음 || echo 없음) remote=$(remote_files | tr '\n' ' ')"
  fi
  teardown
}

# ⑧ 선(先)스테이징된 무관 파일 → 커밋 안 됨
t8() {
  setup_fixture
  echo "일기 잔류" > "$REPO_T/posts/2099-01-01.md"
  git -C "$REPO_T" add "posts/2099-01-01.md"
  echo "본문" > "$SRC_T/payload/ok.md"
  touch "$SRC_T/DONE"
  run_publish; rc=$?
  staged=$(git -C "$REPO_T" diff --cached --name-only | grep -c . || true)
  if [ "$rc" -ne 0 ] && [ "$(git -C "$REPO_T" rev-parse HEAD)" = "$INIT_SHA" ] && [ "$staged" -gt 0 ] && ! remote_has "posts/2099-01-01.md"; then
    ok "⑧선스테이징 무관 파일 → 미커밋"
  else
    no "⑧선스테이징 무관 파일" "rc=$rc head=$(git -C "$REPO_T" rev-parse --short HEAD) remote=$(remote_files | tr '\n' ' ')"
  fi
  teardown
}

# ⑨ 미전송 커밋에 금지 경로 → push 거부
t9() {
  setup_fixture
  echo "메모" > "$REPO_T/notes.txt"
  git -C "$REPO_T" add notes.txt
  git -C "$REPO_T" commit -qm wip
  echo "본문" > "$SRC_T/payload/ok.md"
  touch "$SRC_T/DONE"
  run_publish; rc=$?
  if [ "$rc" -ne 0 ] && ! remote_has "notes.txt" && ! remote_has "course/ok.md" && [ ! -f "$STAMP_T" ]; then
    ok "⑨미전송 금지 경로 → push 거부"
  else
    no "⑨미전송 금지 경로" "rc=$rc remote=$(remote_files | tr '\n' ' ')"
  fi
  teardown
}

echo "subject: $SUBJECT"
t1; t2; t3; t4; t5; t6; t7; t8; t9
echo "== $PASS passed, $FAILED failed =="
[ "$FAILED" -eq 0 ]
