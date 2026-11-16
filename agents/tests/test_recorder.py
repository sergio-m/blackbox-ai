"""Tests for the flight recorder pipeline (offline: mock LLM, in-memory store)."""
import relate

from flightrec.config import Settings
from flightrec.embed import Embedder, hash_embed
from flightrec.llm import MockLLM
from flightrec.orchestrator import Orchestrator, extract_code, extract_decisions
from flightrec.recorder import Recorder


def make():
    """Fresh settings + in-memory store with schema; nothing touches Docker."""
    s = Settings(step_delay=0)
    db = relate.connect(":memory:")
    rec = Recorder(db)
    rec.init_schema()
    return s, db, rec


def test_extractors():
    """Reply parsing: fenced code block and DECISION lines."""
    text = "```python\nprint(1)\n```\nDECISION: a\nDECISION: b"
    assert extract_code(text) == "print(1)\n"
    assert extract_decisions(text) == ["a", "b"]


def test_hash_embed_similarity():
    """Word-overlap should score higher than unrelated text (word-order agnostic)."""
    a = hash_embed("coder started the loop at one", 256)
    b = hash_embed("loop started at one by the coder", 256)
    c = hash_embed("completely unrelated weather forecast", 256)
    dot = lambda x, y: sum(i * j for i, j in zip(x, y))
    assert dot(a, b) > dot(a, c)


def test_mock_run_builds_graph():
    """Full scripted run: approval, message count, reply chain, buggy tool output."""
    s, db, rec = make()
    run_id = Orchestrator(rec, MockLLM(), Embedder(s), s).run("first 10 primes")
    status = list(db.execute("MATCH (r:Run {id: $id}) RETURN r.status AS s", {"id": run_id}))
    assert status[0]["s"] == "approved"
    msgs = list(db.execute("MATCH (m:Message) RETURN count(m) AS c"))[0]["c"]
    assert msgs == 5
    # The Critic's first reply must be chained to the Coder's first attempt.
    chain = list(db.execute(
        "MATCH (m:Message {agent: 'Coder'})-[:REPLIED_TO]->(c:Message {agent: 'Critic'}) RETURN count(m) AS c"
    ))[0]["c"]
    assert chain == 1
    # The buggy first solution was really executed and its output recorded.
    bad = list(db.execute("MATCH (t:ToolCall) WHERE t.result CONTAINS '[1,' RETURN count(t) AS c"))[0]["c"]
    assert bad == 1
