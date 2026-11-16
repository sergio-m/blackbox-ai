"""LLM backends for the agents.

`MockLLM` replays a fixed, deterministic script: the Coder's first solution is
wrong (it counts 1 as prime), the Critic rejects it, the second attempt passes.
This makes tests and offline demos reproducible. `OpenAILLM` calls any
OpenAI-compatible chat endpoint (Abacus.AI RouteLLM, OpenAI, Ollama, ...).
"""
import httpx

from .config import Settings

# --- Scripted replies used by MockLLM (one per agent, per round) -------------

PLAN = """PLAN: 1) write a small function that generates primes, 2) print the first 10, 3) have the critic check the output.
DECISION: Use trial division by known primes; it is simple and fast enough for 10 numbers."""

CODE_V1 = """```python
primes = []
for n in range(1, 40):
    if all(n % d for d in range(2, n)):
        primes.append(n)
print(primes[:10])
```
DECISION: Scan from n = 1 and keep numbers with no divisor between 2 and n - 1."""

CRITIC_REJECT = """The output is [1, 2, 3, 5, 7, 11, 13, 17, 19, 23] which is wrong: 1 is not prime and 29 is missing.
The scan must start at 2, because range(2, 1) is empty so 1 passes the divisibility test.
VERDICT: REJECTED
DECISION: Reject the first solution because the counter starts at 1 instead of 2."""

CODE_V2 = """```python
primes = []
for n in range(2, 40):
    if all(n % d for d in range(2, n)):
        primes.append(n)
print(primes[:10])
```
DECISION: Rewrite the scan to start at n = 2 as the critic requested."""

CRITIC_OK = """The output [2, 3, 5, 7, 11, 13, 17, 19, 23, 29] is the correct list of the first 10 primes.
VERDICT: APPROVED
DECISION: Approve the second solution because the output matches the first 10 primes."""


class MockLLM:
    """Deterministic offline LLM: returns the scripted reply per agent/round."""

    def __init__(self):
        self.calls: dict[str, int] = {}

    def complete(self, agent: str, system: str, user: str) -> str:
        """Return the next scripted line for `agent` (round-tracked per agent)."""
        n = self.calls[agent] = self.calls.get(agent, 0) + 1
        if agent == "Planner":
            return PLAN
        if agent == "Coder":
            return CODE_V1 if n == 1 else CODE_V2
        if agent == "Critic":
            return CRITIC_REJECT if n == 1 else CRITIC_OK
        if agent == "Analyst":
            # The post-mortem analyst just echoes the evidence it was given.
            return "Based on the recorded run: " + user.split("EVIDENCE:", 1)[-1].strip()[:900]
        return "OK"


class OpenAILLM:
    """Calls an OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, settings: Settings):
        self.s = settings

    def complete(self, agent: str, system: str, user: str) -> str:
        """One system+user chat round for `agent`; returns the reply text."""
        r = httpx.post(
            f"{self.s.llm_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.s.llm_api_key}"},
            json={
                "model": self.s.llm_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=180,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def make_llm(settings: Settings):
    """Pick the backend from LLM_MODE ("openai" -> API, otherwise mock)."""
    return OpenAILLM(settings) if settings.llm_mode == "openai" else MockLLM()
