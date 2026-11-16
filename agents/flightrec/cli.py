"""CLI entry point: `flightrec init|run|ask`.

- init: create the store directory and schema (the `init` compose service).
- run:  execute the agent team and record everything (the writer).
- ask:  post-mortem Q&A over the read-only MCP follower (no writer here).
"""
import argparse

import relate

from .config import Settings
from .embed import Embedder
from .llm import make_llm
from .orchestrator import Orchestrator
from .postmortem import PostMortem
from .recorder import Recorder


def main() -> None:
    p = argparse.ArgumentParser(prog="flightrec")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("run").add_argument("task")
    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--run", default=None, help="run id, or 'all' (default: latest run)")
    args = p.parse_args()

    s = Settings()
    if args.cmd == "ask":
        # Answer path: goes through MCP to the follower, never opens the store.
        print(PostMortem(s, make_llm(s), Embedder(s)).ask(args.question, args.run))
        return

    # Writer path: connect to the embedded engine (no server process involved).
    db = relate.connect(s.store_path)
    try:
        rec = Recorder(db)
        rec.init_schema()
        if args.cmd == "run":
            Orchestrator(rec, make_llm(s), Embedder(s), s).run(args.task)
        else:
            print(f"store ready at {s.store_path}")
    finally:
        db.close()
