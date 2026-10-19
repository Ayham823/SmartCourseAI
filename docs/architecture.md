# Architecture

The source below is reproducible Mermaid. It describes the implemented modules and their intended runtime flow; live execution evidence belongs in `verification.md`.

```mermaid
flowchart TD
    C[HTML CSS JavaScript client] -->|REST JSON same origin| F[Flask endpoints]
    F --> V[Validate request and session]
    V --> M[Load bounded recent conversation]
    M --> A[Explicit Agent Router]
    A -->|RAG| R[Embed query and retrieve PDF chunks]
    A -->|TOOL| TP[LCEL tool selection prompt]
    TP --> TC[ChatAnthropic with selected tool schema]
    TC --> T[Anthropic tool call arguments]
    A -->|DIRECT_LLM| D[Direct conversation prompt]
    T --> E[Validate and execute allowlisted Python tool]
    E --> TR[Tool result or structured failure]
    R --> L[LangChain LCEL prompt and ChatAnthropic]
    TR --> L
    D --> L
    L --> AN[Configured Anthropic model]
    AN --> O[Central response formatter]
    O --> P[Persist messages and response metadata]
    P -->|answer route tool sources reason| C
    V <-->|UUID sessions| DB[(PostgreSQL in Docker)]
    M <-->|ordered messages| DB
    E -->|input output and failure logs| DB
    P --> DB
    R <-->|cosine search VECTOR 384| DB
    PDF[Course PDFs] --> X[pypdf text and page extraction]
    X --> CH[Overlapping text chunks]
    CH --> EM[MiniLM embeddings dimension 384]
    EM -->|documents and document_chunks| DB
    CI[Verified course_info JSON] --> E
```

`server/agent/` owns routing, `server/rag/` owns ingestion/retrieval, `server/tools/` owns the tool schemas and execution, `server/llm/` owns orchestration, and `server/database/` owns persistence. The client has no direct connection to Anthropic or PostgreSQL.
