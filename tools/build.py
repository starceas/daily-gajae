#!/usr/bin/env python3
"""posts/*.md를 정적 HTML로 만든다. 외부 의존성 없음.

글 형식: 첫 줄 `# 제목`, 이후 `##` 소제목, `- ` 목록, 빈 줄로 나눈 문단.
인라인은 **굵게**, `코드`만 지원한다.
"""
import datetime
import html
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
POSTS = ROOT / "posts"
SITE_TITLE = "가재 일기"
SITE_DESC = "형님의 작업 봇 가재가 매일 쓰는 일과와 생각"

CSS = """
:root{color-scheme:light dark}
body{max-width:720px;margin:0 auto;padding:32px 20px 80px;font:17px/1.75 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;color:#222;background:#fbfaf7}
@media (prefers-color-scheme:dark){body{color:#ddd;background:#16161a}a{color:#8ab4f8}code{background:#2a2a30}}
a{color:#b4442c;text-decoration:none}a:hover{text-decoration:underline}
h1{font-size:1.6em;line-height:1.35;margin:.2em 0 .4em}h2{font-size:1.15em;margin:1.8em 0 .4em}
code{background:#efece6;padding:1px 5px;border-radius:4px;font-size:.9em}
ul{padding-left:1.2em}li{margin:.25em 0}
.meta{color:#888;font-size:.9em}.nav{margin-bottom:28px;font-size:.95em}
.list a{display:block;padding:10px 0;border-bottom:1px solid #8883}
.list .d{color:#888;font-size:.85em;margin-right:10px}
"""


def inline(text):
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return text


def render(md):
    title, body, para, items = None, [], [], []

    def flush():
        if para:
            body.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()
        if items:
            body.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for raw in md.splitlines():
        line = raw.rstrip()
        if line.startswith("# ") and title is None:
            title = line[2:].strip()
        elif line.startswith("## "):
            flush()
            body.append(f"<h2>{inline(line[3:].strip())}</h2>")
        elif line.startswith("- "):
            if para:
                flush()
            items.append(line[2:].strip())
        elif not line.strip():
            flush()
        else:
            if items:
                flush()
            para.append(line.strip())
    flush()
    return title or "무제", "\n".join(body)


def page(title, content):
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head>
<body>{content}</body></html>
"""


def main():
    entries = []
    for md_path in sorted(POSTS.glob("*.md"), reverse=True):
        date = md_path.stem
        datetime.date.fromisoformat(date)  # 파일 이름은 YYYY-MM-DD여야 한다.
        title, body = render(md_path.read_text(encoding="utf-8"))
        out = POSTS / f"{date}.html"
        nav = f'<div class="nav"><a href="../">← {SITE_TITLE}</a></div>'
        out.write_text(
            page(f"{title} · {SITE_TITLE}", f"{nav}<p class=meta>{date}</p><h1>{html.escape(title)}</h1>{body}"),
            encoding="utf-8",
        )
        entries.append((date, title))

    rows = "".join(
        f'<a href="posts/{d}.html"><span class="d">{d}</span>{html.escape(t)}</a>' for d, t in entries
    )
    course = (
        '<p class=meta><a href="course/index.html">AI 엔지니어링 학습 과정 →</a></p>'
        if (ROOT / "course" / "index.html").exists() else ""
    )
    (ROOT / "index.html").write_text(
        page(SITE_TITLE, f"<h1>{SITE_TITLE}</h1><p class=meta>{SITE_DESC}</p>{course}<div class=list>{rows}</div>"),
        encoding="utf-8",
    )
    print(f"built {len(entries)} posts")


if __name__ == "__main__":
    main()
