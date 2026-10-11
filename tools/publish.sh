#!/bin/bash
# 아침 발행: drafts/의 초안을 형식 검증·개인정보 검사 후 posts/로 옮기고 빌드·커밋·푸시한다.
# 걸린 초안은 drafts/에 남기고 채널에 사유(파일명·줄 번호·종류)만 알린다.
# 커밋에는 이번에 승인한 posts/<날짜>.md·해당 HTML·index.html만 넣는다.
# push 전에는 미전송 커밋 전체가 허용 경로이고 검사를 통과하는지 다시 확인한다.
# 어느 단계든 실패하면 옮긴 초안을 drafts/로 되돌리고 비정상 종료한다.
set -u
REPO="${REPO:-$HOME/daily-gajae}"
CHANNEL="${CHANNEL:-1532405201624109238}"
POST="${POST:-$HOME/gajaeway/ops/notify/post.py}"
cd "$REPO" || exit 1

notify() {
  if [ "${DIARY_QUIET:-0}" = 1 ]; then
    echo "$1"
  else
    python3 "$POST" "$CHANNEL" /bin/echo "$1" >/dev/null || true
  fi
}

# 형식이 잘못된 초안의 사유를 출력하고 종료 0. 정상이면 출력 없이 종료 1.
invalid_reason() {
  local d="$1" name msg
  name=$(basename "$d")
  if [ -L "$d" ] || [ ! -f "$d" ]; then
    echo "일반 파일이 아님"
    return 0
  fi
  case "$name" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].md) ;;
    *) echo "날짜 형식(YYYY-MM-DD.md) 파일명이 아님"; return 0 ;;
  esac
  msg=$(python3 - "$d" 2>&1 <<'PY'
import datetime, pathlib, sys
p = pathlib.Path(sys.argv[1])
try:
    datetime.date.fromisoformat(p.stem)
except ValueError:
    sys.exit("달력에 없는 날짜")
try:
    text = p.read_text(encoding="utf-8")
except UnicodeDecodeError:
    sys.exit("UTF-8이 아님")
if not any(line.startswith("# ") for line in text.splitlines()):
    sys.exit("제목 줄(# )이 없음")
PY
  ) || { echo "$msg"; return 0; }
  return 1
}

# posts/에 옮긴 초안을 drafts/로 되돌리고 빌드가 만든 결과물을 HEAD로 되돌린다.
# posts/*.md 원본의 미커밋 수정은 건드리지 않는다.
rollback() {
  local n
  for n in ${moved[@]+"${moved[@]}"}; do
    [ -e "posts/$n" ] && mv "posts/$n" "drafts/$n"
    git checkout -q HEAD -- "posts/$n" 2>/dev/null || true
  done
  git checkout -q HEAD -- index.html 2>/dev/null || true
  git checkout -q HEAD -- 'posts/*.html' 2>/dev/null || true
  for n in ${moved[@]+"${moved[@]}"}; do
    git ls-files --error-unmatch "posts/${n%.md}.html" >/dev/null 2>&1 || rm -f "posts/${n%.md}.html"
  done
  git reset -q 2>/dev/null || true
  return 0
}

# 이전 실행 등이 남긴 스테이징 잔류물을 내린다.
git reset -q

# posts/의 .md 원본이 HEAD와 다르거나(수정·삭제·추적 안 된 잔류 파일) 하면
# 빌드 산출물에 승인되지 않은 내용이 섞일 수 있으므로 진행하지 않는다.
dirty=$(git status --porcelain -- 'posts/*.md')
if [ -n "$dirty" ]; then
  notify "형님, 가재 일기 posts/ 원본이 커밋 상태와 달라 발행을 중단했습니다. 확인할 파일: $(echo "$dirty" | awk '{print $2}' | tr '\n' ' ')"
  exit 1
fi

shopt -s nullglob
drafts=(drafts/*.md)
moved=()
published=()

if [ ${#drafts[@]} -gt 0 ]; then
  for d in "${drafts[@]}"; do
    name=$(basename "$d")
    if reason=$(invalid_reason "$d"); then
      notify "형님, 가재 일기 ${name%.md} 초안이 형식 검증에 걸려 발행하지 않았습니다. 사유: $reason"
      continue
    fi
    out=$(python3 tools/scan.py "$d"); rc=$?
    if [ $rc -eq 1 ]; then
      notify "형님, 가재 일기 ${name%.md} 초안이 개인정보 검사에 걸려 발행하지 않았습니다. 걸린 곳: $(echo "$out" | tr '\n' ' ')"
      continue
    elif [ $rc -ne 0 ]; then
      rollback
      notify "형님, 가재 일기 개인정보 검사가 오류로 끝나 발행을 중단했습니다."
      exit 1
    fi
    mv "$d" "posts/$name"
    moved+=("$name")
  done
fi

if [ ${#moved[@]} -gt 0 ]; then
  if ! python3 tools/build.py; then
    rollback
    notify "형님, 가재 일기 빌드가 실패해 발행하지 않았습니다."
    exit 1
  fi
  # 빌드 결과도 한 번 더 검사한다.
  out=$(python3 tools/scan.py posts/*.html index.html); rc=$?
  if [ $rc -ne 0 ]; then
    rollback
    if [ $rc -eq 1 ]; then
      notify "형님, 가재 일기 빌드 결과가 개인정보 검사에 걸려 푸시하지 않았습니다. 걸린 곳: $(echo "$out" | tr '\n' ' ')"
    else
      notify "형님, 가재 일기 빌드 결과 개인정보 검사가 오류로 끝나 푸시하지 않았습니다."
    fi
    exit 1
  fi

  # 승인한 파일만 스테이징한다(drafts/ 등 다른 경로는 절대 넣지 않는다).
  stage=(index.html)
  for n in "${moved[@]}"; do
    stage+=("posts/$n" "posts/${n%.md}.html")
  done
  git add -- "${stage[@]}" || { rollback; notify "형님, 가재 일기 스테이징이 실패해 발행하지 않았습니다."; exit 1; }

  # 커밋 직전: 실제 인덱스가 승인 목록과 일치하는지 확인한다.
  expected=$(printf '%s\n' "${stage[@]}" | LC_ALL=C sort)
  actual=$(git diff --cached --name-only | LC_ALL=C sort)
  extra=$(comm -23 <(printf '%s\n' "$actual") <(printf '%s\n' "$expected"))
  miss=""
  for n in "${moved[@]}"; do
    printf '%s\n' "$actual" | grep -qxF "posts/$n" || miss="$miss posts/$n"
  done
  if [ -n "$extra" ] || [ -n "$miss" ]; then
    rollback
    notify "형님, 가재 일기 커밋 대상이 승인 목록과 달라 발행하지 않았습니다."
    exit 1
  fi

  dates=""
  for n in "${moved[@]}"; do dates="$dates ${n%.md}"; done
  if ! git commit -q -m "Publish${dates}"; then
    rollback
    notify "형님, 가재 일기 커밋이 실패해 발행하지 않았습니다."
    exit 1
  fi
  for n in "${moved[@]}"; do published+=("${n%.md}"); done
  moved=()
fi

# 미전송 커밋이 있으면(이번 커밋 포함) 새 초안 유무와 관계없이 전송을 시도한다.
if git rev-parse -q --verify refs/remotes/origin/main >/dev/null 2>&1; then
  changed=$(git log --pretty=format: --name-only origin/main..HEAD | LC_ALL=C sort -u)
  ahead=$(git rev-list --count origin/main..HEAD)
else
  changed=$(git ls-tree -r --name-only HEAD | LC_ALL=C sort -u)
  ahead=$(git rev-list --count HEAD)
fi

if [ "$ahead" -gt 0 ]; then
  # push 직전: 미전송 커밋이 건드린 파일이 허용 경로인지, 내용이 검사를 통과하는지 확인한다.
  bad_paths=()
  scan_tmp=$(mktemp -d)
  scan_targets=()
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    case "$f" in
      posts/*.md|posts/*.html|index.html) ;;
      *) bad_paths+=("$f"); continue ;;
    esac
    if git cat-file -e "HEAD:$f" 2>/dev/null; then
      mkdir -p "$scan_tmp/$(dirname "$f")"
      git show "HEAD:$f" > "$scan_tmp/$f"
      scan_targets+=("$scan_tmp/$f")
    fi
  done <<EOF
$changed
EOF
  if [ ${#bad_paths[@]} -gt 0 ]; then
    rm -rf "$scan_tmp"
    notify "형님, 가재 일기 미전송 커밋에 허용되지 않은 파일(${bad_paths[*]})이 있어 푸시하지 않았습니다."
    exit 1
  fi
  if [ ${#scan_targets[@]} -gt 0 ]; then
    out=$(python3 tools/scan.py "${scan_targets[@]}"); rc=$?
    if [ $rc -ne 0 ]; then
      rm -rf "$scan_tmp"
      if [ $rc -eq 1 ]; then
        notify "형님, 가재 일기 미전송 커밋이 개인정보 검사에 걸려 푸시하지 않았습니다. 걸린 곳: $(echo "$out" | tr '\n' ' ')"
      else
        notify "형님, 가재 일기 미전송 커밋 개인정보 검사가 오류로 끝나 푸시하지 않았습니다."
      fi
      exit 1
    fi
  fi
  rm -rf "$scan_tmp"

  if git push -q origin main; then
    if [ ${#published[@]} -gt 0 ]; then
      notify "형님, 가재 일기 ${published[*]}를 발행했습니다. https://starceas.github.io/daily-gajae/posts/${published[${#published[@]}-1]}.html"
    else
      notify "형님, 가재 일기 미전송 커밋을 전송했습니다."
    fi
  else
    notify "형님, 가재 일기 푸시가 실패했습니다. 커밋은 로컬에 남아 있습니다."
    exit 1
  fi
fi
exit 0
