"""Post-mortem: answer questions about a recorded run.

Retrieval over the live MCP follower (read-only), generation via the LLM:
1. embed the question, top-K Messages/Decisions by vector similarity
   (filtered to one run unless --run all);
2. walk REPLIED_TO backwards from each hit to rebuild the causal chain;
3. attach each message's Decisions;
4. hand the ordered evidence to the Analyst LLM, which must cite message ids.
"""
from .config import Settings
from .embed import Embedder
from .mcp_client import McpClient

# Top-K semantic hits among messages and decisions; $run is None for "all runs".
TOP_K = """
MATCH (n) WHERE (n:Message OR n:Decision) AND ($run IS NULL OR n.run_id = $run)
WITH n, vector.similarity.cosine(n.embedding, $q) AS score
RETURN labels(n)[0] AS kind, n.id AS id, score
ORDER BY score DESC
LIMIT $k
"""

# From one hit, collect the message it was based on (if any) and walk the
# REPLIED_TO chain backwards up to 6 hops - the causal conversation so far.
HIT_MESSAGE = """
MATCH (n {id: $id})
OPTIONAL MATCH (n)-[:BASED_ON]->(b:Message)
WITH coalesce(b, n) AS m
MATCH (m)-[:REPLIED_TO*0..6]->(c:Message)
RETURN DISTINCT c.id AS id, c.step AS step, c.agent AS agent, c.content AS content
ORDER BY step
"""

# Decisions that were made on the basis of one message.
DECISIONS = """
MATCH (d:Decision)-[:BASED_ON]->(m:Message {id: $id})
RETURN d.id AS id, d.agent AS agent, d.text AS text
"""

# Every message of a run (or all runs), in order - used by the summary fallback.
RUN_MESSAGES = """
MATCH (m:Message) WHERE $run IS NULL OR m.run_id = $run
RETURN m.id AS id, m.step AS step, m.agent AS agent, m.content AS content
ORDER BY m.run_id, step
"""

LATEST_RUN = """
MATCH (r:Run) RETURN r.id AS id, r.task AS task ORDER BY r.started_at DESC LIMIT 1
"""

RUN_TASK = """
MATCH (r:Run {id: $id}) RETURN r.task AS task
"""


class PostMortem:
    """Question-answering over the recorded runs, via the read-only MCP server."""

    def __init__(self, settings: Settings, llm, embedder: Embedder, mcp: McpClient | None = None):
        self.s = settings
        self.llm = llm
        self.emb = embedder
        self.mcp = mcp or McpClient(settings.mcp_url, settings.relate_auth)

    def resolve_run(self, run: str | None) -> tuple[str | None, str]:
        """Map the CLI --run flag to a run id + task label (None id = all runs)."""
        if run == "all":
            return None, "all runs"
        rows = self.mcp.read_cypher(RUN_TASK, {"id": run}) if run else self.mcp.read_cypher(LATEST_RUN)
        if not rows:
            raise SystemExit(f"run {run} not found" if run else "no runs recorded yet")
        return (run or rows[0]["id"]), rows[0]["task"]

    def gather(self, question: str, run_id: str | None, k: int = 4) -> list[dict]:
        """Vector-search hits, expand each to its causal chain, attach decisions."""
        hits = self.mcp.read_cypher(TOP_K, {"q": self.emb.embed(question), "k": k, "run": run_id})
        chains: dict[str, dict] = {}
        for h in hits:
            for m in self.mcp.read_cypher(HIT_MESSAGE, {"id": h["id"]}):
                chains.setdefault(m["id"], {**m, "decisions": [
                    d["text"] for d in self.mcp.read_cypher(DECISIONS, {"id": m["id"]})
                ]})
        return sorted(chains.values(), key=lambda m: m["step"])

    def whole_run(self, run_id: str | None) -> list[dict]:
        """Every message of the run in order, with its decisions (summary mode)."""
        rows = self.mcp.read_cypher(RUN_MESSAGES, {"run": run_id})
        for m in rows:
            m["decisions"] = [d["text"] for d in self.mcp.read_cypher(DECISIONS, {"id": m["id"]})]
        return rows

    def ask(self, question: str, run: str | None = None) -> str:
        """Answer `question` from the recorded graph; cites [msg ...] ids."""
        run_id, task = self.resolve_run(run)
        if not any(self.emb.embed(question)):
            # Question had no searchable words: summarize the whole run instead.
            question = "Summarize what happened in this run and why each key decision was made."
            evidence = self.whole_run(run_id)
        else:
            evidence = self.gather(question, run_id)
        if not evidence:
            return "No recorded messages matched the question."
        # Render the evidence compactly; the Analyst may only use this.
        lines = []
        for m in evidence:
            first = m["content"].strip().splitlines()[0][:160]
            decs = "; ".join(m["decisions"])
            lines.append(f"[msg {m['id']} step {m['step']} {m['agent']}] {first}" + (f" | decisions: {decs}" if decs else ""))
        context = "\n".join(lines)
        system = ("You are a post-mortem analyst for a multi-agent run. Answer the QUESTION directly in a few "
                  "sentences, using only the EVIDENCE. Cite message ids like [msg abc123]. "
                  "If the evidence does not answer the question, say so.")
        answer = self.llm.complete(
            "Analyst", system, f"RUN TASK: {task}\nQUESTION: {question}\nEVIDENCE:\n{context}"
        )
        return f"Run {run_id or 'all'}: {task}\n\n{answer}\n\nEvidence chain:\n{context}"
