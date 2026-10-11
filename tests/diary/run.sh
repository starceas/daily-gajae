#!/bin/bash
# publish.sh 회귀시험 — 임시 저장소·로컬 bare 원격·알림 스텁·합성 차단어로 실행한다.
#
# 사용:
#   bash tests/diary/run.sh                      # 현재 tools/publish.sh와 .gitignore 대상
#   PUBLISH_SH=/path/old-publish.sh \
#   GITIGNORE_SRC=/path/old-gitignore \
#     bash tests/diary/run.sh                    # 수정 전 버전 대조 실행
#
# 시나리오:
#   s1 정상+거부+미검사 파일 동시 → 원격 tree에는 승인 파일만
#   s2 비날짜 파일명 초안 → 뒤이은 정상 초안이 발행됨
#   s3 빌드 실패 → 초안 복구, 다음 실행 성공
#   s4 커밋 실패 → 비정상 종료·초안 복구, 다음 실행 성공
#   s5 push 실패 → 비정상 종료, 새 초안 없이 재실행해 전송됨
#   s6 스테이징 잔류물 → 커밋에 안 들어감
#   s7 미전송 커밋에 금지 파일 → push 거부
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PUBLISH_SH="${PUBLISH_SH:-$ROOT/tools/publish.sh}"
GITIGNORE_SRC="${GITIGNORE_SRC:-$ROOT/.gitignore}"
TOOLS_SRC="${TOOLS_SRC:-$ROOT/tools}"

pass=0
fail=0
ok() { pass=$((pass + 1)); printf 'PASS %s\n' "$1"; }
no() { fail=$((fail + 1)); printf 'FAIL %s\n' "$1"; }
assert() {
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then ok "$desc"; else no "$desc"; fi
}
assert_not() {
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then no "$desc"; else ok "$desc"; fi
}

remote_ls() { git --git-dir="$REMOTE" ls-tree -r --name-only main; }
has_remote() { remote_ls | grep -qxF "$1"; }
notify_has() { grep -qF "$1" "$NOTIFY"; }

# $1=파일명(확장자 제외) $2=제목 $3=본문(생략 가능)
mk_draft() { printf '# %s\n\n%s\n' "$2" "${3:-본문입니다.}" > "$WORK/drafts/$1.md"; }

sandbox() {
  T=$(mktemp -d)
  SANDBOX="$T"
  REMOTE="$T/remote.git"
  WORK="$T/work"
  NOTIFY="$T/notify.log"; : > "$NOTIFY"
  BLOCKLIST="$T/blocklist.txt"; printf 'ZZZFAKEBLOCKWORDZZZ\n' > "$BLOCKLIST"
  STUB="$T/post_stub.py"
  cat > "$STUB" <<'PY'
import os, sys
with open(os.environ["NOTIFY_LOG"], "a") as f:
    f.write(" ".join(sys.argv[3:]) + "\n")
PY
  git init -q --bare "$REMOTE"
  git init -q "$WORK"
  local at='@'
  git -C "$WORK" config user.email "test${at}example.invalid"
  git -C "$WORK" config user.name "test"
  mkdir -p "$WORK/tools" "$WORK/posts" "$WORK/drafts"
  cp "$TOOLS_SRC"/*.py "$WORK/tools/"
  cp "$PUBLISH_SH" "$WORK/tools/publish.sh"
  cp "$GITIGNORE_SRC" "$WORK/.gitignore"
  printf '# 시드 글\n\n본문입니다.\n' > "$WORK/posts/2026-10-01.md"
  (cd "$WORK" && python3 tools/build.py >/dev/null)
  git -C "$WORK" add -A
  git -C "$WORK" commit -qm seed
  git -C "$WORK" remote add origin "$REMOTE"
  git -C "$WORK" push -q -u origin main
}

run_pub() {
  (cd "$WORK" && env REPO="$WORK" POST="$STUB" CHANNEL=000 \
    DIARY_BLOCKLIST="$BLOCKLIST" NOTIFY_LOG="$NOTIFY" \
    bash tools/publish.sh >"$T/pub.log" 2>&1)
}

# s1: 정상 초안 + 거부 초안 + 검사 대상이 아닌 파일이 함께 있어도 승인 파일만 원격에 간다.
s1() {
  sandbox
  local at='@' dot='.'
  mk_draft 2026-10-02 "정상 글"
  mk_draft 2026-10-03 "거부 글" "여기에 ZZZFAKEBLOCKWORDZZZ 와 someone${at}nowhere${dot}invalid 포함"
  printf '검사 대상이 아닌 메모\n' > "$WORK/drafts/notes.txt"
  run_pub
  assert "s1 정상+거부 동시 실행은 성공 종료" test $? -eq 0
  assert "s1 원격에 승인 md 있음" has_remote posts/2026-10-02.md
  assert "s1 원격에 승인 html 있음" has_remote posts/2026-10-02.html
  assert_not "s1 원격에 거부 md 없음" has_remote posts/2026-10-03.md
  assert_not "s1 원격에 drafts 경로 0건" sh -c "git --git-dir='$REMOTE' ls-tree -r --name-only main | grep -q '^drafts/'"
  assert_not "s1 원격에 미검사 txt 없음" remote_ls_grep notes.txt
  assert "s1 거부 초안은 drafts에 남음" test -f "$WORK/drafts/2026-10-03.md"
  assert "s1 미검사 파일은 drafts에 남음" test -f "$WORK/drafts/notes.txt"
  assert "s1 알림에 거부 파일명 있음" notify_has 2026-10-03
  assert_not "s1 알림에 차단어 원문 없음" notify_has ZZZFAKEBLOCKWORDZZZ
}
remote_ls_grep() { remote_ls | grep -qF "$1"; }

# s2: 형식이 잘못된 초안은 거부되고 뒤이은 정상 초안 발행을 막지 않는다.
s2() {
  sandbox
  mk_draft "not-a-date" "잘못된 이름의 글"
  mk_draft 2026-13-99 "달력에 없는 날짜"
  printf '제목 줄이 없는 본문\n' > "$WORK/drafts/2026-10-04.md"
  printf '\xff\xfeUTF-8이 아님\n' > "$WORK/drafts/2026-10-05.md"
  printf '# 외부를 가리키는 링크\n' > "$T/target.md"
  ln -s "$T/target.md" "$WORK/drafts/2026-10-06.md"
  run_pub
  assert "s2 잘못된 초안만 있으면 성공 종료(거부 알림)" test $? -eq 0
  assert "s2 비날짜 초안은 drafts에 남음" test -f "$WORK/drafts/not-a-date.md"
  assert "s2 달력에 없는 날짜는 drafts에 남음" test -f "$WORK/drafts/2026-13-99.md"
  assert "s2 제목 없는 초안은 drafts에 남음" test -f "$WORK/drafts/2026-10-04.md"
  assert "s2 비UTF-8 초안은 drafts에 남음" test -f "$WORK/drafts/2026-10-05.md"
  assert "s2 링크 초안은 drafts에 남음" test -L "$WORK/drafts/2026-10-06.md"
  assert "s2 알림에 거부 파일명 있음" notify_has not-a-date
  assert "s2 알림에 링크 사유 있음" notify_has "일반 파일이 아님"
  mk_draft 2026-10-02 "정상 글"
  run_pub
  assert "s2 뒤이은 정상 초안 실행 성공" test $? -eq 0
  assert "s2 정상 초안이 원격에 발행됨" has_remote posts/2026-10-02.md
  assert_not "s2 비날짜 파일은 원격에 없음" remote_ls_grep not-a-date
  assert_not "s2 링크 대상 내용은 원격에 없음" remote_ls_grep 2026-10-06
}

# s3: 빌드 실패 뒤 옮긴 초안이 복구되고 다음 실행이 성공한다.
s3() {
  sandbox
  printf 'import sys; sys.exit(1)\n' > "$WORK/tools/build.py"
  mk_draft 2026-10-02 "정상 글"
  run_pub
  assert_not "s3 빌드 실패는 비정상 종료" test $? -eq 0
  assert "s3 초안이 drafts로 복구됨" test -f "$WORK/drafts/2026-10-02.md"
  assert_not "s3 posts에 초안이 남지 않음" test -e "$WORK/posts/2026-10-02.md"
  assert_not "s3 posts에 생성 html이 남지 않음" test -e "$WORK/posts/2026-10-02.html"
  assert "s3 posts·index가 HEAD와 동일" sh -c "test -z \"\$(git -C '$WORK' status --porcelain -- posts index.html)\""
  cp "$TOOLS_SRC/build.py" "$WORK/tools/build.py"
  run_pub
  assert "s3 복구 후 재실행 성공" test $? -eq 0
  assert "s3 재실행으로 원격에 발행됨" has_remote posts/2026-10-02.md
}

# s4: 커밋 실패는 성공으로 삼키지 않고 초안을 복구한다.
s4() {
  sandbox
  printf '#!/bin/sh\nexit 1\n' > "$WORK/.git/hooks/pre-commit"
  chmod +x "$WORK/.git/hooks/pre-commit"
  mk_draft 2026-10-02 "정상 글"
  local before
  before=$(git -C "$WORK" rev-parse HEAD)
  run_pub
  assert_not "s4 커밋 실패는 비정상 종료" test $? -eq 0
  assert "s4 초안이 drafts로 복구됨" test -f "$WORK/drafts/2026-10-02.md"
  assert_not "s4 posts에 초안이 남지 않음" test -e "$WORK/posts/2026-10-02.md"
  assert "s4 HEAD가 변하지 않음" sh -c "test \"\$(git -C '$WORK' rev-parse HEAD)\" = '$before'"
  assert "s4 알림에 커밋 실패 사유 있음" notify_has "커밋이 실패"
  rm "$WORK/.git/hooks/pre-commit"
  run_pub
  assert "s4 훅 제거 후 재실행 성공" test $? -eq 0
  assert "s4 재실행으로 원격에 발행됨" has_remote posts/2026-10-02.md
}

# s5: push 실패는 비정상 종료이고, 새 초안 없이 재실행하면 미전송 커밋이 전송된다.
s5() {
  sandbox
  mk_draft 2026-10-02 "정상 글"
  git -C "$WORK" remote set-url origin "$T/gone.git"
  run_pub
  assert_not "s5 push 실패는 비정상 종료" test $? -eq 0
  assert "s5 알림에 푸시 실패 사유 있음" notify_has "푸시가 실패"
  assert_not "s5 실패 시점에 원격에 글 없음" has_remote posts/2026-10-02.md
  git -C "$WORK" remote set-url origin "$REMOTE"
  run_pub
  assert "s5 새 초안 없이 재실행 성공" test $? -eq 0
  assert "s5 미전송 커밋이 원격에 전송됨" has_remote posts/2026-10-02.md
}

# s6: 이전 실행이 남긴 스테이징 잔류물은 커밋에 들어가지 않는다.
s6() {
  sandbox
  printf '잔류물\n' > "$WORK/staged-junk.txt"
  git -C "$WORK" add staged-junk.txt
  mk_draft sneaky "스테이징된 초안 잔류물"
  git -C "$WORK" add -f drafts/sneaky.md
  mk_draft 2026-10-02 "정상 글"
  run_pub
  assert "s6 잔류물 있어도 실행 성공" test $? -eq 0
  assert "s6 정상 초안이 원격에 발행됨" has_remote posts/2026-10-02.md
  assert_not "s6 스테이징 잔류 txt는 원격에 없음" remote_ls_grep staged-junk.txt
  assert_not "s6 스테이징 잔류 초안은 원격에 없음" remote_ls_grep sneaky
  assert "s6 커밋 파일이 승인 목록과 일치" sh -c "test -z \"\$(git --git-dir='$REMOTE' diff-tree --no-commit-id --name-only -r main | grep -vxF -e posts/2026-10-02.md -e posts/2026-10-02.html -e index.html || true)\""
}

# s7: 미전송 커밋에 허용 경로 밖 파일이 섞여 있으면 push를 거부한다.
s7() {
  sandbox
  printf '금지 파일\n' > "$WORK/forbidden.txt"
  git -C "$WORK" add forbidden.txt
  git -C "$WORK" commit -qm "unrelated commit"
  run_pub
  assert_not "s7 금지 파일 미전송 커밋은 push 거부" test $? -eq 0
  assert "s7 알림에 거부 파일명 있음" notify_has forbidden.txt
  assert_not "s7 원격에 금지 파일 없음" has_remote forbidden.txt
  assert "s7 로컬 커밋은 보존됨" sh -c "git -C '$WORK' log --format=%s -1 | grep -q 'unrelated commit'"
  mk_draft 2026-10-02 "정상 글"
  run_pub
  assert_not "s7 새 초안이 있어도 여전히 push 거부" test $? -eq 0
  assert_not "s7 원격에 새 글도 밀려 나가지 않음" has_remote posts/2026-10-02.md
}

# s8: 알림 전송 실패는 발행 성공 여부에 영향을 주지 않는다.
s8() {
  sandbox
  printf 'import sys; sys.exit(1)\n' > "$STUB"
  mk_draft 2026-10-02 "정상 글"
  run_pub
  assert "s8 알림 실패에도 발행 성공 종료" test $? -eq 0
  assert "s8 알림 실패에도 원격에 발행됨" has_remote posts/2026-10-02.md
}

s1; s2; s3; s4; s5; s6; s7; s8
printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
