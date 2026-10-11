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
staged=$(git diff --cached --name-only) || fail 1 "형님, 스테이징 목록을 확인하지 못해 중단했습니다."
extra=$(printf '%s\n' "$staged" | grep -vE '^(course/.+|index\.html)$' || true)
[ -n "$extra" ] && fail 1 "형님, 스테이징에 학습 과정 발행과 무관한 파일이 섞여 있어 커밋하지 않았습니다: $(printf '%s' "$extra" | tr '\n' ' ')"

git diff --cached --quiet || \
  git commit -q -m "Publish course $(date +%F)" || \
  fail 1 "형님, 학습 과정 커밋이 실패해 발행하지 않았습니다. 스테이징 상태는 그대로입니다."

# 원격으로 나가는 모든 커밋(이전 실행이 남긴 것 포함)의 변경 파일이 허용 경로 안이고 검사를 통과해야 한다.
if git rev-parse --verify -q origin/main >/dev/null; then
  base=origin/main
else
  base=4b825dc642cb6eb9a060e54bf8d69288fbee4904
fi
if ! outgoing=$(git rev-list "$base..HEAD"); then
  fail 1 "형님, 미전송 커밋을 확인하지 못해 중단했습니다."
fi
if [ -z "$outgoing" ]; then
  # 미전송 커밋이 없다 = 로컬이 원격과 같다. 변경이 없어도 stamp를 갱신할 수 있다.
  touch "$STAMP"
  exit 0
fi
paths=$(git diff --name-only "$base..HEAD") || fail 1 "형님, 미전송 커밋의 변경 파일을 확인하지 못해 중단했습니다."
bad=$(printf '%s\n' "$paths" | grep -vE '^(course/.+|index\.html|posts/[0-9]{4}-[0-9]{2}-[0-9]{2}\.(md|html))$' || true)
[ -n "$bad" ] && fail 1 "형님, 미전송 커밋에 발행 경계 밖 파일이 있어 푸시하지 않았습니다: $(printf '%s' "$bad" | tr '\n' ' ')"
send_list=$(git diff --name-only --diff-filter=d "$base..HEAD") || fail 1 "형님, 미전송 커밋의 변경 파일을 확인하지 못해 중단했습니다."
send=()
missing=
while IFS= read -r f; do
  [ -z "$f" ] && continue
  if [ -f "$f" ]; then
    send+=("$f")
  else
    missing="$missing $f"
  fi
done <<< "$send_list"
[ -n "$missing" ] && fail 1 "형님, 미전송 커밋의 파일이 작업 트리에 없어 검사하지 못했습니다:$missing"
if [ ${#send[@]} -gt 0 ]; then
  blocked=$(check_scan "${send[@]}")
  rc=$?
  if [ "$rc" -eq 1 ]; then
    fail 1 "형님, 미전송 커밋이 개인정보 검사에 걸려 푸시하지 않았습니다. 걸린 곳: $(printf '%s' "$blocked" | tr '\n' ' ')"
  elif [ "$rc" -ne 0 ]; then
    fail 2 "형님, 미전송 커밋의 개인정보 검사 자체가 실패해 푸시하지 않았습니다."
  fi
fi

if git push -q origin main; then
  touch "$STAMP"
  notify "형님, AI 엔지니어링 학습 과정 새 차수를 발행했습니다. https://starceas.github.io/daily-gajae/course/"
else
  fail 1 "형님, 학습 과정 푸시가 실패했습니다. 커밋은 로컬에 남아 있습니다."
fi
