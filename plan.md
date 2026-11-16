# BlackBox — Agent Flight Recorder: Plan

Hackathon: Relate by Neo4j. Constraint: everything runs in Docker.

## 1. Goal

A multi-agent team (Planner, Coder, Critic) works on a task. Every message, decision, tool call
and artifact is written into a **Relate** graph as the run happens. A second container follows the
same store live and exposes it over Bolt/HTTP/MCP, so the audience watches the collaboration graph
grow in Neo4j Browser. Afterwards a **post-mortem agent** answers "why did X happen?" using
vector search plus causal-chain traversal, over a strictly read-only MCP connection.

Demo in one line: *run a team of agents, watch their reasoning appear as a live graph, then
interrogate the run.*

## 2. Verified Relate facts this design relies on (v1.0.1)

| Need | Relate capability | Source |
| --- | --- | --- |
| Embedded writer in Python | `pip install relate-db`, `import relate`, `relate.connect(path)` | README |
| Live view while writer runs | `relate serve --read-only=live` tails the WAL of a native directory store (refuses `.rl` and `:memory:`) | docs/api/cli/spec.md |
| Neo4j Browser / drivers | `--bolt 7687`; HTTP Query API on 7474 allows `browser.neo4j.io` origin by default | README, spec |
| Agent access | `--mcp 7475` streamable HTTP; read-only serve does not list `write_cypher` | docs/api/mcp/spec.md |
| Semantic recall | list/`vector()` properties, `vector.similarity.cosine`, optional `CREATE VECTOR INDEX` + `SEARCH` | docs/guides/vector-similarity.md |
| Server image | none published; release binaries `relate-linux-{amd64,arm64}` + `SHA256SUMS` on GitHub Releases | releases API |

Constraints: one writer per store; working set in RAM; `serve` is plaintext (keep it on the compose
network, publish ports on 127.0.0.1 only); auth is on (`RELATE_AUTH`).

## 3. Architecture

```
            named volume "store" (/data/graph, native directory store)
                 |  writer (read/write)            |  follower (read-only, live WAL tail)
        +--------+---------+                +------+----------------+
        | agents container |                | relate container      |
        |  flightrec CLI   |                |  relate serve         |
        |  embedded relate |                |  Bolt 7687 HTTP 7474  |
        |  Planner/Coder/  |                |  MCP 7475             |
        |  Critic + recorder|               +---+---------+---------+
        +---------+--------+                    |         |
                  |  LLM (OpenAI-compatible)    |         +--> Neo4j Browser (bolt://localhost:7687)
                  v                             |
        mock | ollama | any API        post-mortem agent --MCP read_cypher--+
```

Compose services:

- `init` (one-shot): creates the store and schema so the follower has something to open.
- `relate` (follower): custom image holding the pinned release binary; starts after `init`.
- `agents` (profile `tools`): the writer; used via `docker compose run --rm agents run|ask`.
- `ollama` (profile `local-llm`): optional, fully offline LLM.

## 4. Graph model

Nodes: `Run`, `Agent`, `Message`, `Decision`, `ToolCall`, `Artifact`.

```
(Run)<-[:IN_RUN]-(Message)            (Agent)-[:SENT]->(Message)
(Message)-[:REPLIED_TO]->(Message)    (Agent)-[:DECIDED]->(Decision)
(Decision)-[:BASED_ON]->(Message)     (Message)-[:PRODUCED]->(Artifact)
(Artifact)-[:INPUT_TO]->(ToolCall)    (ToolCall)-[:OBSERVED_BY]->(Message)
```

`Message`, `Decision`, `Artifact` carry an `embedding` list. Message also has `step`, `agent`,
`content`, `tokens`, `ts`.

## 5. Components (`agents/flightrec/`)

| File | Responsibility |
| --- | --- |
| `config.py` | Env-driven settings |
| `llm.py` | `MockLLM` (scripted, deterministic, no key needed) and `OpenAILLM` (any OpenAI-compatible endpoint: Ollama, OpenAI, Abacus RouteLLM) |
| `embed.py` | Local hashing embedder (zero deps, offline) or OpenAI-compatible embeddings |
| `recorder.py` | Schema init and all graph writes |
| `orchestrator.py` | Planner -> Coder -> run_python tool -> Critic loop; records everything |
| `mcp_client.py` | Minimal MCP streamable-HTTP client for `read_cypher` |
| `postmortem.py` | Vector hit -> causal-chain traversal -> grounded answer |
| `cli.py` | `init`, `run`, `ask` |

## 6. Milestones

1. **Skeleton (this scaffold)**: compose, images, schema, recorder, mock-mode end-to-end run. Verify
   follower sees live writes and MCP answers a query.
2. **Real LLMs**: wire `LLM_MODE=openai`, test against Ollama and a hosted API; tune prompts so
   DECISION lines appear reliably.
3. **Post-mortem quality**: vector index + `SEARCH` instead of scan, hybrid with full-text, better
   chain rendering, answer citations (message ids).
4. **Demo polish**: seed an interesting task, step delay for pacing, saved Browser style/queries,
   `clone` the finished run to a single `.rl` file to commit as a replayable artifact.
5. **Stretch**: more agents (Researcher with web tool), per-run cost/token dashboard queries,
   WASM replay viewer, `pull`/`push` mirror to Aura.

## 7. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Follower cannot open a store that does not exist yet | `init` service creates it first; follower entrypoint also waits for it |
| Live WAL tailing on a shared Docker volume behaves differently than on host | Named volume (not bind mount); verified in milestone 1 |
| Venue wifi / API keys unavailable | `LLM_MODE=mock` default, offline embeddings, optional Ollama |
| Single writer lock | Only `agents` writes; everything else reads through the follower |
| LLM output noise | Mock mode for rehearsal; strict `DECISION:` line convention and tolerant parsing |
| `run_python` tool executes model code | Runs inside the container, 10 s timeout, no network needed; do not mount secrets into `agents` beyond the LLM key |

## 8. Definition of done (for the scaffold)

- `docker compose build` succeeds.
- `make up` starts the follower; `make run` completes a mock run.
- Querying the follower (HTTP or MCP) returns the recorded run's nodes.
- `make ask Q="..."` returns an answer citing recorded message ids.
- Unit tests pass in the `agents` image.

## 9. Status (2026-11-14)

Milestones 1 and 2 are done and verified. The rest is open.

Verified by running it:
- `docker compose build` for all images; the 3 unit tests pass in the `agents` image.
- The follower follows: a query over HTTP returned a growing message count while a run was
  still in flight.
- Mock run end-to-end (run `29750678`): 5 messages, 5 decisions, 2 artifacts, 2 tool calls.
- Real-LLM run with Abacus.AI RouteLLM (`route-llm`), run `b6bd1a7c` (palindrome task).
- `ask` over the read-only MCP follower: latest-run default, `--run <id>`, `--run all`, and the
  no-searchable-words fallback to a whole-run summary.
- Compliance queries 1 and 2 in `queries.cypher` executed over HTTP. Query 2 returned 0 rows
  because no run has had a failed tool call yet, so its non-empty path is unobserved.

Not yet verified: Neo4j Browser itself, the `ollama` profile, amd64 (the release binary needs
glibc 2.39; the image is Ubuntu 24.04), vector-index `SEARCH` and full-text hybrid (retrieval is
still a scan — milestone 3), milestones 4 and 5.
