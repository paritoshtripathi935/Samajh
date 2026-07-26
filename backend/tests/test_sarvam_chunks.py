from app.services.sarvam import CHAT_TRANSLATION_CHUNK_SIZE, english_source_chunks


def test_english_generation_chunks_use_page_boundaries():
    pages = [
        {"page_num": 1, "blocks": [{"reading_order": 1, "text": "पहला पेज", "layout_tag": "paragraph"}]},
        {"page_num": 2, "blocks": [{"reading_order": 1, "text": "दूसरा पेज", "layout_tag": "paragraph"}]},
    ]

    chunks = english_source_chunks(raw_text="", pages=pages)

    assert len(chunks) == 1
    assert "[Page 1]" in chunks[0]
    assert "[Page 2]" in chunks[0]
    assert chunks[0].index("[Page 1]") < chunks[0].index("[Page 2]")
    assert len(chunks[0]) <= CHAT_TRANSLATION_CHUNK_SIZE
