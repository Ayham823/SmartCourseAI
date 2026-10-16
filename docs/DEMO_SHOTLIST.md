# Five-minute portfolio walkthrough (local demo)

This is a **reproducible demo script**, not a video or a hosted deployment. The public repo includes a [real development screenshot](demo-ui.png); do not mistake it for a public live service.

## Before recording

1. Follow [README setup](../README.md#getting-started-local-development), configure your **own** Anthropic API key outside Git, start Docker PostgreSQL, run the migration, and ingest `knowledge/course_documents/sample_course_notes.pdf`.
2. Start `python -m server.app` and open `http://localhost:5000`.
3. Avoid showing API keys, environment files, student records, private course PDFs, or real usernames during screen capture. Use only the bundled original sample.
4. Keep the server on localhost; this prototype does not have user authentication.

## Suggested recording sequence

| Approximate time | Screen/action | Engineering evidence |
| --- | --- | --- |
| 0:00–0:30 | Display the architecture diagram and working local app | Flask API, agent router, pgvector database, browser |
| 0:30–1:45 | Ask a question grounded in the bundled sample PDF | `RAG` route and answer with filename/page citations |
| 1:45–2:40 | New chat: `Exam 82 (70%), Project 95 (30%). Calculate my final grade.` | `TOOL: Grade Calculator`, expected result `85.9` |
| 2:40–3:20 | New chat: a general greeting | `DIRECT_LLM` route, no invented sources |
| 3:20–4:00 | Refresh and show persisted messages and metadata | Session persistence and response formatting |
| 4:00–5:00 | Show `pytest -q`, the GitHub Actions page, and known limitations | Reproducible deterministic tests and transparent security scope |

The listed outcomes are expected behavior based on the project's existing documentation; **verify them in your own environment before making a new recording or claiming a fresh pass**.

## Publish checklist

- [ ] Record an actual video or GIF of your local demo (no fabricated screenshots).
- [ ] Inspect every frame for sensitive data and identifiable student information.
- [ ] Add only the reviewed media to `docs/`; update README with its actual path.
- [ ] Run `python -m pytest -q`; capture new results with their date.
- [ ] Verify any older leaked Anthropic key is revoked in its provider console.

See [the full demo steps](demo.md) and [historical verification](verification.md).