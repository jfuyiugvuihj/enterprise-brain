from pathlib import Path

from app.rag.loader import load_document


TEXT_EXTENSIONS = {".txt", ".md", ".doc", ".docx"}
PDF_EXTENSIONS = {".pdf"}
MAX_PREVIEW_CHARS = 200_000


def build_document_preview(
    file_path: str,
    filename: str | None = None,
    max_chars: int = MAX_PREVIEW_CHARS,
) -> dict:
    """Return browser-friendly metadata for a document preview."""
    path = Path(file_path)
    display_name = filename or path.name
    extension = path.suffix.lower()

    if extension in PDF_EXTENSIONS:
        return {
            "filename": display_name,
            "kind": "pdf",
            "text": "",
        }

    if extension in TEXT_EXTENSIONS:
        text = load_document(str(path))
        return {
            "filename": display_name,
            "kind": "text",
            "text": text[:max_chars],
            "truncated": len(text) > max_chars,
        }

    raise ValueError(f"Unsupported preview format: {extension}")
