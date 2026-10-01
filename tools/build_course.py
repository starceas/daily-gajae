#!/usr/bin/env python3
"""AI 엔지니어링 학습 과정을 사이트의 course/ 아래 정적 HTML로 만든다.

원본은 합의(독립 검토 최종 PASS·DONE)가 끝난 학습 과정 폴더다. 공개 대상은
README·course·labs·templates·research와 실습 kit 원본이며, 작업 기록(work·review·
devlog·ref·REPORT)은 싣지 않는다. 원본의 로컬 절대 경로는 `<학습 폴더>`로 바꾼다.

실행: uv run --with markdown python tools/build_course.py <원본 폴더>
"""
import html
import pathlib
import re
import shutil
import sys

import markdown

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "course"
TITLE = "AI 엔지니어링 학습 과정"
DOC_DIRS = ("course", "labs", "templates", "research")
SKIP_PARTS = {"__pycache__", "_work", ".DS_Store"}
TEXT_SUFFIXES = {".md", ".py", ".json", ".txt"}
DIR_LINKS = set()

sys.path.insert(0, str(ROOT / "tools"))
from build import CSS, page  # noqa: E402

EXTRA_CSS = """
table{border-collapse:collapse;width:100%;font-size:.92em;margin:1em 0;display:block;overflow-x:auto}
th,td{border:1px solid #8885;padding:6px 8px;vertical-align:top}
pre{background:#efece6;padding:12px;border-radius:6px;overflow-x:auto;font-size:.88em;line-height:1.5}
pre code{background:none;padding:0}
@media (prefers-color-scheme:dark){pre{background:#2a2a30}}
"""


def publishable(src):
    files = [src / "README.md"]
    for d in DOC_DIRS:
        for p in sorted((src / d).rglob("*")):
            if p.is_file() and not (SKIP_PARTS & set(p.relative_to(src).parts)) and p.suffix in TEXT_SUFFIXES:
                files.append(p)
    return files


def scrub(text, src):
    return text.replace(str(src), "<학습 폴더>")


def md_to_html(text):
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    # 문서 간 링크는 만든 HTML을 가리키게 한다. 원본 저장 위치를 드러내는 작업 보고 링크는 뺀다.
    body = re.sub(r'href="([^":#]+)\.md(#[^"]*)?"', r'href="\1.html\2"', body)
    body = re.sub(r'href="((?:[^":#]*/)?)README\.html', r'href="\1index.html', body)
    body = re.sub(r'<a href="(\.\./)*REPORT\.html">([^<]*)</a>', r"\2", body)
    return body


def link_dirs(body, dest_dir):
    """Pages는 폴더 목록을 보여 주지 않는다. 폴더 링크는 그 폴더의 목록 페이지로 보낸다."""

    def fix(m):
        target = (dest_dir / m.group(1)).resolve()
        DIR_LINKS.add(target)
        return f'href="{m.group(1)}index.html"'

    return re.sub(r'href="([^":#]+/)"', fix, body)


def write_dir_index(d):
    """README가 없는 실습 폴더에 파일 목록 페이지를 만든다."""
    if (d / "index.html").exists():
        return
    rows = "".join(
        f'<a href="{html.escape(p.name)}{"/index.html" if p.is_dir() else ""}">{html.escape(p.name)}</a>'
        for p in sorted(d.iterdir()) if not p.name.endswith(".html"))
    name = d.relative_to(OUT).as_posix()
    up = "../" * len(d.relative_to(OUT).parts)
    nav = f'<div class="nav"><a href="{up}index.html">← {TITLE}</a></div>'
    (d / "index.html").write_text(
        page(f"{name} · {TITLE}", f"{nav}<h1>{html.escape(name)}/</h1><div class=list>{rows}</div>"),
        encoding="utf-8")
    for p in d.iterdir():
        if p.is_dir():
            write_dir_index(p)


def main():
    src = pathlib.Path(sys.argv[1]).resolve()
    if not (src / "DONE").exists():
        sys.exit(f"합의 미완료(DONE 없음): {src.name}")
    if OUT.exists():
        shutil.rmtree(OUT)
    count = 0
    for p in publishable(src):
        rel = p.relative_to(src)
        text = scrub(p.read_text(encoding="utf-8"), src)
        if p.suffix == ".md":
            first = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), rel.stem)
            depth = len(rel.parts) - 1
            up = "../" * depth
            nav = f'<div class="nav"><a href="{up}index.html">← {TITLE}</a> · <a href="{up}../">가재 일기</a></div>'
            dest = OUT / rel.with_name("index.html" if rel.name == "README.md" else rel.stem + ".html")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(page(f"{first} · {TITLE}", nav + link_dirs(md_to_html(text), dest.parent)).replace(
                f"<style>{CSS}</style>", f"<style>{CSS}{EXTRA_CSS}</style>"), encoding="utf-8")
        # kit 원본과 문서 원본도 그대로 둬서 실습 파일을 받을 수 있게 한다.
        raw = OUT / rel
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(text, encoding="utf-8")
        count += 1
    for d in sorted(DIR_LINKS):
        if not d.is_dir():
            sys.exit(f"없는 폴더 링크: {d}")
        write_dir_index(d)
    print(f"built course {count} files")


if __name__ == "__main__":
    main()
