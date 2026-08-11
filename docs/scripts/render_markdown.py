#!/usr/bin/env python3
"""Render a report Markdown file into a standalone page using the portal styles.

Deliberately small: the reports use headings, paragraphs, pipe tables, lists,
block quotes, fenced code and inline emphasis, and nothing else.  Keeping the
renderer here avoids a third-party dependency in a build that must stay
reproducible from a clean checkout.
"""
from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

INLINE_CODE = re.compile(r'`([^`]+)`')
# ``![caption](figures/name)`` with no file extension expands to the light and
# dark rendering of that figure; CSS shows whichever matches the viewer.
FIGURE = re.compile(r'^!\[([^\]]*)\]\(([^)\s]+?)(\.\w+)?\)$')
BOLD = re.compile(r'\*\*([^*]+)\*\*')
ITALIC = re.compile(r'(?<![*\w])\*([^*]+)\*(?!\*)')
LINK = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
ALLOWED_TAGS = re.compile(r'&lt;(/?)(sub|sup)&gt;')


def inline(text: str) -> str:
    text = html.escape(text)
    text = ALLOWED_TAGS.sub(r'<\1\2>', text)
    text = INLINE_CODE.sub(lambda m: f'<code>{m.group(1)}</code>', text)
    text = BOLD.sub(r'<strong>\1</strong>', text)
    text = ITALIC.sub(r'<em>\1</em>', text)
    text = LINK.sub(r'<a href="\2">\1</a>', text)
    return text


def is_separator(row: str) -> bool:
    cells = [cell.strip() for cell in row.strip().strip('|').split('|')]
    return bool(cells) and all(re.fullmatch(r':?-{2,}:?', cell) for cell in cells)


def split_row(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip('|').split('|')]


def render(markdown: str) -> str:
    lines = markdown.splitlines()
    out: list[str] = []
    index = 0
    list_open = False

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            out.append('</ul>')
            list_open = False

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith('```'):
            close_list()
            index += 1
            block: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith('```'):
                block.append(html.escape(lines[index]))
                index += 1
            index += 1
            out.append('<pre class="mono"><code>' + '\n'.join(block) + '</code></pre>')
            continue

        # Pipe table: a header row followed by a --- separator.
        if (stripped.startswith('|') and index + 1 < len(lines)
                and is_separator(lines[index + 1])):
            close_list()
            header = split_row(stripped)
            aligns = ['num' if cell.strip().endswith(':') else ''
                      for cell in split_row(lines[index + 1])]
            index += 2
            body: list[str] = []
            while index < len(lines) and lines[index].strip().startswith('|'):
                body.append(split_row(lines[index].strip()))
                index += 1
            head = ''.join(f'<th class="{cls}">{inline(cell)}</th>'
                           for cell, cls in zip(header, aligns))
            rows = ''.join(
                '<tr>' + ''.join(
                    f'<td class="{aligns[position] if position < len(aligns) else ""}">{inline(cell)}</td>'
                    for position, cell in enumerate(row)) + '</tr>'
                for row in body)
            out.append(f'<div class="table-scroll"><table class="data">'
                       f'<thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>')
            continue

        if not stripped:
            close_list()
            index += 1
            continue

        if stripped == '---':
            close_list()
            out.append('<hr>')
            index += 1
            continue

        figure = FIGURE.match(stripped)
        if figure:
            close_list()
            caption, path, extension = figure.groups()
            index += 1
            if extension:
                images = f'<img src="{html.escape(path + extension)}" alt="{inline(caption)}">'
            else:
                images = (
                    f'<img class="fig-light" src="{html.escape(path)}_light.png" '
                    f'alt="{inline(caption)}">'
                    f'<img class="fig-dark" src="{html.escape(path)}_dark.png" '
                    f'alt="{inline(caption)}">')
            out.append(f'<figure>{images}'
                       f'<figcaption>{inline(caption)}</figcaption></figure>')
            continue

        heading = re.match(r'(#{1,4})\s+(.*)', stripped)
        if heading:
            close_list()
            level = len(heading.group(1))
            out.append(f'<h{level}>{inline(heading.group(2))}</h{level}>')
            index += 1
            continue

        if stripped.startswith('> '):
            close_list()
            quote: list[str] = []
            while index < len(lines) and lines[index].strip().startswith('>'):
                quote.append(lines[index].strip().lstrip('>').strip())
                index += 1
            out.append(f'<div class="callout">{inline(" ".join(quote))}</div>')
            continue

        item = re.match(r'(?:[-*]|\d+\.)\s+(.*)', stripped)
        if item:
            if not list_open:
                out.append('<ul class="clean">')
                list_open = True
            text = [item.group(1)]
            index += 1
            # Continuation lines of the same bullet are indented.
            while (index < len(lines) and lines[index].startswith('   ')
                   and lines[index].strip()
                   and not re.match(r'(?:[-*]|\d+\.)\s', lines[index].strip())):
                text.append(lines[index].strip())
                index += 1
            out.append(f'<li>{inline(" ".join(text))}</li>')
            continue

        close_list()
        paragraph = [stripped]
        index += 1
        while index < len(lines) and lines[index].strip() and not re.match(
                r'^(#{1,4}\s|[-*]\s|\d+\.\s|\||>|```|---$)', lines[index].strip()):
            paragraph.append(lines[index].strip())
            index += 1
        out.append(f'<p>{inline(" ".join(paragraph))}</p>')

    close_list()
    return '\n'.join(out)


PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="assets/portal.css?v=20260811b">
<style>
  main {{ max-width: 82ch; }}
  main h1 {{ font-size: 1.7rem; margin-top: .2em; }}
  main h2 {{ margin-top: 1.9em; padding-top: .3em; border-top: 1px solid var(--border); }}
  main h3 {{ margin-top: 1.4em; }}
  main table.data td, main table.data th {{ white-space: normal; }}
  main table.data td.num, main table.data th.num {{ white-space: nowrap; }}
  main hr {{ border: 0; border-top: 1px solid var(--border); margin: 2em 0; }}
  main pre.mono {{ background: var(--surface-2); padding: .85rem 1rem; border-radius: 9px;
                   overflow-x: auto; font-size: .8rem; line-height: 1.5; }}
  main figure {{ margin: 1.9em 0; }}
  main figure img {{ width: 100%; max-width: 100%; height: auto; border-radius: 8px;
                     border: 1px solid var(--border); }}
  main figcaption {{ margin-top: .6rem; font-size: .84rem; color: var(--text-muted);
                     line-height: 1.5; }}
  .fig-dark {{ display: none; }}
  @media (prefers-color-scheme: dark) {{
    .fig-light {{ display: none; }} .fig-dark {{ display: block; }}
  }}
  :root[data-theme="light"] .fig-light {{ display: block; }}
  :root[data-theme="light"] .fig-dark {{ display: none; }}
  :root[data-theme="dark"] .fig-light {{ display: none; }}
  :root[data-theme="dark"] .fig-dark {{ display: block; }}
</style>
</head>
<body>
<header class="masthead"><div class="masthead-inner">
  <h1 class="brand">Russian Soil Observatory<small>{subtitle}</small></h1>
  <span class="masthead-spacer"></span>
  <a class="pill" href="index.html">← {back}</a>
</div></header>
<main>
{body}
</main>
<footer><div class="inner">Russian Soil Observatory · CC BY 4.0</div></footer>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--title', default='Научный анализ базы')
    parser.add_argument('--subtitle', default='научный анализ базы данных')
    parser.add_argument('--back', default='к геопорталу')
    args = parser.parse_args()

    body = render(args.input.read_text(encoding='utf-8'))
    args.output.write_text(PAGE.format(
        title=html.escape(args.title), subtitle=html.escape(args.subtitle),
        back=html.escape(args.back), body=body), encoding='utf-8')
    print(f'{args.input} -> {args.output} ({args.output.stat().st_size} bytes)')


if __name__ == '__main__':
    main()
