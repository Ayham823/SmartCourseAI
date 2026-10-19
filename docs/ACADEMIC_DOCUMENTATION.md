# SmartCourse AI — Agentic Study Assistant

Verification evidence is recorded separately in [verification.md](verification.md); an implemented feature is not proof that a live integration has passed.

## Purpose and features

SmartCourse AI is a university-course study assistant for students. It keeps the existing three-tier architecture: a plain HTML/CSS/JavaScript client, a Python Flask REST server, and Dockerized PostgreSQL with pgvector. Every chat question passes through an explicit Agent Router, which chooses document retrieval (`RAG`), an approved custom tool (`TOOL`), or a general Anthropic response (`DIRECT_LLM`).

The chat interface shows the answer, route, tool name, routing reason when available, and retrieved document/page sources. It supports Enter to send, Shift+Enter for a newline, loading/error states, New Chat, and history restoration after refresh. The frontend calls Flask on the same origin; model credentials and database access stay on the server.

## Architecture and stack

- Client: HTML5, CSS3, vanilla JavaScript, Fetch API; no frontend framework.
- Server: Python 3.12, Flask, LangChain LCEL and `ChatAnthropic`, Anthropic tool-use schemas.
- RAG: pypdf, character chunks with overlap, local `sentence-transformers/all-MiniLM-L6-v2` embeddings, cosine retrieval from pgvector `VECTOR(384)`.
- Persistence: psycopg, PostgreSQL 16 in `pgvector/pgvector:pg16`, UUID sessions, messages and JSONB tool-call logs.
- Tests: pytest, mocked Anthropic/model/database calls for deterministic unit tests, plus separately documented live checks.

See the reproducible Mermaid diagram in [architecture.md](architecture.md).

Provider integration references: [LangChain ChatAnthropic documentation](https://docs.langchain.com/oss/python/integrations/chat/anthropic) and [Anthropic tool definitions](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools).

## Prerequisites and configuration

Use Ubuntu in WSL2 with Python 3.12 and the existing `venv`, Docker Desktop with WSL integration, and Docker Compose. Anthropic generation requires an active API key, network access, and an accessible model ID. The embedding model may need to be downloaded once and then cached locally. Keep your existing `.env` and database credentials if they already work.

For a fresh checkout, copy the example and edit it locally:

```bash
cd ~/SmartCourseAI
cp .env.example .env
```

Do not overwrite an existing `.env`. Replace every placeholder. `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `DATABASE_URL` must describe the same database; URL-encode reserved characters in the URL password. Docker initialization variables do not change users/passwords inside an existing volume. Set `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` to your own active key and a model ID available to your account. No model ID is hardcoded. Never commit `.env` or paste keys into logs/screenshots. If a previous key was exposed, revoke it in the provider console.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | psycopg PostgreSQL connection string |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Docker database initialization; preserve existing credentials |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | Provider credentials and explicitly selected model |
| `HOST`, `PORT` | Flask bind address and port; defaults `127.0.0.1:5000` |
| `FLASK_DEBUG` | Debug flag; keep `false` for normal runs |
| `MAX_MESSAGE_LENGTH` | Server input limit; default 4000 characters |
| `MEMORY_MESSAGES` | Recent context messages; default 20, maximum 30 and 12000 text characters |
| `LLM_TIMEOUT_SECONDS` | Per-provider-attempt timeout; default 30 seconds, allowed 5–120 |
| `LLM_MAX_RETRIES` | SDK retries for transient failures; default 2, maximum 3 |
| `LLM_MAX_TOKENS` | Output token budget; default 1024, allowed 128–4096 |
| `RAG_MIN_SIMILARITY` | Minimum retrieved cosine similarity used as evidence; default 0.25 |

Additional provider/retrieval settings are documented in the comments of `.env.example` when supported. The application loads configuration from the project rather than requiring commands from the `server` directory.

## Install, database, ingestion, and startup

Run from the repository root. Reuse the existing environment; if it is absent, create it with `python3.12 -m venv venv` first.

```bash
cd ~/SmartCourseAI
source venv/bin/activate
pip install -r requirements.txt
docker compose up -d
python -m server.database.migrate
python -m server.rag.ingest knowledge/course_documents/sample_course_notes.pdf
python -m server.app
```

Wait for `docker compose ps` to show a healthy database before migration. The named `smartcourse_postgres_data` volume is preserved; never use `docker compose down -v` to solve schema problems. `migrations/init.sql` runs only for a fresh volume. The migration command applies the required additive schema updates to an existing database without deleting conversations or documents.

Place readable, text-based course PDFs in `knowledge/course_documents/` before ingestion and run the ingestion command once per PDF path. Ingestion stores document/page/chunk metadata and 384-dimensional embeddings. Identical PDF bytes are deduplicated by SHA-256; ingestion performs extraction/embedding first and saves each document and its chunks in a transaction. Changed document contents are indexed as a separate version while older records are preserved. Legacy documents can be adopted only when their filename and ordered text/page metadata exactly match. Verify idempotence against your actual database using the checks in [verification.md](verification.md). Image-only scanned PDFs need OCR before ingestion. Deduplication uses the PDF SHA-256: identical bytes reuse existing chunks; changed PDFs are retained as another version. Retrieval searches indexed versions, so use versioned filenames for revisions.

Open [http://localhost:5000](http://localhost:5000) to use the frontend, and [http://localhost:5000/health](http://localhost:5000/health) to check server/database health. Check existing processes and ports before starting another server; do not stop unrelated processes. The server and database bind locally by default.

## Database schema

| Table | Stored information |
| --- | --- |
| `sessions` | UUID and creation/update timestamps |
| `messages` | Session foreign key, role, content, timestamps, answer metadata where available |
| `tool_calls` | Session, allowlisted tool name, JSONB input/output, failure information and timestamp |
| `documents` | Source filename/title and ingestion metadata |
| `document_chunks` | Document foreign key, index, text, page and `VECTOR(384)` embedding |

Persistence is isolated under `server/database/`; schema updates live under `migrations/`. Older messages created before route metadata was stored can load without a route or sources.

## API contract

| Method and endpoint | Request | Result |
| --- | --- | --- |
| `GET /health` | None | Server/database status; 200 connected, 503 unavailable |
| `POST /sessions` | JSON `{}` | Optional explicit session creation; UUID and 201 before model generation |
| `POST /chat` | JSON `message`, optional existing `session_id` | Full routing, memory, generation and persistence |
| `GET /history?session_id=<uuid>` | Existing UUID | Chronologically ordered message list and saved metadata |
| `POST /rag/search` | JSON `query` | Retrieved content and source/page/similarity metadata |
| `POST /rag/answer` | JSON `query` | Standalone grounded generation and sources |

Start a session explicitly with `POST /sessions` and send the returned UUID to `/chat`, or omit `session_id` from the first `/chat` request for compatibility. The browser creates and remembers the UUID before generation so it can recover history if the first answer is slow or unavailable. An unknown UUID returns 404; it does not silently create a new conversation. Invalid JSON, missing/invalid fields, and invalid UUIDs produce a structured error with an appropriate 4xx status. Provider/database failures use sanitized errors rather than raw exceptions. Error responses have `error` and `code`; an error may also return a created/reused session ID. A user/assistant exchange is saved atomically only after successful generation; tool failures are logged separately.

```bash
curl -s http://localhost:5000/health
curl -s -X POST http://localhost:5000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello, what can you help me with?"}'
```

A successful chat response has the same fields for every route:

```json
{
  "session_id": "<returned-uuid>",
  "answer": "<generated-answer>",
  "route": "RAG",
  "tool": null,
  "sources": [{"document": "<retrieved-filename>", "page": 3, "similarity": 0.703}],
  "routing_reason": "<router-explanation>"
}
```

This JSON illustrates the contract, not an observed answer or retrieval result.

## Router, RAG, tools, and memory

The explicit rule-based router considers the current question and recent conversation context. Grade calculations and structured course-information requests choose their respective tools; lecture/document questions choose RAG; general questions choose the direct path. Follow-ups use relevant history. The route and reason are included in each successful response so the decision can be demonstrated and tested.

RAG retrieves relevant PDF chunks and supplies them as evidence to the LangChain/Anthropic answer chain. Retrieved content is untrusted source data, not permission to run tools or override application instructions. Sources come from retrieval metadata; empty or irrelevant retrieval must be reported honestly rather than filled with invented facts. Similarity measures retrieval closeness, not factual certainty.

The two custom tools are `grade_calculator` and `course_information_lookup`. Anthropic receives tool schemas, arguments are validated, only allowlisted Python functions can execute, results/errors are logged, and the tool result feeds the final model response. Arithmetic is performed by Python: grades 82 at 70% and 95 at 30% produce **85.9**. Grades and weights must be numeric and within 0–100; weights must total 100. Course lookup uses `knowledge/course_info.json`. Unverified example deadlines/weights are not real course facts; missing verified data must produce an honest unavailable result.

Conversation messages are stored by UUID and included in the model context with a bounded recent-history window. The browser remembers `smartcourse_session_id` in localStorage before sending the first question and reloads `/history` after refresh, including stored route/tool/source metadata. Client requests have a five-minute timeout; after an answer timeout, Retry history checks whether the backend eventually saved a response. New Chat clears that browser reference; it does not erase the old database conversation. A failed history reload can be retried before sending more messages.

## Testing, demonstration, and limitations

```bash
cd ~/SmartCourseAI
source venv/bin/activate
pytest -q
```

Routine tests mock external generation and do not make paid Anthropic calls. Their success does not prove that local Docker, a PDF embedding download, or live provider credentials work. Record executed commands and actual outcomes in [verification.md](verification.md). Use [demo.md](demo.md) for the required RAG, tool and direct-answer demonstration. [reflection.md](reflection.md) contains the reflection on the implementation, challenges and future improvements.

Opt-in local database/RAG checks and paid live Anthropic checks are separate:

```bash
env SMARTCOURSE_INTEGRATION_TESTS=1 pytest -q -m 'integration and not live'
env SMARTCOURSE_INTEGRATION_TESTS=1 SMARTCOURSE_LIVE_TESTS=1 pytest -q -m live
```

The live command invokes the configured model and consumes API usage. Recent model context is limited to at most 30 messages and 12,000 characters even if a larger history limit is configured.

Example prompts: “How do I authenticate with the Anthropic Python SDK according to the course PDF?”, “My exam grade is 82 with weight 70%, and my project grade is 95 with weight 30%. Calculate my final grade.”, “When is the Final Project deadline?”, and “Hello, what can you help me with?”

This local academic prototype has no user authentication: a session UUID is a bearer reference, and anyone who obtains it can retrieve that chat. Do not use it for sensitive student records or publish it as a multi-user service without authentication/authorization, TLS and deployment controls. Rule-based routing can misclassify ambiguous questions; retrieval beyond the supplied English demonstration material has not been evaluated against a labeled course dataset; history sent to the model is bounded; OCR is not implemented. Anthropic generation depends on account access and network availability. Live tests and browser checks passed; see the dated verification record for exact results and limits. Verified course deadlines are optional: without official data, the lookup intentionally reports information unavailable.
