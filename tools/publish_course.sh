#!/bin/bash
# 오전 7시 학습 과정 발행: 원본 폴더에 새 합의(DONE)가 생겼을 때만 course/를 다시 만들어 푸시한다.
# 개인정보 검사에서 검토된 오탐(course-scan-allow.txt) 밖의 걸림이 있으면 푸시하지 않고 채널에 알린다.
set -u
REPO="$HOME/daily-gajae"
SRC="$HOME/ai-eng-curriculum-20261001"
STAMP="$HOME/gajaeway/state/diary/course-published.stamp"
CHANNEL=1532405201624109238
POST="$HOME/gajaeway/ops/notify/post.py"
cd "$REPO" || exit 1
notify() { python3 "$POST" "$CHANNEL" /bin/echo "$1" >/dev/null; }

[ -f "$SRC/DONE" ] || exit 0
[ -f "$STAMP" ] && [ ! "$SRC/DONE" -nt "$STAMP" ] && exit 0

uv run -q --with markdown python tools/build_course.py "$SRC" || { notify "형님, 학습 과정 빌드가 실패해 발행하지 않았습니다."; exit 1; }
python3 tools/build.py >/dev/null || { notify "형님, 학습 과정 발행 중 사이트 빌드가 실패했습니다."; exit 1; }
hits=$(python3 tools/scan.py $(find course -type f) index.html | grep -vxF -f tools/course-scan-allow.txt)
if [ -n "$hits" ]; then
  notify "형님, 학습 과정 새 차수가 개인정보 검사에 걸려 발행하지 않았습니다. 걸린 곳: $(echo "$hits" | tr '\n' ' ')"
  exit 1
fi
git add -A course index.html
git commit -q -m "Publish course $(date +%F)" || { touch "$STAMP"; exit 0; }
if git push -q origin main; then
  touch "$STAMP"
  notify "형님, AI 엔지니어링 학습 과정 새 차수를 발행했습니다. https://starceas.github.io/daily-gajae/course/"
else
  notify "형님, 학습 과정 푸시가 실패했습니다. 커밋은 로컬에 남아 있습니다."
fi
