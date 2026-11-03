# Reliability iteration — M0

## Scope and preserved baseline

This iteration starts at upstream `c2b818312c3acf6d0847645858e8858d85d73f3a`.
The clone is separate from the WSL academic submission. No `.env`, conversation
records, academic PDF or database volume was copied. Baseline unit result:
155 passed and 7 opt-in cases skipped. The application remains a local prototype;
authentication and multi-user deployment belong to later milestones.

## Decision 1: tool facts are rendered by Python

Previously a tool-selection response with no calls was accepted as an answer.
Even after the correct Python calculation, a final model completion could replace
the numeric answer. Tests demonstrated both an unexecuted `85.9` and a model
replacing an actual `85.9` with `999`.

The selected tool name still describes the router's intent, preserving existing
clients and follow-up routing. A new additive `tool_execution` field describes
execution separately. Calculator breakdowns and verified course records are
rendered from Python results; arbitrary model prose is not presented as a tool
answer. No call produces fixed localized guidance. Validation errors stay errors,
including when the model responds with invented facts after a rejected call.
There is no extra generative completion to rewrite a successful tool result.

Statuses:

- `not_executed`: no accepted attempt was executed or logged; `calls` is empty.
- `executed`: all calls in the final batch returned successfully. Earlier failed
  correction attempts can still appear in `calls`.
- `failed`: at least one call in the final batch failed validation/execution;
  successful calls in a mixed batch remain explicitly recorded as successes.

Every accepted attempt must be persisted before it can be returned. `calls`
contains the tool name and actual success result or safe failure, not proposed
input arguments. Detailed input audit records remain in the existing tool table.
An unavailable course record is a successful lookup with unavailable data.

Example additive response fields (illustration, not a live provider transcript):

```json
{
  "route": "TOOL",
  "tool": "grade_calculator",
  "tool_execution": {
    "status": "executed",
    "calls": [{
      "name": "grade_calculator",
      "status": "success",
      "result": {"final_grade": 85.9, "total_weight": 100, "breakdown": []}
    }]
  }
}
```

Trade-off: fixed templates are less flexible than generated prose and validation
details currently remain in English. This buys an enforceable boundary for numeric
and date facts. The model can still extract incorrect arguments using numbers
already present in user history; the existing numeric-provenance check is not a
proof that every grade was assigned to the intended component. More precise input
confirmation and semantic provenance are later work.

## Decision 2: conservative retrieval context

Short questions beginning How/Why/كيف/لماذا are no longer automatically treated
as continuations. Explicit referential words and topic-free continuation phrases
can inherit only a recent topic. A recent TOOL or DIRECT_LLM answer blocks that
inheritance. Legacy user history identified as a tool request is also excluded;
the resolver never searches back past 12 rows for an older topic.

This remains a bounded heuristic, not a language-understanding guarantee. Ambiguous
pronouns and demonstrative noun phrases may still need clarification. Regression
tests cover independent questions, real follow-ups, multilingual reference words,
malformed rows and recent route changes. These tests do not establish general
multilingual retrieval quality.

## Decision 3: local configuration checks are separate from live verification

`python -m server.preflight [--json]` uses only local configuration. It names
missing/placeholder/invalid settings, never their values, and exits 1 when action
is needed. Passing this command says nothing about credentials being accepted,
model access, funds or database reachability. `get_llm` also rejects the shipped
placeholder model/key before constructing the provider.

No key is copied into the portfolio clone and no model is silently selected.

## Reproduce from a fresh WSL/Linux checkout

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
SMARTCOURSE_ENV_FILE=/dev/null python -m pytest -q
python -m server.preflight --json  # expected exit 1 until configured locally
```

For real local retrieval, cache the public embedding model once if needed. This
downloads public weights; it does not call the generative provider:

```bash
python -c 'from sentence_transformers import SentenceTransformer; SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")'
docker compose -f compose.test.yml up -d --wait
SMARTCOURSE_ENV_FILE=/dev/null \
DATABASE_URL=postgresql://portfolio_test:local-test-only@127.0.0.1:55432/smartcourse_portfolio_test \
SMARTCOURSE_INTEGRATION_TESTS=1 SMARTCOURSE_TEST_DISPOSABLE_DB=1 \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
python -m pytest -q -m 'integration and not live'
docker compose -f compose.test.yml down
```

Never substitute the submission database in this command. Integration tests now
require an explicit disposable-database flag, a loopback connection, and a test
database name. Fresh schema migration precedes vector connection registration.
The Compose test database is ephemeral; stopping it loses its data intentionally.
The existing real retrieval evaluation also requires its own newly empty
`smartcourse_eval_*` database, not an already-used integration database.

## Learning walkthrough

Trace one request: `client/app.js` → `POST /chat` → bounded history → AgentRouter
→ `_process_tool` → LCEL tool-argument selection → provenance/argument validation
→ Python executor → committed audit log → deterministic presentation → exchange
saved with execution metadata → browser → `/history` after refresh.

Exercise: the model returns “85.9” without a tool call. Explain why `route=TOOL`
is insufficient evidence of execution, why Python discards that prose, what the
user sees, what is saved, and why there is no successful tool log.

Next exercise: change a grade or weight, predict the calculator result or rejection,
then add a regression test before changing implementation. Do not add a paid API
call to an ordinary unit test.
