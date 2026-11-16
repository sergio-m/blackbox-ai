"""Text embeddings for semantic recall.

Default is a local hashing embedder (bag-of-words projected to a unit vector):
no network, no model download, works offline in Docker. Set EMBED_MODE=openai
to use any OpenAI-compatible embeddings endpoint instead.
"""
import hashlib
import math
import re

import httpx

from .config import Settings


def hash_embed(text: str, dim: int) -> list[float]:
    """Embed text as a normalized signed bag-of-words vector (deterministic, offline)."""
    vec = [0.0] * dim
    for tok in re.findall(r"[a-z0-9_]+", text.lower()):
        # One hashed bucket per token; the top bit picks the sign so
        # unrelated tokens partly cancel instead of all adding up.
        h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big")
        vec[h % dim] += 1.0 if (h >> 63) & 1 else -1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class Embedder:
    """Produces an embedding vector for a text, per the configured mode."""

    def __init__(self, settings: Settings):
        self.s = settings

    def embed(self, text: str) -> list[float]:
        """Return a vector for `text` (API-backed or local hash)."""
        if self.s.embed_mode == "openai":
            r = httpx.post(
                f"{self.s.llm_base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.s.llm_api_key}"},
                json={"model": self.s.embed_model, "input": text},
                timeout=60,
            )
            r.raise_for_status()
            return r.json()["data"][0]["embedding"]
        return hash_embed(text, self.s.embed_dim)
