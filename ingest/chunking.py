"""Split documents into overlapping chunks with ids that stay the same while the text does.

No Azure or FAA specifics here, so other projects can reuse it as is.
"""
import base64
import hashlib


def doc_id_for(blob_name: str) -> str:
    """A search-safe id for a file. Keys allow only letters, digits, - _ and =, so encode the name.

    The same file name always gives the same id; a renamed file is a new document.
    """
    return base64.urlsafe_b64encode(blob_name.encode()).decode().rstrip("=")


def chunk_text(text: str, size: int = 1200, overlap: int = 150, min_len: int = 50) -> list[str]:
    """Fixed-size windows that overlap, so a fact cut at one boundary is whole in the next chunk.

    Each window starts `size - overlap` characters after the previous one.
    Chunks shorter than `min_len` (usually the tail end) are dropped.
    """
    if not 0 <= overlap < size:
        raise ValueError(f"overlap must be at least 0 and smaller than size, got {overlap=} {size=}")
    step = size - overlap
    chunks = [text[i:i + size].strip() for i in range(0, len(text), step)]
    return [c for c in chunks if len(c) > min_len]


def chunk_id(doc_id: str, chunk: str) -> str:
    """Document id + hash of the text: unchanged text keeps its id, edited text gets a new one."""
    return f"{doc_id}-{hashlib.sha1(chunk.encode()).hexdigest()[:16]}"
