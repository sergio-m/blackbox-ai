"""Writes the run to the embedded Relate engine as a typed graph.

The Recorder is the ONLY writer. Graph model:

    (Run)<-[:IN_RUN]-(Message)         (Agent)-[:SENT]->(Message)
    (Message)-[:REPLIED_TO]->(Message) (Agent)-[:DECIDED]->(Decision)
    (Decision)-[:BASED_ON]->(Message)  (Message)-[:PRODUCED]->(Artifact)
    (Artifact)-[:INPUT_TO]->(ToolCall) (ToolCall)-[:OBSERVED_BY]->(Message)

Messages, Decisions and Artifacts carry an `embedding` list property used for
vector recall later. Durability comes from Relate's WAL; a follower container
tails that same WAL live (see the `relate` compose service).
"""
import uuid
from datetime import datetime, timezone

# Uniqueness constraints so MERGE works and ids stay stable across runs.
SCHEMA = [
    "CREATE CONSTRAINT run_id IF NOT EXISTS FOR (r:Run) REQUIRE r.id IS UNIQUE",
    "CREATE CONSTRAINT agent_name IF NOT EXISTS FOR (a:Agent) REQUIRE a.name IS UNIQUE",
    "CREATE CONSTRAINT message_id IF NOT EXISTS FOR (m:Message) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT decision_id IF NOT EXISTS FOR (d:Decision) REQUIRE d.id IS UNIQUE",
]


def _id() -> str:
    """Short unique node id (8 hex chars) used in ids and citations like [msg abc]."""
    return uuid.uuid4().hex[:8]


def _now() -> str:
    """UTC timestamp with milliseconds, as an ISO string property."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Recorder:
    """Thin wrapper turning orchestrator events into Cypher writes."""

    def __init__(self, db):
        self.db = db

    def _run(self, query: str, params: dict | None = None) -> list:
        """Execute one Cypher statement and materialize its rows."""
        return list(self.db.execute(query, params or {}))

    def init_schema(self) -> None:
        """Create the uniqueness constraints (idempotent, safe to re-run)."""
        for stmt in SCHEMA:
            self._run(stmt)

    def start_run(self, task: str) -> str:
        """Create the Run node for one orchestrator execution; returns its id."""
        run_id = _id()
        self._run(
            "CREATE (:Run {id: $id, task: $task, status: 'running', started_at: $ts})",
            {"id": run_id, "task": task, "ts": _now()},
        )
        return run_id

    def finish_run(self, run_id: str, status: str) -> None:
        """Stamp the final status ("approved"/"failed") and end time on the Run."""
        self._run(
            "MATCH (r:Run {id: $id}) SET r.status = $status, r.ended_at = $ts",
            {"id": run_id, "status": status, "ts": _now()},
        )

    def message(self, run_id, agent, content, embedding, step, parent_id=None, tokens=0) -> str:
        """Record one agent reply: Message + SENT + IN_RUN (+ REPLIED_TO parent)."""
        mid = _id()
        self._run(
            "MATCH (r:Run {id: $run}) "
            "MERGE (a:Agent {name: $agent}) "
            "CREATE (m:Message {id: $id, run_id: $run, step: $step, agent: $agent, "
            "content: $content, embedding: $emb, ts: $ts, tokens: $tokens}) "
            "CREATE (a)-[:SENT]->(m) "
            "CREATE (m)-[:IN_RUN]->(r)",
            {"run": run_id, "agent": agent, "id": mid, "step": step, "content": content,
             "emb": embedding, "ts": _now(), "tokens": tokens},
        )
        if parent_id:
            # Chain the conversation so the causal path is walkable later.
            self._run(
                "MATCH (m:Message {id: $id}), (p:Message {id: $parent}) "
                "CREATE (m)-[:REPLIED_TO]->(p)",
                {"id": mid, "parent": parent_id},
            )
        return mid

    def decision(self, run_id, agent, text, embedding, step, message_id) -> str:
        """Record a DECISION line from a reply, linked to the message it was based on."""
        did = _id()
        self._run(
            "MATCH (m:Message {id: $mid}) "
            "MERGE (a:Agent {name: $agent}) "
            "CREATE (d:Decision {id: $id, run_id: $run, step: $step, agent: $agent, "
            "text: $text, embedding: $emb, ts: $ts}) "
            "CREATE (a)-[:DECIDED]->(d) "
            "CREATE (d)-[:BASED_ON]->(m)",
            {"mid": message_id, "agent": agent, "id": did, "run": run_id, "step": step,
             "text": text, "emb": embedding, "ts": _now()},
        )
        return did

    def artifact(self, run_id, message_id, name, content, embedding) -> str:
        """Record a produced artifact (e.g. solution.py) linked to its message."""
        aid = _id()
        self._run(
            "MATCH (m:Message {id: $mid}) "
            "CREATE (x:Artifact {id: $id, run_id: $run, name: $name, content: $content, "
            "embedding: $emb, ts: $ts}) "
            "CREATE (m)-[:PRODUCED]->(x)",
            {"mid": message_id, "id": aid, "run": run_id, "name": name, "content": content,
             "emb": embedding, "ts": _now()},
        )
        return aid

    def tool_call(self, run_id, artifact_id, tool, result) -> str:
        """Record a tool execution over an artifact (e.g. run_python + its output)."""
        tid = _id()
        self._run(
            "MATCH (x:Artifact {id: $aid}) "
            "CREATE (t:ToolCall {id: $id, run_id: $run, tool: $tool, result: $result, ts: $ts}) "
            "CREATE (x)-[:INPUT_TO]->(t)",
            {"aid": artifact_id, "id": tid, "run": run_id, "tool": tool, "result": result,
             "ts": _now()},
        )
        return tid

    def observe(self, tool_call_id: str, message_id: str) -> None:
        """Link a tool call to the message that saw its result (OBSERVED_BY)."""
        self._run(
            "MATCH (t:ToolCall {id: $t}), (m:Message {id: $m}) CREATE (t)-[:OBSERVED_BY]->(m)",
            {"t": tool_call_id, "m": message_id},
        )
