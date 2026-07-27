from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from graph_pipeline.config import IngestionConfig, load_config
from graph_pipeline.models.document import Document, TextChunk

logger = logging.getLogger(__name__)

# ── Optional format handlers ──────────────────────────────────────────────

def _try_read_pdf(filepath: Path) -> str | None:
    try:
        import pdfplumber
        with pdfplumber.open(str(filepath)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
            text = "\n\n---\n\n".join(p.strip() for p in pages if p.strip())
            return text if text else None
    except ImportError:
        logger.debug("pdfplumber not installed; skipping %s", filepath.name)
        return None
    except Exception as exc:
        logger.warning("Failed to read PDF %s: %s", filepath.name, exc)
        return None


def _try_read_html(filepath: Path) -> str | None:
    try:
        from bs4 import BeautifulSoup
        raw = filepath.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        return "\n".join(lines) if lines else None
    except ImportError:
        logger.debug("beautifulsoup4 not installed; skipping %s", filepath.name)
        return None
    except Exception as exc:
        logger.warning("Failed to read HTML %s: %s", filepath.name, exc)
        return None


_FORMAT_HANDLERS: dict[str, callable] = {
    ".pdf": _try_read_pdf,
    ".html": _try_read_html,
    ".htm": _try_read_html,
}


class TextChunker:
    """Ingest text files and produce overlapping sliding-window chunks.

    Supports .txt, .md, .pdf (via pdfplumber), and .html/.htm (via BeautifulSoup).
    Tracks content hashes for incremental processing.
    """

    def __init__(self, config: IngestionConfig | None = None) -> None:
        if config is None:
            config = load_config().ingestion
        self.chunk_size = config.chunk_size
        self.chunk_overlap = config.chunk_overlap
        self.input_dir = Path(config.input_dir)
        self.supported_extensions = set(config.supported_extensions)
        self.max_file_size_bytes = config.max_file_size_mb * 1024 * 1024
        self._content_hashes: dict[str, str] = {}

    # ── file discovery ───────────────────────────────────────────────────

    def discover_files(self) -> list[Path]:
        if not self.input_dir.exists():
            return []
        all_handlers = self.supported_extensions | set(_FORMAT_HANDLERS.keys())
        files: list[Path] = []
        for ext in all_handlers:
            files.extend(self.input_dir.rglob(f"*{ext}"))
        return sorted(set(files))

    def file_content_hash(self, filepath: Path) -> str:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _derive_document_id(self, filepath: Path) -> str:
        try:
            relative = filepath.relative_to(self.input_dir)
        except ValueError:
            relative = filepath
        doc_id = str(relative).replace("\\", "/").replace("/", "__")
        doc_id = Path(doc_id).stem
        return doc_id

    def _derive_subfolder(self, filepath: Path) -> str:
        try:
            relative = filepath.relative_to(self.input_dir)
            parts = relative.parts
            if len(parts) > 1:
                return "/".join(parts[:-1])
        except ValueError:
            pass
        return ""

    # ── file reading ─────────────────────────────────────────────────────

    def ingest_file(self, filepath: Path) -> Document:
        ext = filepath.suffix.lower()
        handler = _FORMAT_HANDLERS.get(ext)
        if handler is not None:
            text = handler(filepath)
            if text is None:
                text = ""
        else:
            fsize = filepath.stat().st_size
            if fsize > self.max_file_size_bytes:
                logger.warning(
                    "File %s is %.1f MB (limit %d MB); skipping",
                    filepath.name, fsize / 1e6, self.max_file_size_bytes / 1e6,
                )
                text = filepath.read_text(encoding="utf-8", errors="replace")[:self.max_file_size_bytes]
            else:
                text = filepath.read_text(encoding="utf-8", errors="replace")

        doc_id = self._derive_document_id(filepath)
        subfolder = self._derive_subfolder(filepath)
        content_hash = self.file_content_hash(filepath)

        doc = Document(
            id=doc_id,
            filename=filepath.name,
            filepath=str(filepath),
            subfolder=subfolder,
            raw_text=text,
        )
        return doc, content_hash

    def chunk_document(self, doc: Document) -> list[TextChunk]:
        text = doc.raw_text
        chunks: list[TextChunk] = []
        start = 0
        idx = 0

        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunk_text = text[start:end]
            if not chunk_text.strip():
                break

            chunk = TextChunk(
                id=f"{doc.id}__chunk_{idx:04d}",
                document_id=doc.id,
                chunk_index=idx,
                text=chunk_text,
                start_char=start,
                end_char=end,
                subfolder=doc.subfolder,
                page_range=doc.page_range,
            )
            chunks.append(chunk)
            idx += 1
            start += self.chunk_size - self.chunk_overlap

        return chunks

    # ── batch processing ─────────────────────────────────────────────────

    def ingest_all(self) -> tuple[list[Document], list[TextChunk]]:
        files = self.discover_files()
        documents: list[Document] = []
        all_chunks: list[TextChunk] = []

        for filepath in files:
            doc, _ = self.ingest_file(filepath)
            chunks = self.chunk_document(doc)
            doc.chunk_ids = [c.id for c in chunks]
            documents.append(doc)
            all_chunks.extend(chunks)

        return documents, all_chunks

    def ingest_all_incremental(
        self,
        previous_hashes: dict[str, str] | None = None,
    ) -> tuple[list[Document], list[TextChunk], list[str]]:
        """Like ingest_all but returns only new/changed files plus stale IDs.

        Returns:
          (new_documents, new_chunks, stale_document_ids)
        """
        previous_hashes = previous_hashes or {}
        files = self.discover_files()
        new_documents: list[Document] = []
        new_chunks: list[TextChunk] = []
        current_hashes: dict[str, str] = {}
        stale_ids: list[str] = []

        for filepath in files:
            doc, content_hash = self.ingest_file(filepath)
            current_hashes[doc.id] = content_hash
            old_hash = previous_hashes.get(doc.id)
            if old_hash == content_hash:
                logger.debug("Skipping unchanged file: %s", filepath.name)
                continue
            chunks = self.chunk_document(doc)
            doc.chunk_ids = [c.id for c in chunks]
            new_documents.append(doc)
            new_chunks.extend(chunks)
            stale_ids.append(doc.id)

        return new_documents, new_chunks, stale_ids

    def ingest_string(self, text: str, doc_id: str = "inline_source") -> TextChunk:
        """Ingest a raw string directly without file I/O — useful for tests."""
        chunk = TextChunk(
            id=f"{doc_id}__chunk_0000",
            document_id=doc_id,
            chunk_index=0,
            text=text,
            start_char=0,
            end_char=len(text),
        )
        return chunk
