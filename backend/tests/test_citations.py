from app.services.citations import extract_ipc_references


def test_extract_ipc_reference_variants():
    markdown = "Charges include u/s 420 IPC, Section 302 IPC, and IPC Section 376."

    refs = extract_ipc_references(markdown)

    assert [ref.section for ref in refs] == ["420", "302", "376"]
    assert [ref.raw_text for ref in refs] == [
        "420",
        "302",
        "376",
    ]
    assert markdown[refs[0].start_offset : refs[0].end_offset] == "420"


def test_extracts_ipc_section_lists_without_accused_number_false_positive():
    markdown = (
        "M/s Example Private Limited (A-5) committed offences under "
        "Sections 420,467,468,471 read with 120-B of IPC."
    )

    refs = extract_ipc_references(markdown)

    assert [ref.section for ref in refs] == ["420", "467", "468", "471", "120B"]
    assert "5" not in [ref.section for ref in refs]
