"""Deterministic cleanup for translated legal Markdown."""
from __future__ import annotations

import re


def sanitize_translated_markdown(text: str) -> str:
    """Clean formatting without rewriting or interpreting legal content."""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    cleaned = _remove_adjacent_duplicate_blocks(cleaned)
    cleaned = _remove_adjacent_duplicate_html_rows(cleaned)
    cleaned = _repair_markdown_tables(cleaned)
    cleaned = re.sub(r"\n*(<table\b)", r"\n\n\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(</table>)\n*", r"\1\n\n", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _normalised_block(block: str) -> str:
    value = re.sub(r"\s+", " ", block).strip().casefold()
    return re.sub(r"^#{1,6}\s*", "", value)


def _remove_adjacent_duplicate_blocks(text: str) -> str:
    output: list[str] = []
    previous = ""
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        key = _normalised_block(block)
        if key and key == previous:
            continue
        output.append(block)
        previous = key
    return "\n\n".join(output)


def _remove_adjacent_duplicate_html_rows(text: str) -> str:
    row_pattern = re.compile(r"(<tr\b[^>]*>.*?</tr>)", re.IGNORECASE | re.DOTALL)
    parts = row_pattern.split(text)
    output: list[str] = []
    previous_row = ""
    for part in parts:
        if row_pattern.fullmatch(part):
            key = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", part)).strip().casefold()
            if key and key == previous_row:
                continue
            previous_row = key
        elif part.strip():
            previous_row = ""
        output.append(part)
    return "".join(output)


def _is_pipe_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _is_separator_row(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _repair_markdown_tables(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        if not _is_pipe_row(lines[index]):
            output.append(lines[index])
            index += 1
            continue
        end = index
        while end < len(lines) and _is_pipe_row(lines[end]):
            end += 1
        table = lines[index:end]
        if len(table) >= 2:
            width = len(table[0].strip().strip("|").split("|"))
            if not _is_separator_row(table[1]):
                table.insert(1, "| " + " | ".join(["---"] * width) + " |")
            repaired: list[str] = []
            for row in table:
                cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
                cells = (cells + [""] * width)[:width]
                repaired.append("| " + " | ".join(cells) + " |")
            table = repaired
        output.extend(table)
        index = end
    return "\n".join(output)
