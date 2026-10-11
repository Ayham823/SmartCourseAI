"""One response contract for every successful routing path."""


def format_response(session_id, answer, route, tool=None, sources=None, routing_reason=None):
    if route not in {"RAG", "TOOL", "DIRECT_LLM"}:
        raise ValueError("Unsupported response route.")
    return {
        "session_id": str(session_id),
        "answer": answer,
        "route": route,
        "tool": tool if route == "TOOL" else None,
        "sources": list(sources or []) if route == "RAG" else [],
        "routing_reason": routing_reason,
    }
