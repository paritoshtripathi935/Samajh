from app.services.sarvam import TRANSLATE_CHUNK_SIZE, _chunk_text


def test_translation_chunks_stay_under_sarvam_limit():
    text = "\n\n".join(["a" * 500, "b" * 1900, "c" * 3000])

    chunks = _chunk_text(text, max_chars=TRANSLATE_CHUNK_SIZE)

    assert chunks
    assert all(len(chunk) <= TRANSLATE_CHUNK_SIZE for chunk in chunks)
    assert TRANSLATE_CHUNK_SIZE < 2000
