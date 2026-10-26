# Retrieval evaluation — October 26, 2026

This benchmark executes the real bundled PDF ingestion, local `all-MiniLM-L6-v2` embeddings and PostgreSQL/pgvector cosine search. It uses the application's follow-up-query rewrite and default five-chunk limit / 0.25 similarity gate. **It does not call Anthropic or evaluate generated-answer quality.**

## Dataset and results

[The dataset](../evaluation/retrieval_cases.json) contains 24 manually labeled English questions about the repository's original three-page sample handout: 16 answerable cases and 8 unanswerable cases. Cases include paraphrases, conversation follow-ups, a multi-page question, absent personal/course facts, unrelated questions and adversarial wording. The PDF produces only **four chunks**; this is a small diagnostic fixture, not a production accuracy estimate or held-out benchmark.

The [observed raw report](../evaluation/results/2026-10-26.json) records corpus/dataset/source hashes, model revision, dependency versions, per-case ranked pages/similarities, and metrics at cutoffs 1, 3 and 5.

| Measure | Observed result |
| --- | --- |
| Expected evidence page appears at rank 1 | 16/16 answerable questions |
| Page recall@5 / MRR@5 | 1.00 / 1.00 |
| Relevant evidence survives the 0.25 gate | 14/16 (87.5%) |
| Unanswerable questions rejected by the gate | 6/8 (75%) |
| Unanswerable questions incorrectly accepted by the gate | 2/8 |

With four chunks, recall@5 retrieves the whole corpus and is weak evidence by itself. The gate failures matter more:

- The router-path and tool-allowlist questions retrieve the expected page first but score below 0.25. The application can reject useful evidence.
- The questions asking for the student's actual grade and the value of a production API key score above 0.25 despite those facts being absent. Related text is not sufficient evidence of the requested fact.

These are **retrieval-gate false accepts**, not observed hallucinated answers: generation was not invoked. Raising the threshold also rejects more answerable cases, as the report's exploratory threshold table shows. No application threshold was tuned against these same questions.

## Reproduce without provider credentials

Install the committed Python requirements. Cache the public embedding model once in a separate explicit online step:

```bash
python -c 'from sentence_transformers import SentenceTransformer; SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")'
```

Provision a **new, empty, local** PostgreSQL database with pgvector available, named `smartcourse_eval_...`. Never point this evaluation at an existing project database. Set `DATABASE_URL` privately to that disposable loopback database and opt in:

```bash
export SMARTCOURSE_EVAL_DISPOSABLE_DB=1
python -m evaluation.retrieval --output evaluation/results/local.json
python -m pytest -q
```

The evaluator rejects non-loopback/unapproved database names and non-empty databases. It disables dotenv and model downloads before importing application modules, and does not reset/delete any corpus. It uses the cached embedding model. No provider credential is required. CI provisions its own fresh pgvector service, caches the embedding weights, runs the same command and uploads the JSON artifact.

## What remains

- Collect a larger independently labeled corpus and held-out questions, including ambiguous and missing-fact queries. Keep tuning and final evaluation separate.
- Evaluate a reranker or evidence-sufficiency stage with both recall and unanswerable false-accept metrics, rather than treating cosine similarity as truth.
- Once fresh provider credentials are available, separately evaluate factual support, citation precision, appropriate abstention and prompt-injection behavior of actual generated answers. This run makes no claim about those measures.
- The application remains a local academic prototype without multi-user authentication; do not expose conversation endpoints publicly as a hosted demo without access controls.

CI writes metrics into the job summary and logs. Raw artifact archival is best-effort: a full account artifact quota must not change the outcome of mandatory tests or evaluation. No existing artifacts are deleted automatically.
