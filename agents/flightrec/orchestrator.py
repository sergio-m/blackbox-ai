"""Runs the multi-agent loop and records every step.

Flow per round: Planner (once) -> Coder -> run the code as a tool -> Critic.
Each reply is stored as a Message; DECISION lines in replies become Decision
nodes; the code becomes an Artifact whose ToolCall holds the real output.
The loop stops when the Critic approves or MAX_ROUNDS is exhausted.
"""
import re
import subprocess
import sys
import time

from .config import Settings
from .embed import Embedder
from .recorder import Recorder

# Role instructions; each asks for a trailing "DECISION:" line, which the
# recorder turns into a Decision node.
SYSTEMS = {
    "Planner": "You are the Planner. Produce a short numbered plan for the task. "
               "End with one line starting with 'DECISION:' stating your key design choice.",
    "Coder": "You are the Coder. Reply with one ```python block that solves the task and prints its result. "
             "End with one line starting with 'DECISION:' explaining your key choice.",
    "Critic": "You are the Critic. Judge the code and its output. Include a line 'VERDICT: APPROVED' or "
              "'VERDICT: REJECTED', then one line starting with 'DECISION:' explaining why.",
}


def extract_decisions(text: str) -> list[str]:
    """Pull all "DECISION: ..." lines out of a reply."""
    return [m.strip() for m in re.findall(r"^DECISION:\s*(.+)$", text, flags=re.M)]


def extract_code(text: str) -> str | None:
    """Return the first ```python fenced block in a reply, or None."""
    m = re.search(r"```(?:python)?\n(.*?)```", text, flags=re.S)
    return m.group(1) if m else None


def run_python(code: str, timeout: int = 10) -> str:
    """Execute generated code in a subprocess; return combined output (bounded).

    Never raises: crashes and timeouts are returned as text so the Critic
    (and the graph) see the failure.
    """
    try:
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=timeout)
        return ((p.stdout or "") + (p.stderr or "")).strip()[:2000] or "(no output)"
    except subprocess.TimeoutExpired:
        return f"(timed out after {timeout}s)"


class Orchestrator:
    """Drives Planner/Coder/Critic and writes every event through the Recorder."""

    def __init__(self, recorder: Recorder, llm, embedder: Embedder, settings: Settings):
        self.rec = recorder
        self.llm = llm
        self.emb = embedder
        self.s = settings
        self.step = 0

    def _say(self, run_id: str, agent: str, user: str, parent: str | None) -> tuple[str, str]:
        """One agent turn: LLM call -> Message (+Decisions); returns (msg_id, text)."""
        self.step += 1
        text = self.llm.complete(agent, SYSTEMS[agent], user)
        mid = self.rec.message(
            run_id, agent, text, self.emb.embed(text), self.step, parent, tokens=len(text.split())
        )
        for d in extract_decisions(text):
            self.rec.decision(run_id, agent, d, self.emb.embed(d), self.step, mid)
        print(f"[{self.step}] {agent}: {text.splitlines()[0][:100]}", flush=True)
        time.sleep(self.s.step_delay)
        return mid, text

    def run(self, task: str) -> str:
        """Run the full loop for `task`; returns the run id (status recorded too)."""
        run_id = self.rec.start_run(task)
        print(f"run {run_id}: {task}", flush=True)
        status = "failed"
        try:
            parent, plan = self._say(run_id, "Planner", f"Task: {task}", None)
            feedback = ""
            for _ in range(self.s.max_rounds):
                # Coder gets the plan plus the Critic's previous feedback.
                parent, reply = self._say(
                    run_id, "Coder", f"Task: {task}\nPlan:\n{plan}\n{feedback}", parent
                )
                code = extract_code(reply) or ""
                coder_msg = parent
                # Record the code as an artifact and actually run it.
                aid = self.rec.artifact(run_id, coder_msg, "solution.py", code, self.emb.embed(code))
                output = run_python(code)
                tid = self.rec.tool_call(run_id, aid, "run_python", output)
                print(f"    run_python -> {output[:100]}", flush=True)
                # Critic sees code + real output; the tool call is linked to it.
                parent, review = self._say(
                    run_id, "Critic", f"Task: {task}\nCode:\n{code}\nOutput:\n{output}", coder_msg
                )
                self.rec.observe(tid, parent)
                if "VERDICT: APPROVED" in review:
                    status = "approved"
                    break
                feedback = f"Critic feedback:\n{review}"
        finally:
            # Never lose the final status, even if the loop raises.
            self.rec.finish_run(run_id, status)
        print(f"run {run_id} finished: {status}", flush=True)
        return run_id
