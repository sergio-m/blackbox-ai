## Inspiration

As AI systems become more capable, it gets harder to understand how they reached an answer—or why they changed course. I wanted to make an agent run observable and explainable: not just a transcript to scroll through, but a connected record of what happened and what influenced it.

## What it does

BlackBox runs a team of AI agents—a Planner, Coder, and Critic—and records their messages, decisions, tool calls, and artifacts in a Relate graph as the run unfolds. You can follow the graph live, then ask a post-mortem agent questions like, “Why did the coder change its solution?” It searches the run’s records, traces the relevant causal chain, and answers with evidence.

## How we built it

Built the agents and recorder in Python, with Relate as the durable graph store. The agents’ container is the sole writer; a second container follows the store’s write-ahead log and exposes the graph over Bolt, HTTP, and MCP. The post-mortem agent uses the read-only MCP connection to retrieve evidence. Docker Compose ties the pieces together, and a deterministic mock mode lets the project run without an API key or internet access.

## Challenges we ran into

The architecture had to support live observation without compromising the graph’s single-writer constraint. I separated writing from serving: the agents write to the embedded store, while a follower exposes a read-only live view. I also had to make post-run answers useful rather than just plausible, so retrieval combines semantic matches with a walk through message and decision relationships.

## Accomplishments that we're proud of

Built an end-to-end system that records a multi-agent run and can answer questions about it afterward. I verified live updates through the follower, tested post-mortem queries over MCP, and ran the system in both deterministic mock mode and with a real LLM. The mock setup also makes the project easy to demo without relying on network access or credentials.

## What we learned

An agent’s history is more useful when it captures relationships, not just text. Connecting decisions to the messages and tool outputs behind them gives us a path from an answer back to its evidence. I also learned that observability needs to be part of the architecture from the start—not bolted on after the agents have finished.

## What's next for BlackBox

I want to improve retrieval with vector and full-text indexes, make answers and causal chains easier to inspect, and add useful run-level views such as token and cost summaries. I’d also like to support richer agent teams and create a replayable run viewer.
