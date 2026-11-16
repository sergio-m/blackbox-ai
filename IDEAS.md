# Relate by Neo4j — Hackathon Project Ideas

Prepared for the Relate hackathon. Everything below is designed to run in Docker.

---

## What Relate actually is (verified from the repo, v1.0.x)

- **Embedded, in-memory property-graph engine written in Rust.** Cypher 25 dialect
  (incl. quantified path patterns, label expressions, path selectors).
- **A store is a directory (WAL + Parquet shards), a single `.rl` file, or `:memory:`.**
  Durable via fsync'd WAL + Parquet checkpoints.
- **Surfaces:** CLI (`relate`), Python (`pip install relate-db`, `import relate`),
  Node (`@relate/relate`), browser WASM (`@relate/relate-wasm`), Rust/Java/Go/Swift/C.
- **Optional one-process server:** `relate serve --database ./friends --bolt 7687 --http 7474 --mcp 7475`
  — Neo4j drivers + **Neo4j Browser work out of the box over Bolt**, HTTP Query API v2,
  and **MCP (streamable HTTP)** for AI hosts. Token auth by default (`RELATE_AUTH=relate:secret`).
- **Vector search:** `vector()` properties, `vector.similarity.*`, `CREATE VECTOR INDEX`,
  `SEARCH` clause top-K with pre-filtering, **hybrid vector + full-text**.
- **Geospatial:** WGS-84/Cartesian points, R-tree point indexes, radius/bbox predicates.
- **Live follow:** `--read-only=live` tails a native store's WAL **while another process writes it**.
  The same access modes ride `serve` (per README; check `docs/api/cli/spec.md` for exact flags).
- **Import/sync:** `LOAD CSV`, `--fetch-params` (bind fetched JSON as a Cypher param),
  `pull`/`push` subgraph mirroring to/from Neo4j/Aura, `clone`.
- **Extensions:** userland commands over MCP stdio (`relate extension init <name> --lang py|ts|rust|sh`).
  First-party examples: `fs-to-graph`, `git-to-graph`, `dungeon` (a MUD where every verb is Cypher).
- **Limits (deliberate):** working set fits in RAM, one graph per store,
  **a single writer/user per process** — not a multi-tenant server.
- **Agent skill:** `relate skill install` teaches your own coding agent (Claude Code, Cursor, …)
  the CLI + Cypher dialect. Do this at the hackathon — it makes your agent build faster.
- Docs: https://relatedb.ai/ · Repo: https://github.com/relatedb/relate

---

## Docker patterns with Relate (pick per idea)

**Pattern A — Embedded app container (truest to the pitch).**
One container; the app `import relate`s the engine in-process; store on a named volume.
No DB service at all. Best for single-agent or single-orchestrator apps.

**Pattern B — `relate serve` container (shared brain over sockets).**
The official server image (build from the repo with `make docker`, tag `relate-bolt:latest`)
runs one process exposing Bolt 7687 / HTTP 7474 / MCP 7475 with token auth.
Agent containers connect as clients. This is the way to give **multiple** containers
one shared graph. Seed with `-e RELATE_QUERY=...`, `-e RELATE_LOAD=<url>` + `RELATE_LOAD_QUERY`,
or mirror from Aura with `RELATE_PULL_FROM` / `RELATE_PULL_QUERY`.

**Pattern C — Writer + live followers (the star pattern for demos).**
The orchestrator container owns the store (embedded, writer). A second container runs
`relate serve` in read-only/live-follow mode on the same named volume, tailing the WAL —
giving you **Neo4j Browser, HTTP, and MCP reads of a graph that is being written right now**.
This is observability of a live agent run with zero extra viz infrastructure.

### Docker gotchas

- **One writer per store.** Two containers writing the same store ⇒ locked-store errors
  (exit code 5). Writer embedded + readers via `serve` read-only/live, or everything through one `serve`.
- **`serve` is plaintext-only** (dev/test image). Keep ports on the internal Docker network;
  don't publish 7475 to the open internet.
- **Use named volumes, not macOS bind mounts**, for the store — WAL fsync on virtiofs is slow.
- **Graph must fit in RAM** (in-memory engine). Batch big seeds (`UNWIND` per few thousand rows)
  and use `-e RELATE_DURABILITY_MODE=everysecond` for the seed run only.
- Python container: `pip install relate-db` (import name `relate`), requires Python ≥ 3.9 —
  use `python:3.12-slim` to be safe with wheel availability.

---

## The ideas

### 1. ⭐ Agent Flight Recorder — "watch agents think"

A Dockerized multi-agent team (planner → researcher → coder → critic) works on a task.
The orchestrator (Pattern A, writer) records **every message, tool call, decision, artifact,
and token cost** into Relate as a typed graph:

```
(:Agent)-[:SENT]->(:Message)-[:CITES]->(:Artifact {embedding: vector(...)})
(:Agent)-[:DECIDED]->(:Decision)-[:TRIGGED_BY]->(:Observation)
(:Message)-[:REPLIED_TO]->(:Message)
```

A second container (Pattern C, `serve --read-only=live`) streams that graph to
**Neo4j Browser over Bolt** — the audience literally watches the collaboration graph grow
in real time, message by message. After the run, a "post-mortem" agent answers questions
with **hybrid vector + graph recall**: *"Why did the coder switch libraries at step 12?"*
→ semantic search finds the message, traversal walks the causal chain back to the planner's decision.

- **Wow moment:** live DAG of agent cognition in Neo4j Browser + post-mortem Q&A over the run.
- **Relate features hit:** embedded writer, WAL live-follow, Bolt/Neo4j Browser, MCP,
  hybrid vector+full-text, graph traversal. This is *exactly* the "agent-native" story.
- **Build plan:** Python orchestrator (Pydantic AI or plain loops) + 3-4 agent roles +
  event-to-graph mapper + serve container + a post-mortem CLI/chat. Very achievable in a weekend.
- **Risks:** LLM cost/noise — keep the task small and scripted-ish (e.g., "build a tiny web game").

### 2. Graph Brain — long-term memory for any AI agent (MCP server)

A drop-in **memory service**: `docker compose up` starts a `relate serve` container (Pattern B)
with MCP on 7475. Any MCP host (Claude Code, Cursor, your own agents) connects and gets
persistent, structured memory:

```
(:Entity)-[:RELATES {since, confidence}]->(:Entity)
(:Fact {text, embedding, valid_from, valid_to})-[:ABOUT]->(:Entity)
(:Session)-[:LEARNED]->(:Fact)-[:SOURCED_FROM]->(:Message)
```

The twist vs. generic "memory" MCP servers: it's **graph-native** — typed entities, relationships
with temporal validity (facts that expire), provenance edges back to the exact message that
taught them, and **hybrid recall** (vector + full-text + traversal in one query).
Neo4j Browser over Bolt becomes the "memory inspector" UI.

- **Wow moment:** fresh Claude Code session, zero context — it *remembers* your conventions,
  past bugs, and decisions, and can show you the message where it learned each fact.
- **Relate features hit:** MCP streamable HTTP, Bolt+Browser inspector, hybrid search,
  `vector()` properties, one `.rl` store you can `clone` and hand around.
- **Build plan:** MCP tool set (remember/recall/forget/inspect) + schema + inspector queries.
  Small scope, huge practicality — the "tool people actually keep using" pitch.
- **Risks:** crowded MCP-memory space — lead with the graph schema + provenance + Browser UI.

### 3. Repo Archaeologist — onboarding agent over a git checkout

Point it at any repo (demo on a famous one — `neo4j/relate` itself is poetic). Build a graph of
commits, authors, files, and changed paths (the built-in `git-to-graph` extension proves the shape),
then **go beyond it**: add embeddings over file contents, PR/issue linkage, and an agent that answers
onboarding questions with citations: *"Who has touched the payments module most recently?"*,
*"What's the blast radius if I change this function?"* (quantified path patterns over the
change graph), *"Summarize the history of this subsystem for a new hire."*

- **Wow moment:** `docker compose run archaeologist https://github.com/...` then ask it
  onboarding questions and watch citation-backed answers + impact paths in Neo4j Browser.
- **Relate features hit:** `LOAD CSV`/`--fetch-params` ingestion, vector index + `SEARCH`,
  quantified path patterns, Bolt viz, Pattern A or C.
- **Build plan:** ingest container (git CLI → graph) + agent container + serve for viz.
  Ingestion is the time sink — cap it (last N commits, one subsystem).
- **Risks:** built-in `git-to-graph` does the raw shape — the *semantic + agent* layer is your
  differentiation, so build that first, not the ingestion.

### 4. The Persistent World — NPCs that remember (and gossip)

A text world (differentiate from the built-in `dungeon` extension) where **every NPC is an
agent with a memory graph**: episodes (`(:Player)-[:DID]->(:Action)-[:WITNESSED_BY]->(:NPC)`),
relationships with sentiment that shifts, and **rumors that propagate between NPCs** as edges
you can query ("which NPC knows about the theft?" — traversal over `[:HEARD_FROM]` chains).
The world lives in a Relate store on a volume: kill the container, restart next session,
and the world *remembers*. Multiple players/observers connect through `serve` (MCP/Bolt).

- **Wow moment:** restart the container mid-demo. NPCs still hold grudges from the previous
  session. Then run a query visualizing how a rumor spread through the town.
- **Relate features hit:** WAL durability across restarts, MCP multi-client via serve,
  traversal for memory/rumor propagation, Pattern B.
- **Build plan:** world schema + 3-5 NPCs (one LLM prompt each, memories pulled from the graph)
  + a simple telnet/web frontend + rumor tick loop.
- **Risks:** needs the LLM layer to feel alive (built-in `dungeon` has no LLMs — that's your edge);
  keep the world small.

### 5. The Connections Investigator — six degrees with receipts

Give it two entities (people, companies, technologies) and an agent researches public sources
(Wikipedia API, news RSS, GDELT), building a **provenance graph** where every edge carries its
source: `(:Entity)-[:CONNECTED {source, fetched_at}]->(:Entity)`. It then answers with
**quantified path patterns**: shortest/interesting paths between the two, each hop clickable
to its citation. Hybrid search surfaces semantically-near entities that exact match misses.

- **Wow moment:** type "Sam Altman" and "thermal runaway" — watch a cited, multi-hop path
  appear in Neo4j Browser, every edge with its source URL.
- **Relate features hit:** `--fetch-params` (bind fetched JSON straight into Cypher!),
  quantified path patterns, vector+full-text hybrid, Bolt viz, Pattern C for live crawl viz.
- **Build plan:** crawl container (rate-limited, cached) + agent container + serve.
  Wikipedia + one news source is enough; don't boil the API ocean.
- **Risks:** crawl latency live on stage — pre-crawl a seed set and demo live expansion on top.

---

## Recommendation

**Build #1 (Agent Flight Recorder)** — it is the most *Relate-native* pitch: embedded engine,
WAL live-follow (a feature almost nobody else will show), MCP, hybrid search, and a free
live visualization via Neo4j Browser. The demo is inherently cinematic.

**If you want the "product" angle instead, build #2 (Graph Brain).**
**#1 + #2 compose well:** the flight recorder's run graph *is* the team's memory.

### Suggested compose skeleton (idea #1)

```yaml
services:
  agents:                      # WRITER — owns the store, embedded `import relate`
    build: ./agents            # python:3.12-slim, pip install relate-db
    volumes: [store:/data]
    environment:
      - LLM_API_KEY=${LLM_API_KEY}     # or point at ollama below for a fully-local stack
  relate:
    image: relate-bolt:latest  # build from github.com/relatedb/relate via `make docker`
    volumes: [store:/data]     # same named volume, opened read-only/live — verify flags
    environment: [RELATE_AUTH=relate:hackathon]
    ports: ["7687:7687", "7474:7474", "7475:7475"]
  ollama:                      # optional: zero external API calls
    image: ollama/ollama
    volumes: [ollama:/root/.ollama]
volumes: { store: {}, ollama: {} }
```

Then open Neo4j Browser → `bolt://localhost:7687` (user `relate`, token `hackathon`)
and watch the run graph grow live.

### Spicy differentiators to sprinkle on any idea

- **Geospatial** (points, R-tree, `point.withinBBox`) — almost nobody will use it.
- **WASM build** (`@relate/relate-wasm` + OPFS) — run the *same* store in the browser tab.
- **`pull`/`push` mirroring to Neo4j/Aura** — "your agent's brain, syncable to production".
- **`clone` to a single `.rl` file** — ship the demo graph as one file in the repo.
- **Write a custom extension** (`relate extension init`) — first-party-quality integration.
- **Arrow IPC** (`execute_arrow()`) — hand run analytics to pandas/Polars in one hop.
