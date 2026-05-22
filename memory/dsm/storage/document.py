from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(slots=True)
class DocumentChunk:
    document_id: str
    chunk_index: int
    text: str
    digest: str

    @property
    def stable_id(self) -> str:
        raw = f"{self.document_id}:{self.chunk_index}".encode("utf-8")
        return hashlib.blake2b(raw, digest_size=16).hexdigest()


def split_document(document_id: str, text: str, chunk_token_limit: int) -> list[DocumentChunk]:
    chunks = chunk_text(text, chunk_token_limit)
    return [
        DocumentChunk(
            document_id=document_id,
            chunk_index=index,
            text=chunk,
            digest=hash_text(chunk),
        )
        for index, chunk in enumerate(chunks)
    ]


def hash_text(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


def chunk_text(text: str, token_limit: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return []
    if token_limit <= 0:
        raise ValueError("token_limit must be positive")
    return [" ".join(words[i : i + token_limit]) for i in range(0, len(words), token_limit)]
