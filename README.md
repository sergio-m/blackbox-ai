# BlackBox — an Agent Flight Recorder built on Relate

Watch a team of AI agents think, as a live graph. Then interrogate the run.

BlackBox runs a small multi-agent team (Planner, Coder, Critic). Every message, decision, tool
call and artifact is written into an embedded [Relate](https://github.com/relatedb/relate) graph
while the agents work. A second container follows the same store live and serves it over Bolt,
HTTP and MCP, so you can watch the run grow in Neo4j Browser. When the run ends, a post-mortem
agent answers questions such as *"why did the coder rewrite its solution?"* by combining vector
search with a walk back through the causal chain, over a read-only MCP connection.

Everything runs in Docker. With the default mock mode it needs no API key and no internet at
runtime.

## Quick start

```bash
cp .env.example .env
make build
make up            # creates the store, starts the live Relate server
make run           # run the agent team (mock LLM by default)
make ask Q="Why did the coder change its solution?"   # answers from the latest run
make ask RUN=all Q="What did the critic verify?"      # evidence from all runs
```

A question with no searchable words (for example `Q="..."`) falls back to a summary of the
latest run instead of failing.

While `make run` is going, open Neo4j Browser at https://browser.neo4j.io, connect to
`bolt://localhost:7687` with user `relate` and the password from `.env` (`RELATE_AUTH`), and run:

```cypher
MATCH (n)-[r]->(m) RETURN n, r, m
```

Re-run it as the agents work to see new nodes appear. To follow one session, filter by run id:
`MATCH (m:Message {run_id: '<run id>'})-[r]-(n) RETURN m, r, n`. HTTP query API:
`http://localhost:7474`, MCP endpoint: `http://localhost:7475`.

## How data flows

One store, two processes. The `agents` container embeds the Relate engine in-process and is the
only writer; its committed WAL frames are tailed live by the `relate` container, which serves
the same graph over three read-only surfaces.

```
 writer: agents container                    reader: relate container
 ┌─────────────────────────────────┐         ┌──────────────────────────────────────┐
 │ flightrec run "task"            │         │ relate serve --read-only=live        │
 │                                 │         │                                      │
 │ Planner → Coder → run_python    │         │ Bolt :7687  ← Neo4j Browser (watch)  │
 │   → Critic loop                 │         │ HTTP :7474  ← curl / query API       │
 │                                 │         │ MCP  :7475  ← post-mortem `ask`      │
 │ each event → Recorder → Cypher  │         │ (read-only: no write tool offered)   │
 │      ▼                          │         └───────────────┬──────────────────────┘
 │ embedded Relate engine          │                         │
 │ (in-process, no server)         │                         │
 └────────┬────────────────────────┘                         │
          │ fsync WAL                                        │ tails WAL live
          ▼                                                  │
   named volume "store" (/data/graph: WAL + Parquet) ◀───────┘
```

### Relate as the team's memory

Relate is the memory of this run: an embedded, durable store of *what happened* and *why*.
Nothing is kept only in chat history — every message, decision and tool output is a node, and
recall is a query, not a scroll-back.

```
 what is remembered                    how it is recalled
 ───────────────────────────           ─────────────────────────────────────────────
 (Agent)-[:SENT]->(Message)            vector search on .embedding (semantic hit)
 (Message)-[:REPLIED_TO]->( )   ──►    REPLIED_TO*0..6 walk  = the causal chain
 (Agent)-[:DECIDED]->(Decision)        Decision.text         = the stated "why"
 (Artifact)-[:INPUT_TO]->(ToolCall)    ToolCall.result       = the real observed output
        -[:OBSERVED_BY]->
```

The post-mortem uses exactly this: embed the question → top-K messages/decisions by similarity
→ walk the reply chain backwards → attach the decisions → let the LLM answer citing message ids.
Because the store is a directory (WAL + Parquet), memory survives container restarts, and the
same store can be read simultaneously as Browser visualization, HTTP rows, or MCP tool calls.

## Using a real LLM

In mock mode the three agents replay a fixed script about prime numbers, so every mock run is
about primes regardless of the task. Use a real model for different tasks.

Any OpenAI-compatible endpoint works. Edit `.env`:

```
LLM_MODE=openai
LLM_BASE_URL=https://api.openai.com/v1      # or http://ollama:11434/v1
LLM_API_KEY=...
LLM_MODEL=gpt-4o-mini
```


Fully local: `docker compose --profile local-llm up -d ollama`, pull a model with
`docker compose exec ollama ollama pull llama3.2`, then set `LLM_BASE_URL=http://ollama:11434/v1`
and `LLM_MODEL=llama3.2`.

## Graph model

```
(Run)<-[:IN_RUN]-(Message)            (Agent)-[:SENT]->(Message)
(Message)-[:REPLIED_TO]->(Message)    (Agent)-[:DECIDED]->(Decision)
(Decision)-[:BASED_ON]->(Message)     (Message)-[:PRODUCED]->(Artifact)
(Artifact)-[:INPUT_TO]->(ToolCall)    (ToolCall)-[:OBSERVED_BY]->(Message)
```

Useful queries are in `queries.cypher`, including compliance queries: which decisions relied on
which tool output, and which relied on a failed tool call (matched by `Traceback`/`Error`/
timeout markers in the recorded result text).

## Layout

| Path | Purpose |
| --- | --- |
| `docker-compose.yml` | init, relate (live follower), agents (writer), optional ollama |
| `relate-server/` | Dockerfile that pins the Relate v1.0.1 Linux release binary (checksum-verified) on Ubuntu 24.04, which the binary requires for glibc 2.39; tested on arm64 |
| `agents/` | Python package `flightrec` and tests |
| `plan.md` | Design, milestones, risks |

## Notes

- Relate allows one writer per store. Only the `agents` container writes; the `relate` container
  opens the same volume with `--read-only=live`.
- `relate serve` is plaintext. Ports are published on 127.0.0.1 only.
- The Coder's code is executed with a 10 s timeout inside the `agents` container.
