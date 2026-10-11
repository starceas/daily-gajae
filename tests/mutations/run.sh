#!/bin/bash
# tests/mutations/run.sh — 변이 8종: 방어 하나를 제거한 tools 사본으로 시험군을 돌려
# 대응 시험이 실제로 깨지는지 확인한다. 변이가 잡히지 않으면 이 스크립트가 FAIL한다.
#
#   변이 → 기대 FAIL
#   m1 관문 blob 스캔 생략        → gate g4·g6, course ⑬
#   m2 관문 허용 경로 검사 생략    → gate g3·g5, diary s7
#   m3 커밋 전 인덱스 대조 생략    → diary s10
#   m4 빌드 결과 HTML 스캔 생략    → diary s11
#   m5 스캐너 오류를 검출로 취급    → gate g10, diary s12
#   m6 NUL 구분 → 비인용 파싱 회귀  → gate g8, course ⑩ (관문 파서 m6a, course 파일 열거 m6b)
#   m7 동기화 확인 없이 stamp      → course ⑪
#   m8 알림 종료상태 누출          → diary s8, course ⑫
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
BASE=$(mktemp -d)
trap 'rm -rf "$BASE"' EXIT
PASS=0; FAILED=0
ok() { PASS=$((PASS + 1)); printf 'PASS %s\n' "$1"; }
no() { FAILED=$((FAILED + 1)); printf 'FAIL %s\n' "$1"; }

mkmut() { mkdir -p "$BASE/$1"; cp -R "$ROOT/tools" "$BASE/$1/tools"; cp "$ROOT/.gitignore" "$BASE/$1/.gitignore"; }

patch1() { python3 - "$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:4]
s = open(p, encoding="utf-8").read()
assert old in s, "patch anchor not found in %s: %r" % (p, old[:60])
open(p, "w", encoding="utf-8").write(s.replace(old, new, 1))
PY
}
patch_all() { python3 - "$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:4]
s = open(p, encoding="utf-8").read()
assert old in s, "patch anchor not found in %s: %r" % (p, old[:60])
open(p, "w", encoding="utf-8").write(s.replace(old, new))
PY
}

run_gate()   { bash "$ROOT/tests/gate/run.sh" "$BASE/$1" >"$BASE/$1.gate.log" 2>&1; }
run_diary()  { env PUBLISH_SH="$BASE/$1/tools/publish.sh" TOOLS_SRC="$BASE/$1/tools" \
                 GITIGNORE_SRC="$BASE/$1/.gitignore" \
                 bash "$ROOT/tests/diary/run.sh" >"$BASE/$1.diary.log" 2>&1; }
run_course() { bash "$ROOT/tests/course/run.sh" "$BASE/$1" >"$BASE/$1.course.log" 2>&1; }

# 기대 FAIL 패턴이 로그에 전부 있으면 변이가 잡힌 것.
expect_fails() {
  local name=$1 log=$2 pat; shift 2
  if [ ! -s "$log" ]; then no "$name (로그 없음)"; return; fi
  for pat in "$@"; do
    grep -qF "FAIL" "$log" && grep -qF "$pat" "$log" || { no "$name (기대 미일치: $pat)"; return; }
  done
  ok "$name"
}

# m1: 새로 공개되는 blob의 내용 스캔을 건너뛴다.
mkmut m1
patch1 "$BASE/m1/tools/push_gate.py" "    if blob_paths:" "    if False:"
run_gate m1;   expect_fails "m1 blob 스캔 생략 → gate" "$BASE/m1.gate.log" "g4 " "g6 "
run_course m1; expect_fails "m1 blob 스캔 생략 → course" "$BASE/m1.course.log" "⑬"

# m2: 허용 경로 집합 검사를 건너뛴다.
mkmut m2
patch1 "$BASE/m2/tools/push_gate.py" "if not ALLOWED_PATH.match(path):" "if False:"
run_gate m2;  expect_fails "m2 경로 검사 생략 → gate" "$BASE/m2.gate.log" "g3 " "g5 "
run_diary m2; expect_fails "m2 경로 검사 생략 → diary" "$BASE/m2.diary.log" "s7 "

# m3: 커밋 전 인덱스가 승인 목록과 같은지 대조하지 않는다.
mkmut m3
patch1 "$BASE/m3/tools/publish.sh" 'if [ -n "$extra" ] || [ -n "$miss" ]; then' 'if false; then'
run_diary m3; expect_fails "m3 인덱스 대조 생략 → diary" "$BASE/m3.diary.log" "s10 "

# m4: 빌드 결과물 스캔을 건너뛴다.
mkmut m4
patch1 "$BASE/m4/tools/publish.sh" 'out=$(python3 tools/scan.py posts/*.html index.html); rc=$?' 'rc=0'
run_diary m4; expect_fails "m4 빌드 결과 스캔 생략 → diary" "$BASE/m4.diary.log" "s11 "

# m5: 스캐너의 오류 종료(2·3)를 검출(1)로 취급한다.
mkmut m5
patch_all "$BASE/m5/tools/scan.py" "sys.exit(2)" "sys.exit(1)"
patch_all "$BASE/m5/tools/scan.py" "sys.exit(3)" "sys.exit(1)"
run_diary m5; expect_fails "m5 오류→검출 취급 → diary" "$BASE/m5.diary.log" "s12 "

# m6: -z/NUL 파싱을 일반 raw 출력 + 탭·따옴표 무시 파싱으로 되돌린다.
mkmut m6
patch1 "$BASE/m6/tools/push_gate.py" '"--no-renames", "-z", p, c)' '"--no-renames", p, c)'
patch1 "$BASE/m6/tools/push_gate.py" \
'                recs = out.split(b"\x00")
                i = 0
                while i < len(recs):
                    meta, path = recs[i], recs[i + 1] if i + 1 < len(recs) else b""
                    if not meta.startswith(b":"):
                        break
                    # --no-renames 이므로 경로는 하나. dst blob은 마지막 sha.
                    fields = meta.split()
                    changes[(os.fsdecode(path), fields[-2].decode())] = None
                    i += 2' \
'                for line in out.splitlines():
                    meta, _, path = line.rpartition(b"\t")
                    if not meta.startswith(b":"):
                        continue
                    fields = meta.split()
                    changes[(os.fsdecode(path), fields[-2].decode())] = None'
run_gate m6;   expect_fails "m6 NUL 파싱 회귀 → gate" "$BASE/m6.gate.log" "g8 "
run_course m6; expect_fails "m6 NUL 파싱 회귀 → course" "$BASE/m6.course.log" "⑩"

# m6b: publish_course.sh의 find -print0 읽기를 공백 분리로 되돌린다.
mkmut m6b
patch1 "$BASE/m6b/tools/publish_course.sh" \
'files=()
while IFS= read -r -d '"'"''"'"' f; do files+=("$f"); done < <(find course -type f -print0)' \
'files=()
for f in $(find course -type f); do files+=("$f"); done'
run_course m6b; expect_fails "m6b 파일 열거 공백 분리 회귀 → course" "$BASE/m6b.course.log" "⑩"

# m7: HEAD==origin/main(SYNC) 확인 없이 무변경 stamp를 갱신한다.
mkmut m7
patch1 "$BASE/m7/tools/publish_course.sh" 'if [ $grc -eq 0 ] && [ "$gate_out" = "SYNC" ]; then' 'if [ $grc -ne 2 ]; then'
run_course m7; expect_fails "m7 동기화 확인 생략 → course" "$BASE/m7.course.log" "⑪"

# m8: 알림의 종료 상태가 발행 결과로 새어 나간다.
mkmut m8a
patch1 "$BASE/m8a/tools/publish.sh" '>/dev/null || true' '>/dev/null'
patch1 "$BASE/m8a/tools/publish.sh" '  exit 1
fi
exit 0' '  exit 1
fi'
run_diary m8a; expect_fails "m8 알림 상태 누출 → diary" "$BASE/m8a.diary.log" "s8 "
mkmut m8b
patch1 "$BASE/m8b/tools/publish_course.sh" '  notify "형님, AI 엔지니어링 학습 과정 새 차수를 발행했습니다. https://starceas.github.io/daily-gajae/course/"
  exit 0' '  notify "형님, AI 엔지니어링 학습 과정 새 차수를 발행했습니다. https://starceas.github.io/daily-gajae/course/"'
run_course m8b; expect_fails "m8 알림 상태 누출 → course" "$BASE/m8b.course.log" "⑫"

echo "== $PASS passed, $FAILED failed =="
echo "(변이 로그는 트랩으로 정리됨. 재현: 이 스크립트의 mkmut·patch를 참조)"
[ "$FAILED" -eq 0 ]
