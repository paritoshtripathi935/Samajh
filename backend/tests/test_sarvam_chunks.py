from app.services import sarvam
from app.services.sarvam import CHAT_TRANSLATION_CHUNK_SIZE, _sse_data_from_line, _stream_delta_content, english_source_chunks


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


def test_stream_parser_accepts_sse_without_space():
    assert _sse_data_from_line('data:{"choices":[{"delta":{"content":"Hi"}}]}').startswith('{"choices"')
    assert _stream_delta_content({"choices": [{"delta": {"content": "Hi"}}]}) == "Hi"
    assert _stream_delta_content({"choices": [{"delta": {"content": None, "reasoning_content": "hidden"}}]}) == ""


def test_latin_only_source_is_passed_through_without_translate_request(monkeypatch):
    monkeypatch.setattr(
        sarvam,
        "_client",
        lambda: (_ for _ in ()).throw(AssertionError("translate API should not be called")),
    )

    result = sarvam._translate_chunk(
        "Already English legal text.",
        source_language="en-IN",
        index=1,
        total=1,
    )

    assert result == "Already English legal text."


def test_devanagari_overrides_incorrect_english_source(monkeypatch):
    calls = {}

    class Text:
        def translate(self, **kwargs):
            calls.update(kwargs)
            return type("Response", (), {"translated_text": "Court judgment"})()

    monkeypatch.setattr(sarvam, "_client", lambda: type("Client", (), {"text": Text()})())

    result = sarvam._translate_chunk(
        "न्यायालय का निर्णय",
        source_language="en-IN",
        index=1,
        total=1,
    )

    assert result == "Court judgment"
    assert calls["source_language_code"] == "hi-IN"


def test_residual_hindi_receives_strict_english_cleanup(monkeypatch):
    class Text:
        def translate(self, **kwargs):
            return type("Response", (), {"translated_text": "Court निर्णय"})()

    monkeypatch.setattr(sarvam, "_client", lambda: type("Client", (), {"text": Text()})())
    monkeypatch.setattr(sarvam, "_english_chat_completion", lambda *args, **kwargs: "Court judgment")

    result = sarvam._translate_chunk(
        "न्यायालय निर्णय",
        source_language="hi-IN",
        index=1,
        total=1,
    )

    assert result == "Court judgment"
