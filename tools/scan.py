#!/usr/bin/env python3
"""공개 전 개인정보 검사. 걸리면 줄 번호와 사유를 찍고 종료 코드 1.

차단어 목록(실명 등)은 저장소 밖 DIARY_BLOCKLIST 파일에 둔다. 저장소에 실명을 남기지 않기 위해서다.
"""
import os
import re
import sys

BLOCKLIST = os.environ.get(
    "DIARY_BLOCKLIST", os.path.expanduser("~/gajaeway/state/diary/blocklist.txt")
)

PATTERNS = [
    ("절대 경로", re.compile(r"/(Users|home|Volumes|private|tmp|var)/")),
    ("홈 경로", re.compile(r"(^|[\s`(])~/")),
    ("Windows 경로", re.compile(r"[A-Za-z]:\\")),
    ("이메일", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("전화번호", re.compile(r"01[016789][-. ]?\d{3,4}[-. ]?\d{4}")),
    ("긴 숫자(학번·ID 등)", re.compile(r"\d{7,}")),
    ("주민번호 형식", re.compile(r"\d{6}-[1-4]\d{6}")),
    ("토큰 형식", re.compile(r"(sk-|ghp_|gho_|xox[bp]-|AKIA)[A-Za-z0-9_-]{8,}")),
    ("Discord 멘션", re.compile(r"<@!?\d+>")),
    ("주소", re.compile(r"[가-힣]+(시|군|구)\s?[가-힣0-9]+(로|길|동|읍|면)\s?\d+")),
]


def load_blocklist():
    terms = []
    if not os.path.exists(BLOCKLIST):
        print(f"차단어 목록 없음: {BLOCKLIST}", file=sys.stderr)
        sys.exit(2)
    with open(BLOCKLIST, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                terms.append(line)
    return terms


def scan(path, terms):
    hits = []
    with open(path, encoding="utf-8") as f:
        for no, line in enumerate(f, 1):
            for label, pat in PATTERNS:
                if pat.search(line):
                    hits.append((no, label))
            low = line.lower()
            for t in terms:
                if t.lower() in low:
                    hits.append((no, "차단어"))
    return hits


def main():
    terms = load_blocklist()
    bad = 0
    for path in sys.argv[1:]:
        for no, label in scan(path, terms):
            # 차단어 자체는 찍지 않는다(로그에 실명이 남지 않게).
            print(f"{os.path.basename(path)}:{no}: {label}")
            bad += 1
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
