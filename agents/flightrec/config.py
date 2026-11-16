"""Environment-driven settings for the flight recorder.

Every value comes from an environment variable (see .env.example) so the same
image works in mock mode, against RouteLLM, or fully local with Ollama.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # Where the native store directory lives (shared Docker volume).
    store_path: str = os.getenv("STORE_PATH", "/data/graph")

    # LLM: "mock" replays a scripted run, "openai" hits any OpenAI-compatible API.
    llm_mode: str = os.getenv("LLM_MODE", "mock")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

    # Embeddings: "hash" is a local, dependency-free embedder; "openai" uses an API.
    embed_mode: str = os.getenv("EMBED_MODE", "hash")
    embed_model: str = os.getenv("EMBED_MODEL", "text-embedding-3-small")
    embed_dim: int = int(os.getenv("EMBED_DIM", "256"))

    # Where the live `relate serve` follower exposes its surfaces.
    mcp_url: str = os.getenv("RELATE_MCP_URL", "http://relate:7475")
    relate_auth: str = os.getenv("RELATE_AUTH", "relate:hackathon")

    # Pacing and bound for the agent loop.
    step_delay: float = float(os.getenv("STEP_DELAY", "1.5"))
    max_rounds: int = int(os.getenv("MAX_ROUNDS", "3"))
