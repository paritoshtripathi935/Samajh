from app.services.citations import extract_ipc_references


def test_extract_ipc_reference_variants():
    markdown = "Charges include u/s 420 IPC, Section 302 IPC, and IPC Section 376."

    refs = extract_ipc_references(markdown)

    assert [ref.section for ref in refs] == ["420", "302", "376"]
    assert [ref.raw_text for ref in refs] == [
        "u/s 420 IPC",
        "Section 302 IPC",
        "IPC Section 376",
    ]
    assert markdown[refs[0].start_offset : refs[0].end_offset] == "u/s 420 IPC"
