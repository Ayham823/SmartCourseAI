# Local demonstration — SmartCourse AI

This walkthrough uses the original sample document bundled with the **public** repository. It is not a prerecorded demo video.

## Preparation

```bash
cp .env.example .env              # replace values with your own, do not commit .env
python -m server.database.migrate
python -m server.rag.ingest knowledge/course_documents/sample_course_notes.pdf
python -m server.app
```

Ensure Docker PostgreSQL is healthy before running migrations. Open http://localhost:5000.

## Three routing paths

1. **RAG:** Ask `How do I authenticate with the Anthropic Python SDK according to the sample course PDF?`. Verify that the answer shows `RAG` and cites `sample_course_notes.pdf` with page numbers. A follow-up like `What is the main security precaution?` should preserve contextual routing.
2. **Tool:** Start a new chat. Ask `My exam grade is 82 with weight 70%, and project 95 with weight 30%. Calculate my final grade.` Verify `TOOL: Grade Calculator` and `85.9`. This calculation happens in Python and is recorded in PostgreSQL.
3. **Direct LLM:** Start a new chat. Ask `Hello, what can you help me with?`. Verify `DIRECT_LLM` without fabricated citations.

Refresh the browser to confirm history, sources and route metadata remain visible. No verified assignment deadlines are bundled; the course-lookup tool should say when this information is unavailable.

## Tests

```bash
python -m pytest -q
SMARTCOURSE_INTEGRATION_TESTS=1 python -m pytest -q -m 'integration and not live'
```

Keep `.env` private, and do not run paid live Anthropic tests unless you intend to use API credits.
