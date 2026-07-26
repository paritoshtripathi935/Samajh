from app.api import routes
from fastapi.responses import Response


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
