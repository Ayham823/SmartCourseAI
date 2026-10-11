# SmartCourse AI — Agentic Study Assistant

English documentation is followed by Hebrew documentation. Verification evidence is recorded separately in [verification.md](verification.md); an implemented feature is not proof that a live integration has passed.

## English

### Purpose and features

SmartCourse AI is a university-course study assistant for students. It keeps the existing three-tier architecture: a plain HTML/CSS/JavaScript client, a Python Flask REST server, and Dockerized PostgreSQL with pgvector. Every chat question passes through an explicit Agent Router, which chooses document retrieval (`RAG`), an approved custom tool (`TOOL`), or a general Anthropic response (`DIRECT_LLM`).

The chat interface shows the answer, route, tool name, routing reason when available, and retrieved document/page sources. It supports Enter to send, Shift+Enter for a newline, loading/error states, New Chat, and history restoration after refresh. The frontend calls Flask on the same origin; model credentials and database access stay on the server.

### Architecture and stack

- Client: HTML5, CSS3, vanilla JavaScript, Fetch API; no frontend framework.
- Server: Python 3.12, Flask, LangChain LCEL and `ChatAnthropic`, Anthropic tool-use schemas.
- RAG: pypdf, character chunks with overlap, local `sentence-transformers/all-MiniLM-L6-v2` embeddings, cosine retrieval from pgvector `VECTOR(384)`.
- Persistence: psycopg, PostgreSQL 16 in `pgvector/pgvector:pg16`, UUID sessions, messages and JSONB tool-call logs.
- Tests: pytest, mocked Anthropic/model/database calls for deterministic unit tests, plus separately documented live checks.

See the reproducible Mermaid diagram in [architecture.md](architecture.md).

Provider integration references: [LangChain ChatAnthropic documentation](https://docs.langchain.com/oss/python/integrations/chat/anthropic) and [Anthropic tool definitions](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools).

### Prerequisites and configuration

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

### Install, database, ingestion, and startup

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

### Database schema

| Table | Stored information |
| --- | --- |
| `sessions` | UUID and creation/update timestamps |
| `messages` | Session foreign key, role, content, timestamps, answer metadata where available |
| `tool_calls` | Session, allowlisted tool name, JSONB input/output, failure information and timestamp |
| `documents` | Source filename/title and ingestion metadata |
| `document_chunks` | Document foreign key, index, text, page and `VECTOR(384)` embedding |

Persistence is isolated under `server/database/`; schema updates live under `migrations/`. Older messages created before route metadata was stored can load without a route or sources.

### API contract

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

### Router, RAG, tools, and memory

The explicit rule-based router considers the current question and recent conversation context. Grade calculations and structured course-information requests choose their respective tools; lecture/document questions choose RAG; general questions choose the direct path. Follow-ups use relevant history. The route and reason are included in each successful response so the decision can be demonstrated and tested.

RAG retrieves relevant PDF chunks and supplies them as evidence to the LangChain/Anthropic answer chain. Retrieved content is untrusted source data, not permission to run tools or override application instructions. Sources come from retrieval metadata; empty or irrelevant retrieval must be reported honestly rather than filled with invented facts. Similarity measures retrieval closeness, not factual certainty.

The two custom tools are `grade_calculator` and `course_information_lookup`. Anthropic receives tool schemas, arguments are validated, only allowlisted Python functions can execute, results/errors are logged, and the tool result feeds the final model response. Arithmetic is performed by Python: grades 82 at 70% and 95 at 30% produce **85.9**. Grades and weights must be numeric and within 0–100; weights must total 100. Course lookup uses `knowledge/course_info.json`. Unverified example deadlines/weights are not real course facts; missing verified data must produce an honest unavailable result.

Conversation messages are stored by UUID and included in the model context with a bounded recent-history window. The browser remembers `smartcourse_session_id` in localStorage before sending the first question and reloads `/history` after refresh, including stored route/tool/source metadata. Client requests have a five-minute timeout; after an answer timeout, Retry history checks whether the backend eventually saved a response. New Chat clears that browser reference; it does not erase the old database conversation. A failed history reload can be retried before sending more messages.

### Testing, demonstration, and limitations

```bash
cd ~/SmartCourseAI
source venv/bin/activate
pytest -q
```

Routine tests mock external generation and do not make paid Anthropic calls. Their success does not prove that local Docker, a PDF embedding download, or live provider credentials work. Record executed commands and actual outcomes in [verification.md](verification.md). Use [demo.md](demo.md) for the required RAG, tool and direct-answer demonstration. [reflection.md](reflection.md) contains the English and Hebrew reflection on the implementation, challenges and future improvements.

Opt-in local database/RAG checks and paid live Anthropic checks are separate:

```bash
env SMARTCOURSE_INTEGRATION_TESTS=1 pytest -q -m 'integration and not live'
env SMARTCOURSE_INTEGRATION_TESTS=1 SMARTCOURSE_LIVE_TESTS=1 pytest -q -m live
```

The live command invokes the configured model and consumes API usage. Recent model context is limited to at most 30 messages and 12,000 characters even if a larger history limit is configured.

Example prompts: “How do I authenticate with the Anthropic Python SDK according to the course PDF?”, “My exam grade is 82 with weight 70%, and my project grade is 95 with weight 30%. Calculate my final grade.”, “When is the Final Project deadline?”, and “Hello, what can you help me with?”

This local academic prototype has no user authentication: a session UUID is a bearer reference, and anyone who obtains it can retrieve that chat. Do not use it for sensitive student records or publish it as a multi-user service without authentication/authorization, TLS and deployment controls. Rule-based routing can misclassify ambiguous questions; Hebrew retrieval has not been evaluated against a labeled course dataset; history sent to the model is bounded; OCR is not implemented. Anthropic generation depends on account access and network availability. Live tests and browser checks passed; see the dated verification record for exact results and limits. Verified course deadlines are optional: without official data, the lookup intentionally reports information unavailable.

## עברית

### מטרת הפרויקט והיכולות

SmartCourse AI הוא עוזר לימודי לסטודנטים בקורס אוניברסיטאי. המערכת שומרת על ארכיטקטורה בת שלוש שכבות: לקוח HTML/CSS/JavaScript ללא מסגרת עבודה, שרת Flask ב-Python ומסד PostgreSQL עם pgvector בתוך Docker. כל שאלה עוברת דרך Agent Router מפורש, שבוחר שליפת מסמכי קורס (`RAG`), כלי מאושר (`TOOL`) או תשובה כללית של Anthropic (`DIRECT_LLM`).

ממשק השיחה מציג תשובה, מסלול, שם כלי, הסבר לניתוב כשקיים ומקורות עם שם מסמך ומספר עמוד. Enter שולח הודעה ו-Shift+Enter מוסיף שורה. הממשק כולל מצב טעינה, הודעות שגיאה, שיחה חדשה ושחזור היסטוריה לאחר רענון. הלקוח מתקשר עם Flask באמצעות REST/JSON מאותו מקור; מפתחות API וגישה למסד נשארים בשרת.

### ארכיטקטורה וטכנולוגיות

- לקוח: HTML5, CSS3, JavaScript רגיל ו-Fetch API.
- שרת: Python 3.12, Flask, LangChain LCEL, `ChatAnthropic` וסכמות כלים של Anthropic.
- RAG: חילוץ טקסט עם pypdf, חלוקה למקטעים עם חפיפה, embeddings מקומיים של `sentence-transformers/all-MiniLM-L6-v2` ושליפה לפי cosine באמצעות pgvector בעמודת `VECTOR(384)`.
- אחסון: psycopg, PostgreSQL 16 בתמונת `pgvector/pgvector:pg16`, שיחות UUID, הודעות ויומני כלים ב-JSONB.
- בדיקות: pytest עם חיקוי של שירותים חיצוניים ובדיקות חיות שמתועדות בנפרד.

תרשים Mermaid שניתן לשחזר נמצא ב-[architecture.md](architecture.md).

מקורות טכניים רשמיים: [תיעוד ChatAnthropic של LangChain](https://docs.langchain.com/oss/python/integrations/chat/anthropic) ו-[הגדרת כלים של Anthropic](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools).

### דרישות מקדימות והגדרת סביבה

נדרשים Ubuntu בתוך WSL2, Python 3.12 וסביבת `venv`, וכן Docker Desktop עם שילוב WSL ו-Docker Compose. יצירת תשובות דורשת מפתח Anthropic פעיל, חיבור רשת ומזהה מודל זמין לחשבון. מודל ה-embeddings עשוי לדרוש הורדה ראשונה ושמירה במטמון.

בעותק חדש של הפרויקט:

```bash
cd ~/SmartCourseAI
cp .env.example .env
```

אין להחליף `.env` קיים שכבר עובד. יש להחליף את כל ערכי הדוגמה. `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` ו-`DATABASE_URL` צריכים לתאר אותו מסד. תווים מיוחדים בסיסמת URL דורשים קידוד מתאים. שינוי משתני האתחול של Docker אינו משנה סיסמה או משתמש שכבר נשמרו בנפח קיים. הגדירו `ANTHROPIC_API_KEY` ומזהה מודל זמין ב-`ANTHROPIC_MODEL`; המודל אינו מקובע בקוד. אין להעלות `.env` ל-Git או לחשוף מפתחות בצילום מסך או ביומן. מפתח שנחשף בעבר צריך להישלל במסוף הספק.

| משתנה | תפקיד |
| --- | --- |
| `DATABASE_URL` | מחרוזת חיבור ל-PostgreSQL |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | אתחול Docker; לשמור על פרטי נפח קיים |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | הרשאה ומודל שנבחר במפורש |
| `HOST`, `PORT` | כתובת ופורט Flask; ברירת מחדל `127.0.0.1:5000` |
| `FLASK_DEBUG` | להשאיר `false` בהרצה רגילה |
| `MAX_MESSAGE_LENGTH` | מגבלת קלט בשרת; ברירת מחדל 4000 תווים |
| `MEMORY_MESSAGES` | מספר הודעות אחרונות שנשלחות כזיכרון; ברירת מחדל 20 |
| `LLM_TIMEOUT_SECONDS` | זמן ניסיון ספק; ברירת מחדל 30 שניות, טווח 5–120 |
| `LLM_MAX_RETRIES` | ניסיונות חוזרים של SDK לכשלים זמניים; ברירת מחדל 2, עד 3 |
| `LLM_MAX_TOKENS` | מגבלת פלט; ברירת מחדל 1024, טווח 128–4096 |
| `RAG_MIN_SIMILARITY` | ציון cosine מינימלי למקטע ראיות; ברירת מחדל 0.25 |

הגדרות נוספות נתמכות מתועדות בהערות של `.env.example`. הפקודות הבאות מורצות משורש הפרויקט.

### התקנה, Docker, מסד, טעינת PDF והרצה

יש להשתמש בסביבת העבודה הקיימת. אם היא אינה קיימת, ליצור אותה עם `python3.12 -m venv venv`.

```bash
cd ~/SmartCourseAI
source venv/bin/activate
pip install -r requirements.txt
docker compose up -d
python -m server.database.migrate
python -m server.rag.ingest knowledge/course_documents/sample_course_notes.pdf
python -m server.app
```

לפני migration יש לבדוק ב-`docker compose ps` שהמסד במצב healthy. הנפח `smartcourse_postgres_data` נשמר. אין להריץ `docker compose down -v` כדי לפתור בעיית סכימה. `migrations/init.sql` מורץ רק באתחול נפח חדש; פקודת ה-migration מעדכנת מסד קיים באופן מצטבר ללא מחיקת שיחות ומסמכים.

יש לשים מסמכי PDF עם טקסט קריא ב-`knowledge/course_documents/` ולהריץ טעינה לכל נתיב PDF. המערכת שומרת מקור, עמוד, מקטע ווקטור באורך 384. קובץ בעל תוכן בינרי זהה מזוהה באמצעות SHA-256 ואינו נטען שוב. חילוץ הטקסט ויצירת הווקטורים קודמים לשמירה בעסקה אחת. תוכן ששונה נטען כגרסה נוספת, בלי למחוק את הישנה. מסמך ישן ללא hash מאומץ רק כאשר שם הקובץ, הטקסט וסדר העמודים תואמים בדיוק. יש לאמת זאת במסד לפי [verification.md](verification.md). מסמך סרוק שמכיל תמונות בלבד דורש OCR חיצוני. מניעת כפילויות מבוססת SHA-256: תוכן זהה משתמש במקטעים הקיימים; PDF שהשתנה נשמר כגרסה נוספת. השליפה מחפשת בגרסאות המאונדקסות, ולכן מומלץ לציין גרסה בשם הקובץ.

הממשק זמין ב-[http://localhost:5000](http://localhost:5000), ובדיקת הבריאות ב-[http://localhost:5000/health](http://localhost:5000/health). יש לבדוק תהליכים ופורטים קיימים לפני הפעלת שרת נוסף ולא לעצור תהליכים שאינם קשורים לפרויקט. ברירת המחדל היא חיבור מקומי.

### סכימת מסד הנתונים

| טבלה | מידע |
| --- | --- |
| `sessions` | UUID ומועדי יצירה ועדכון |
| `messages` | מזהה שיחה, תפקיד, תוכן, זמן ומטא-נתונים של התשובה כשקיימים |
| `tool_calls` | שיחה, שם כלי מאושר, קלט ופלט JSONB, מידע כשל וזמן |
| `documents` | שם מקור, כותרת ומטא-נתונים של טעינה |
| `document_chunks` | מסמך, אינדקס, תוכן, עמוד ו-`VECTOR(384)` |

קוד האחסון מופרד ב-`server/database/`, ושינויי סכימה נמצאים ב-`migrations/`. הודעות ישנות שנוצרו לפני שמירת מטא-נתונים עשויות להיטען ללא מסלול או מקורות.

### תיעוד API

| שיטה וכתובת | קלט | פלט |
| --- | --- | --- |
| `GET /health` | ללא קלט | מצב שרת ומסד; 200 בהצלחה ו-503 כשאין חיבור |
| `POST /sessions` | JSON `{}` | יצירת שיחה מפורשת אופציונלית; UUID ו-201 לפני יצירת תשובה |
| `POST /chat` | JSON עם `message` ומזהה קיים אופציונלי `session_id` | ניתוב, זיכרון, יצירת תשובה ושמירה |
| `GET /history?session_id=<uuid>` | מזהה קיים | הודעות בסדר כרונולוגי ומטא-נתונים שנשמרו |
| `POST /rag/search` | JSON עם `query` | מקטעים, מקורות, עמודים וציוני דמיון |
| `POST /rag/answer` | JSON עם `query` | תשובה מבוססת מסמכים ומקורות |

ליצירת שיחה מפורשת שולחים `POST /sessions` ואז את ה-UUID שהוחזר ל-`/chat`; לתאימות אפשר גם להשמיט `session_id` מבקשת `/chat` הראשונה. הדפדפן יוצר ושומר UUID לפני יצירת התשובה כדי שיוכל לשחזר היסטוריה גם אם התשובה הראשונה איטית או נכשלת. מזהה שאינו קיים מחזיר 404 ואינו יוצר שיחה בשקט. JSON פגום, שדות לא תקינים ומזהים לא תקינים מחזירים שגיאה מובנית וקוד 4xx מתאים. שגיאות ספק ומסד מוחזרות ללא חריגות פנימיות או סודות. שגיאה מכילה `error` ו-`code`, ולעיתים מזהה שיחה שנוצרה או שנעשה בה שימוש. זוג הודעות משתמש ועוזר נשמר בעסקה אחת רק לאחר יצירת תשובה מוצלחת; כשלי כלים נשמרים ביומן נפרד.

```bash
curl -s http://localhost:5000/health
curl -s -X POST http://localhost:5000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello, what can you help me with?"}'
```

תשובה מוצלחת כוללת `session_id`, `answer`, `route`, `tool`, `sources` ו-`routing_reason`. המקורות כוללים שם מסמך, עמוד וציון דמיון כשזמין. דוגמת ה-JSON בחלק האנגלי מתארת חוזה API בלבד, ולא תוצאת בדיקה חיה.

### ניתוב, RAG, כלים וזיכרון

הנתב מבוסס כללים ונעזר בשאלה ובהקשר השיחה האחרון. שאלות על חישוב ציונים ומידע מובנה על הקורס מופנות לכלי המתאים; שאלות על הרצאות ומסמכים מופנות ל-RAG; שאלות כלליות מופנות ליצירה ישירה. שאלות המשך משתמשות בהיסטוריה רלוונטית. המסלול והסבר הבחירה נכללים בתשובה.

ב-RAG נשלפים מקטעי PDF רלוונטיים ונשלחים כראיות לשרשרת LangChain/Anthropic. המסמכים הם נתוני מקור שאינם מהימנים כהוראות, ואינם רשאים לשנות את מדיניות הכלים. המקורות מגיעים ממטא-נתוני השליפה; בהיעדר מקורות רלוונטיים יש לציין זאת בלי להמציא מידע. ציון דמיון אינו הוכחה לנכונות עובדתית.

שני הכלים הם `grade_calculator` ו-`course_information_lookup`. המודל מקבל סכמות כלים, הארגומנטים עוברים אימות, רק פונקציות Python מאושרות רצות, והפלט או השגיאה נשמרים ביומן לפני יצירת התשובה. החישוב נעשה ב-Python: ציון 82 במשקל 70% וציון 95 במשקל 30% נותנים **85.9**. ציונים ומשקלים חייבים להיות מספריים בטווח 0–100; סכום המשקלים חייב להיות 100. כלי המידע משתמש ב-`knowledge/course_info.json`. תאריכים ומשקלים לדוגמה שלא אומתו אינם עובדות על הקורס; מידע שלא אומת מוחזר כלא זמין.

הודעות נשמרות לפי UUID, והקשר השיחה שמועבר למודל מוגבל למספר הודעות אחרונות. הדפדפן שומר `smartcourse_session_id` ב-localStorage לפני שליחת השאלה הראשונה וטוען `/history` לאחר רענון, כולל מטא-נתוני מסלול, כלי ומקורות. מגבלת זמן בקשת לקוח היא חמש דקות; אחרי חריגה אפשר להשתמש ב-Retry history כדי לבדוק אם השרת שמר תשובה בהמשך. שיחה חדשה מאפסת את ההפניה בדפדפן ואינה מוחקת את השיחה הישנה במסד. לאחר כשל בטעינת היסטוריה אפשר לנסות שוב לפני שליחת הודעות נוספות.

### בדיקות, הדגמה ומגבלות

```bash
cd ~/SmartCourseAI
source venv/bin/activate
pytest -q
```

בדיקות שגרתיות מדמות שירותים חיצוניים ואינן מבצעות קריאות Anthropic בתשלום. הצלחתן אינה מוכיחה ש-Docker המקומי, הורדת מודל embeddings או מפתח הספק עובדים. תוצאות של פקודות שבוצעו נרשמות ב-[verification.md](verification.md). תסריט שלוש ההדגמות נמצא ב-[demo.md](demo.md), ורפלקציה באנגלית ובעברית על המימוש, האתגרים והשיפורים האפשריים נמצאת ב-[reflection.md](reflection.md).

בדיקות מקומיות ובדיקות Anthropic חיות מופעלות בנפרד ובמפורש:

```bash
env SMARTCOURSE_INTEGRATION_TESTS=1 pytest -q -m 'integration and not live'
env SMARTCOURSE_INTEGRATION_TESTS=1 SMARTCOURSE_LIVE_TESTS=1 pytest -q -m live
```

הפקודה החיה משתמשת במודל שהוגדר וצורכת שימוש API. הקשר המודל מוגבל לעד 30 הודעות ו-12,000 תווים גם כאשר הוגדר חלון היסטוריה גדול יותר.

שאלות לדוגמה: כיצד מבצעים אימות ב-Anthropic Python SDK לפי מסמך הקורס? מהו הציון הסופי עבור 82 במשקל 70% ו-95 במשקל 30%? מתי מועד ההגשה של פרויקט הגמר? במה אפשר לעזור לי ללמוד?

זהו אבטיפוס אקדמי מקומי ללא אימות משתמשים: מי שמחזיק UUID של שיחה יכול לקרוא אותה. אין להשתמש בו למידע רגיש על סטודנטים או לפרסם אותו כשירות רב-משתמשים ללא אימות והרשאות, TLS והגדרות פריסה מתאימות. הנתב עשוי לטעות בשאלות עמומות, שליפה בעברית טרם הוערכה מול אוסף נתוני קורס מתויג, הקשר השיחה חסום באורכו ו-OCR אינו כלול. יצירת תשובות תלויה בזמינות חשבון Anthropic וברשת. בדיקות חיות ובדיקות דפדפן עברו; התוצאות והמגבלות מתועדות בקובץ האימות המתוארך. נתוני מועדים רשמיים הם אופציונליים: בהיעדר מידע מאומת כלי הקורס מדווח שהמידע אינו זמין.


