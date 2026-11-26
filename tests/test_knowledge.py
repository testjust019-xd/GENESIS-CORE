from genesis_core.knowledge import KnowledgeError, KnowledgeStore
from genesis_core.state import StateStore


def test_ingest_chunks_and_search_returns_citations(tmp_path):
    store = KnowledgeStore(StateStore(tmp_path / "genesis.db"))
    text = ("GENESIS is a local-first agent framework. It stores knowledge locally. " * 55)

    document = store.ingest_text(
        "Architecture notes", text, "docs/architecture.md",
        {"category": "design"},
    )

    assert document["chunk_count"] > 1
    results = store.search("local-first agent framework")
    assert results
    assert results[0]["citation"]["title"] == "Architecture notes"
    assert results[0]["citation"]["source"] == "docs/architecture.md"
    assert results[0]["citation"]["chunk"] >= 1


def test_duplicate_content_is_not_indexed_twice(tmp_path):
    store = KnowledgeStore(StateStore(tmp_path / "genesis.db"))

    first = store.ingest_text("First title", "Unique local knowledge content.")
    duplicate = store.ingest_text("Other title", "Unique local knowledge content.")

    assert duplicate["duplicate"] is True
    assert duplicate["id"] == first["id"]
    assert len(store.list_documents()) == 1


def test_delete_document_removes_its_search_results(tmp_path):
    store = KnowledgeStore(StateStore(tmp_path / "genesis.db"))
    document = store.ingest_text("Temporary", "Quasar knowledge should be removable.")

    store.delete_document(document["id"])

    assert store.search("Quasar") == []
    assert store.list_documents() == []


def test_empty_and_oversized_documents_are_rejected(tmp_path):
    store = KnowledgeStore(StateStore(tmp_path / "genesis.db"))

    try:
        store.ingest_text("Empty", "  ")
        assert False, "Expected empty document to be rejected"
    except KnowledgeError:
        pass

    try:
        store.ingest_text("Large", "x" * (store.MAX_DOCUMENT_CHARS + 1))
        assert False, "Expected oversized document to be rejected"
    except KnowledgeError:
        pass


def test_import_file_accepts_markdown_and_rejects_other_formats(tmp_path):
    store = KnowledgeStore(StateStore(tmp_path / "genesis.db"))
    markdown = tmp_path / "guide.md"
    markdown.write_text("# Local setup\nInstall Ollama.", encoding="utf-8")

    result = store.ingest_file(markdown)

    assert result["title"] == "guide.md"
    assert result["metadata"]["format"] == ".md"

    binaryish = tmp_path / "archive.pdf"
    binaryish.write_text("not a real pdf", encoding="utf-8")
    try:
        store.ingest_file(binaryish)
        assert False, "Expected unsupported extension to be rejected"
    except KnowledgeError:
        pass


def test_pdf_import_extracts_selectable_text_with_page_metadata(tmp_path, monkeypatch):
    import sys
    import types

    from genesis_core.knowledge import KnowledgeStore
    from genesis_core.state import StateStore

    class Page:
        def extract_text(self):
            return "PDF page contains searchable local knowledge."

    class Reader:
        def __init__(self, path):
            self.is_encrypted = False
            self.pages = [Page()]

    fake_module = types.ModuleType("pypdf")
    fake_module.PdfReader = Reader
    monkeypatch.setitem(sys.modules, "pypdf", fake_module)

    store = KnowledgeStore(StateStore(tmp_path / "genesis.db"))
    pdf = tmp_path / "notes.pdf"
    pdf.write_bytes(b"%PDF-fake")

    result = store.ingest_file(pdf)

    assert result["metadata"]["format"] == ".pdf"
    assert result["metadata"]["page_count"] == 1
    assert store.search("searchable local knowledge")
