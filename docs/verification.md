> **Historical academic submission verification (2026-10-09).** This record documents the original course-document environment. The public portfolio edition uses a newly authored sample PDF and must be tested separately before claiming that all integration/live results reproduce on the sample.

# Verification record / תיעוד אימות

Executed on **2026-10-09**, in WSL2 Ubuntu with the existing Python 3.12 virtual environment and Docker PostgreSQL. Results below are observed checks, not historical assumptions. No existing tables, documents, conversations or Docker volumes were deleted.

הבדיקות בוצעו ב-**09.10.2026** ב-WSL2 Ubuntu, בסביבת Python 3.12 הקיימת ובמסד PostgreSQL בתוך Docker. אלו תוצאות שנצפו בפועל. לא נמחקו טבלאות, מסמכים, שיחות או נפחי Docker קיימים.

| Check | Observed result |
| --- | --- |
| Existing Docker database | `smartcourse-db` healthy; pgvector/pgvector:pg16; localhost port5432 |
| `docker compose up -d` after configuration update | Succeeded; same data volume retained; container healthy |
| Database schema/migrations | `001_persistence.sql` applied safely; repeat migration returns none; embedding column `vector(384)` |
| Existing document preservation | 1 document and 11 chunks before and after migration, re-ingestion and live checks |
| Dependencies | `python -m pip check`: no broken requirements |
| Deterministic Python suite | 149 passed, 7 opt-in tests skipped in 2.78 s; those 7 were executed separately below |
| Real PostgreSQL/RAG integration, mocked Anthropic | 6 passed in 19.44 s on the final original repository: migration repeat, ingestion repeat, actual float32 embeddings of dimension 384 and vector retrieval, persisted tool results/errors, history/source metadata |
| Real Anthropic | 1 live test passed in 38.53 s on the final original repository; covers DIRECT_LLM, Grade Calculator 85.9, Course Lookup, RAG with sources and a same-session follow-up |
| Flask startup and HTTP health | Started successfully; debug disabled; `/health`200 with database connected |
| Browser grade calculation | Actual answer 85.9; `TOOL: Grade Calculator` visible; loading disables controls |
| Browser RAG and refresh | Actual PDF answer; route RAG; page 3 similarity 0.703, pages 9/2/1/4 also supplied; messages/metadata/sources survived refresh |
| Browser keyboard/errors/New Chat | Enter sends; Shift+Enter retains newline; empty-input error visible; New Chat resets active view |
| Responsive browser | At 390×844: document width 390, no horizontal overflow |
| Client syntax/safe rendering | `node --check client/app.js` passed; content and source metadata rendered as text; simulated DOM checks passed |
| Active key scan | No active Anthropic key found in project files outside `.env`; excluded venv, caches and backups |
| Git history | Original project has no `.git`; historical commit audit unavailable |
| Bilingual deliverables | English/Hebrew README, Mermaid architecture, reflection, demo and implementation checklist prepared |

## Reproduce the checks / שחזור הבדיקות

```bash
cd ~/SmartCourseAI
source venv/bin/activate
python -m pip check
pytest -q
env SMARTCOURSE_INTEGRATION_TESTS=1 pytest -q -m 'integration and not live'
# Opt-in: the following consumes Anthropic API credits.
env SMARTCOURSE_INTEGRATION_TESTS=1 SMARTCOURSE_LIVE_TESTS=1 pytest -q -m live
```

Normal pytest runs mock external services. Database integration checks intentionally retain their newly created demonstration sessions and logs; they do not erase earlier records. Live tests use the configured model/key and are never enabled automatically.

בדיקות רגילות מדמות שירותים חיצוניים. בדיקות המסד שומרות שיחות ויומנים חדשים של ההדגמה ואינן מוחקות מידע קודם. בדיקות ספק חיות משתמשות בהגדרות הקיימות ומופעלות רק במפורש.

## Grading rubric / מחוון

| Component | Weight | Evidence |
| --- | --- | --- |
| Client–Server–DB integration |15%| Actual HTTP/browser chat, refreshed history and PostgreSQL records |
| Docker setup |10%| Compose startup, healthy container and preserved data volume |
| Agent Router |20%| Explicit rule-based three-path router; live route labels; automated router cases |
| RAG pipeline |20%| Idempotent PDF ingestion,384-dimensional vectors, cosine retrieval, live answer and sources |
| Tools implementation |15%| Anthropic schemas, Python arithmetic, verified-data lookup, successful/failed persisted calls |
| LCEL, memory, error handling |10%| Prompt/model/parser chains, live follow-up, bounded history and sanitized error tests |
| Documentation/diagram |10%| English/Hebrew README and reproducible Mermaid diagram; reflection and demo |

## Limits and user review / מגבלות ובדיקת המשתמש

- No verified course deadlines/weights were supplied. The lookup correctly returns unavailable information rather than invented records. Add official records marked`verified:true` only when known.
- This local academic prototype has no user authentication; possession of a UUID grants access to its conversation. Hebrew MiniLM retrieval quality is limited, and scanned PDFs need external OCR.
- Review the reflection in your own words and perform the demonstration using`demo.md` for submission.
- Revocation of the older exposed API key cannot be verified from the available local environment. The current key works and was kept private; confirm old-key revocation in the provider console.
- Final session preflight (/sessions), plain-text model output and DIRECT_LLM history refresh were also checked in the browser. All 156 test cases passed across the three explicit test runs; routine pytest intentionally skips the 7 opt-in cases.

מידע רשמי על מועדים ומשקלים לא סופק; הכלי מחזיר מידע לא זמין. האבטיפוס מקומי וללא אימות משתמשים. יש לעבור על הרפלקציה ולבצע את ההדגמה להגשה. ביטול המפתח הישן שנחשף לא ניתן לאימות מהסביבה המקומית; המפתח הפעיל פועל ונשמר פרטי.

