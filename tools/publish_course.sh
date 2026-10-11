#!/bin/bash
# 오전 7시 학습 과정 발행: 원본 폴더에 새 합의(DONE)가 생겼을 때만 course/를 다시 만들어 푸시한다.
# 개인정보 검사에서 검토된 오탐(course-scan-allow.txt) 밖의 걸림이 있으면 푸시하지 않고 채널에 알린다.
set -u
REPO="${REPO:-$HOME/daily-gajae}"
SRC="${SRC:-$HOME/ai-eng-curriculum-20261001}"
STAMP="${STAMP:-$HOME/gajaeway/state/diary/course-published.stamp}"
CHANNEL="${CHANNEL:-1532405201624109238}"
POST="${POST:-$HOME/gajaeway/ops/notify/post.py}"
COURSE_BUILD="${COURSE_BUILD:-uv run -q --with markdown python tools/build_course.py}"
ALLOW="tools/course-scan-allow.txt"
cd "$REPO" || exit 1
notify() { python3 "$POST" "$CHANNEL" /bin/echo "$1" >/dev/null; }
fail() { notify "$2"; exit "$1"; }

[ -f "$SRC/DONE" ] || exit 0
[ -f "$STAMP" ] && [ ! "$SRC/DONE" -nt "$STAMP" ] && exit 0

$COURSE_BUILD "$SRC" || fail 1 "형님, 학습 과정 빌드가 실패해 발행하지 않았습니다."
python3 tools/build.py >/dev/null || fail 1 "형님, 학습 과정 발행 중 사이트 빌드가 실패했습니다."

# 검사 대상: course/ 아래 모든 파일과 index.html. 공백·특수문자가 든 이름도 보존해 전달한다.
files=()
while IFS= read -r -d '' f; do files+=("$f"); done < <(find course -type f -print0)
[ ${#files[@]} -eq 0 ] && fail 1 "형님, 학습 과정 검사 대상 파일이 없어 발행하지 않았습니다."
files+=(index.html)

# 허용 목록(주석·빈 줄 제외)에 정확히 없는 검출 줄만 통과시킨다.
unallowed() { grep -vxF -f <(grep -vE '^[[:space:]]*(#|$)' "$ALLOW"); }

# 종료 상태: 0=통과, 1=검출(허용 목록 적용 후 남은 것만 차단), 2 이상=검사 자체 오류.
check_scan() {
  local out rc left
  out=$(python3 tools/scan.py "$@")
  rc=$?
  if [ "$rc" -eq 0 ]; then
    return 0
  elif [ "$rc" -eq 1 ]; then
    [ -z "$out" ] && return 2
    left=$(printf '%s\n' "$out" | unallowed)
    if [ -n "$left" ]; then
      printf '%s' "$left"
      return 1
    fi
    return 0
  fi
  return 2
}

blocked=$(check_scan "${files[@]}")
rc=$?
if [ "$rc" -eq 1 ]; then
  fail 1 "형님, 학습 과정 새 차수가 개인정보 검사에 걸려 발행하지 않았습니다. 걸린 곳: $(printf '%s' "$blocked" | tr '\n' ' ')"
elif [ "$rc" -ne 0 ]; then
  fail 2 "형님, 학습 과정 개인정보 검사 자체가 실패해 발행하지 않았습니다."
fi

# 커밋 경계: 검사를 통과한 course/ 변경분과 index.html만 커밋한다.
git add -A course index.html
extra=()
while IFS= read -r -d '' f; do
  case "$f" in
    course/*|index.html) ;;
    *) extra+=("$f") ;;
  esac
done < <(git diff --cached --name-only -z)
[ ${#extra[@]} -gt 0 ] && fail 1 "형님, 스테이징에 학습 과정 발행과 무관한 파일이 섞여 있어 커밋하지 않았습니다: ${extra[*]}"

git diff --cached --quiet || \
  git commit -q -m "Publish course $(date +%F)" || \
  fail 1 "형님, 학습 과정 커밋이 실패해 발행하지 않았습니다. 스테이징 상태는 그대로입니다."

# push 직전 공유 관문: 미전송 커밋 전체의 새 (경로, blob)이 허용 경로이고 검사를
# 통과해야 한다. 로컬==원격일 때만 무변경 성공(stamp 갱신)이다.
git fetch -q origin || fail 1 "형님, 학습 과정 원격 확인이 실패해 푸시하지 않았습니다."
gate_out=$(python3 tools/push_gate.py); grc=$?
if [ $grc -eq 0 ] && [ "$gate_out" = "SYNC" ]; then
  touch "$STAMP"
  exit 0
elif [ $grc -eq 1 ]; then
  fail 1 "형님, 학습 과정 미전송 커밋이 발행 경계 검사에 걸려 푸시하지 않았습니다. $(printf '%s' "$gate_out" | tr '\n' ' ')"
elif [ $grc -ne 0 ]; then
  fail 2 "형님, 학습 과정 발행 경계 검사 자체가 실패해 푸시하지 않았습니다."
fi

if git push -q --no-follow-tags origin refs/heads/main:refs/heads/main; then
  touch "$STAMP"
  notify "형님, AI 엔지니어링 학습 과정 새 차수를 발행했습니다. https://starceas.github.io/daily-gajae/course/"
  exit 0
else
  fail 1 "형님, 학습 과정 푸시가 실패했습니다. 커밋은 로컬에 남아 있습니다."
fi
