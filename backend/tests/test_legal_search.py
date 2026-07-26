from app.services import legal_search, sarvam
from app.api import routes


def test_sarvam_search_items_are_parsed_and_validated(monkeypatch):
    monkeypatch.setattr(
        sarvam,
        "chat",
        lambda **kwargs: """```json
        [
          {
            "title": "Dishonest inducement",
            "query": "dishonest inducement delivery of property cheating Supreme Court India",
            "rationale": "Tests the required causal link between inducement and delivery.",
            "kind": "precedent"
          }
        ]
        ```""",
    )

    items = sarvam.generate_legal_search_items(
        section_title="Cheating allegation",
        section_content="The accused allegedly induced payment using forged purchase orders.",
        filing_type="chargesheet",
    )

    assert items == [
        {
            "title": "Dishonest inducement",
            "query": "dishonest inducement delivery of property cheating Supreme Court India",
            "rationale": "Tests the required causal link between inducement and delivery.",
            "kind": "precedent",
        }
    ]


def test_sarvam_search_items_retry_and_accept_wrapped_items(monkeypatch):
    responses = iter(
        [
            "",
            """Here are the results:
            {"items": [{
              "title": "Consent and force",
              "query": "assault woman criminal force intent Supreme Court India",
              "rationale": "Finds the governing test for criminal force and intent.",
              "kind": "precedent"
            }]}""",
        ]
    )
    models = []

    def fake_chat(**kwargs):
        models.append(kwargs["model"])
        return next(responses)

    monkeypatch.setattr(sarvam, "chat", fake_chat)
    items = sarvam.generate_legal_search_items(
        section_title="IPC 354 analysis",
        section_content="The allegation concerns assault and use of criminal force against a woman.",
    )

    assert models == [sarvam.RESEARCH_SEARCH_MODEL, sarvam.CHAT_MODEL]
    assert items[0]["title"] == "Consent and force"


def test_sarvam_search_items_fall_back_to_content_grounded_queries(monkeypatch):
    monkeypatch.setattr(sarvam, "chat", lambda **kwargs: "")

    items = sarvam.generate_legal_search_items(
        section_title="IPC 354 analysis",
        section_content="The allegation concerns assault and criminal force against a woman.",
    )

    assert len(items) == 3
    assert all("assault" in item["query"] for item in items)
    assert all(item["query"] != "IPC 354" for item in items)


def test_ipc_summary_returns_chat_content(monkeypatch):
    monkeypatch.setattr(sarvam, "chat", lambda **kwargs: "Section 354 concerns assault on a woman.")

    summary = sarvam.summarize_ipc_section("354")

    assert summary == "Section 354 concerns assault on a woman."


def test_ipc_summarization_tolerates_empty_model_response(monkeypatch):
    monkeypatch.setattr(routes, "extract_ipc_references", lambda text: [type("Ref", (), {"section": "354"})()])
    monkeypatch.setattr(routes.sarvam, "summarize_ipc_section", lambda section: None)

    sections = routes._summarize_ipc_sections("Section 354 IPC")

    assert sections[0].ipc == "354"
    assert sections[0].summary == ""


def test_generated_items_receive_balanced_source_results(monkeypatch):
    monkeypatch.setattr(
        legal_search,
        "_search_one",
        lambda query: [
            {
                "title": "Authority",
                "url": "https://indiankanoon.org/doc/1/",
                "snippet": "Relevant holding",
                "source": "indian_kanoon",
                "doc_type": "judgment",
                "jurisdiction": "Supreme Court of India",
                "citation": None,
            }
        ],
    )
    generated = [
        {
            "title": "Dishonest inducement",
            "query": "dishonest inducement cheating",
            "rationale": "Find the governing test.",
            "kind": "precedent",
        }
    ]

    enriched = legal_search.search_generated_items(generated)

    assert enriched[0]["query"] == "dishonest inducement cheating"
    assert enriched[0]["results"][0]["source"] == "indian_kanoon"
