from app.services.translation_sanitizer import sanitize_translated_markdown


def test_removes_only_adjacent_duplicate_content():
    source = """## CNR NO.-123

## CNR NO.-123

1. Evidence recorded.

2. Evidence recorded."""

    cleaned = sanitize_translated_markdown(source)

    assert cleaned.count("CNR NO.-123") == 1
    assert "1. Evidence recorded." in cleaned
    assert "2. Evidence recorded." in cleaned


def test_repairs_markdown_table_separator_and_cell_width():
    source = """| Date | Event |
| 11.11.2022 | FIR lodged |
| 12.11.2022 |"""

    cleaned = sanitize_translated_markdown(source)

    assert "| --- | --- |" in cleaned
    assert "| 12.11.2022 |  |" in cleaned


def test_removes_adjacent_duplicate_html_rows():
    source = """<table><tbody>
<tr><td>1</td><td>Complaint</td></tr>
<tr><td>1</td><td>Complaint</td></tr>
</tbody></table>"""

    cleaned = sanitize_translated_markdown(source)

    assert cleaned.count("<tr>") == 1
    assert cleaned.startswith("<table>")
