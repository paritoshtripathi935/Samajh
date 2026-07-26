from app.api import routes
from fastapi.responses import Response
from fastapi import UploadFile
from io import BytesIO


def _processed():
    return routes.ProcessDocumentOut(
        raw_extraction="Section 420 IPC",
        eng_extraction="Section 420 IPC",
        ipc_sections=[routes.IpcSectionOut(ipc="420", summary="Cheating")],
        filing_type="chargesheet",
    )


def test_persist_process_uploads_pdf_and_saves_file_ref(monkeypatch):
    calls = {}

    monkeypatch.setattr(routes.repo, "insert_document", lambda **kwargs: {"id": "doc-1"})
    monkeypatch.setattr(
        routes.repo,
        "upload_document_file",
        lambda **kwargs: (calls.update(upload=kwargs) or "doc-1/filing.pdf"),
    )
    monkeypatch.setattr(
        routes.repo,
        "update_document",
        lambda document_id, **fields: calls.update(update=(document_id, fields)) or {},
    )
    monkeypatch.setattr(routes.repo, "insert_digitization", lambda **kwargs: {})
    monkeypatch.setattr(routes.repo, "insert_translation", lambda **kwargs: {})
    monkeypatch.setattr(routes.repo, "insert_extraction", lambda **kwargs: {})

    document_id = routes._persist_process(
        file_name="filing.pdf",
        language="en-IN",
        processed=_processed(),
        original_pdf=b"%PDF-test",
    )

    assert document_id == "doc-1"
    assert calls["upload"]["content"] == b"%PDF-test"
    assert calls["update"] == ("doc-1", {"file_ref": "doc-1/filing.pdf"})


def test_persist_process_keeps_extraction_when_pdf_upload_fails(monkeypatch):
    digitization = {}

    monkeypatch.setattr(routes.repo, "insert_document", lambda **kwargs: {"id": "doc-2"})
    monkeypatch.setattr(
        routes.repo,
        "upload_document_file",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("bucket unavailable")),
    )
    monkeypatch.setattr(
        routes.repo,
        "insert_digitization",
        lambda **kwargs: digitization.update(kwargs) or {},
    )
    monkeypatch.setattr(routes.repo, "insert_translation", lambda **kwargs: {})
    monkeypatch.setattr(routes.repo, "insert_extraction", lambda **kwargs: {})

    document_id = routes._persist_process(
        file_name="filing.pdf",
        language="en-IN",
        processed=_processed(),
        original_pdf=b"%PDF-test",
    )

    assert document_id == "doc-2"
    assert digitization["document_id"] == "doc-2"


def test_get_document_pdf_streams_private_storage_object(monkeypatch):
    monkeypatch.setattr(
        routes.repo,
        "get_document",
        lambda document_id: {
            "id": document_id,
            "file_name": "filing.pdf",
            "file_ref": f"{document_id}/filing.pdf",
        },
    )
    monkeypatch.setattr(routes.repo, "download_document_file", lambda file_ref: b"%PDF-test")

    response = routes.get_document_pdf("doc-3")

    assert isinstance(response, Response)
    assert response.body == b"%PDF-test"
    assert response.media_type == "application/pdf"
    assert response.headers["content-disposition"] == 'inline; filename="filing.pdf"'


def test_list_documents_returns_dashboard_rows(monkeypatch):
    monkeypatch.setattr(
        routes.repo,
        "list_documents",
        lambda limit: [
            {
                "id": "doc-4",
                "file_name": "filing.pdf",
                "filing_type": "chargesheet",
                "source_language": "hi-IN",
                "page_count": 5,
                "status": "ready",
                "file_ref": "doc-4/filing.pdf",
                "created_at": "2026-07-26T09:00:00Z",
                "updated_at": "2026-07-26T09:01:00Z",
            }
        ],
    )

    response = routes.list_documents(limit=500)

    assert len(response.documents) == 1
    assert response.documents[0].id == "doc-4"
    assert response.documents[0].status == "ready"


def test_mark_document_ingested_updates_statuses(monkeypatch):
    calls = {}

    monkeypatch.setattr(routes.repo, "get_document", lambda document_id: {"id": document_id})
    monkeypatch.setattr(
        routes.repo,
        "update_document_ingestion_status",
        lambda **kwargs: calls.update(kwargs) or {},
    )

    response = routes.mark_document_ingested("doc-5")

    assert response.document_id == "doc-5"
    assert response.vector_ingestion_status == "ready"
    assert response.structured_ingestion_status == "ready"
    assert calls["document_id"] == "doc-5"
    assert calls["vector_status"] == "ready"


def test_chat_with_document_persists_user_and_assistant(monkeypatch):
    calls = {"messages": []}

    monkeypatch.setattr(
        routes.repo,
        "get_document_bundle",
        lambda document_id: {
            "document": {"id": document_id, "file_name": "filing.pdf"},
            "translations": [{"translated_text": "English filing context with Section 420 IPC."}],
            "digitizations": [],
        },
    )
    monkeypatch.setattr(
        routes.repo,
        "create_document_conversation",
        lambda **kwargs: {"id": "convo-1", "document_id": kwargs["document_id"], "title": kwargs["title"]},
    )
    monkeypatch.setattr(routes.repo, "list_document_chat_messages", lambda conversation_id, limit=50: [])
    monkeypatch.setattr(
        routes.repo,
        "insert_document_chat_message",
        lambda **kwargs: calls["messages"].append(kwargs) or {"id": f"msg-{len(calls['messages'])}", **kwargs},
    )
    monkeypatch.setattr(routes, "_answer_document_question", lambda **kwargs: "Grounded answer")

    response = routes.chat_with_document(
        "doc-6",
        routes.DocumentChatIn(message="What is alleged?"),
    )

    assert response.conversation_id == "convo-1"
    assert response.answer == "Grounded answer"
    assert calls["messages"][0]["role"] == "user"
    assert calls["messages"][1]["role"] == "assistant"


def test_processing_start_returns_id_before_background_ocr(monkeypatch):
    calls = {}

    class Tasks:
        def add_task(self, function, *args):
            calls["task"] = (function, args)

    monkeypatch.setattr(
        routes.repo,
        "insert_document",
        lambda **kwargs: calls.update(insert=kwargs) or {"id": "doc-fast"},
    )
    monkeypatch.setattr(
        routes.repo,
        "upload_document_file",
        lambda **kwargs: calls.update(upload=kwargs) or "doc-fast/filing.pdf",
    )
    monkeypatch.setattr(
        routes.repo,
        "update_document",
        lambda document_id, **fields: calls.update(update=(document_id, fields)) or {},
    )

    result = routes.start_document_processing(
        Tasks(),
        UploadFile(filename="filing.pdf", file=BytesIO(b"%PDF-test")),
        "hi-IN",
    )

    assert result.document_id == "doc-fast"
    assert calls["insert"]["status"] == "uploaded"
    assert calls["task"][0] is routes._process_document_background
