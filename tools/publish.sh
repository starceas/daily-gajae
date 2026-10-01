#!/bin/bash
# 아침 발행: drafts/의 초안을 개인정보 검사 후 posts/로 옮기고 빌드·커밋·푸시한다.
# 검사에 걸린 초안은 발행하지 않고 채널에 사유(줄 번호·종류)만 알린다.
set -u
REPO="$HOME/daily-gajae"
CHANNEL=1532405201624109238
POST="$HOME/gajaeway/ops/notify/post.py"
cd "$REPO" || exit 1

notify() { python3 "$POST" "$CHANNEL" /bin/echo "$1" >/dev/null; }

shopt -s nullglob
drafts=(drafts/*.md)
[ ${#drafts[@]} -eq 0 ] && exit 0

published=()
for d in "${drafts[@]}"; do
  name=$(basename "$d")
  if out=$(python3 tools/scan.py "$d"); then
    git mv -f "$d" "posts/$name" 2>/dev/null || mv "$d" "posts/$name"
    published+=("${name%.md}")
  else
    notify "형님, 가재 일기 ${name%.md} 초안이 개인정보 검사에 걸려 발행하지 않았습니다. 걸린 곳: $(echo "$out" | tr '\n' ' ')"
  fi
done

[ ${#published[@]} -eq 0 ] && exit 0
python3 tools/build.py || { notify "형님, 가재 일기 빌드가 실패해 발행하지 않았습니다."; exit 1; }
# 빌드 결과도 한 번 더 검사한다.
if ! out=$(python3 tools/scan.py posts/*.html index.html); then
  notify "형님, 가재 일기 빌드 결과가 개인정보 검사에 걸려 푸시하지 않았습니다. 걸린 곳: $(echo "$out" | tr '\n' ' ')"
  exit 1
fi
git add -A posts index.html drafts
git commit -q -m "Publish ${published[*]}" || exit 0
if git push -q origin main; then
  notify "형님, 가재 일기 ${published[*]}를 발행했습니다. https://starceas.github.io/daily-gajae/posts/${published[-1]}.html"
else
  notify "형님, 가재 일기 푸시가 실패했습니다. 커밋은 로컬에 남아 있습니다."
fi
