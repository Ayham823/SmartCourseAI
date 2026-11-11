"""Grounded answers with source metadata preserved for conversation history."""

import os
import re

from server.errors import AppError
from server.agent.router import AgentRouter
from server.llm.chain import generate_rag_answer
from server.rag.retriever import retrieve_chunks


def _retrieval_query(question, history):
    pronouns = re.search(
        r"\b(?:it|its|they|them|their|that|those|this|these|ذلك|هذا|هذه|هو|هي|זה|זאת|אלה|שלו|שלה)\b",
        question, flags=re.IGNORECASE,
    )
    # A generic How/Why question may introduce a completely new subject.
    # Only explicit references or a topic-free continuation inherit history.
    continuation = re.fullmatch(
        r"(?:why|how so|tell me more|explain more|explain further|continue|"
        r"لماذا|أكمل|اشرح أكثر|اشرح المزيد|למה|המשך|הסבר עוד)[\s?.!؟]*",
        question.strip(), flags=re.IGNORECASE,
    )
    if not (pronouns or continuation):
        return question
    for item in reversed(list(history or [])[-12:]):
        if not isinstance(item, dict):
            continue
        if item.get("role") == "assistant":
            metadata = item.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            route = metadata.get("route", item.get("route"))
            if route in {"TOOL", "DIRECT_LLM"}:
                return question
        if item.get("role") == "user" and isinstance(item.get("content"), str) and item["content"].strip():
            # Legacy history has no route metadata; never append calculator or
            # course-lookup input to a retrieval query.
            if AgentRouter().route(item["content"])["route"] == "TOOL":
                return question
            return f"{item['content'][:600]}\nFollow-up: {question[:600]}"
    return question


def answer_with_rag(question, limit=5, minimum_similarity=None, history=None):
    if minimum_similarity is None:
        minimum_similarity = float(os.getenv("RAG_MIN_SIMILARITY", "0.25"))
    results = retrieve_chunks(_retrieval_query(question, history), limit=limit)
    relevant = [result for result in results if result["similarity"] >= minimum_similarity]
    if not relevant:
        raise AppError(
            "I could not find enough relevant information in the course materials. Try a more specific question or ingest the relevant course PDF.",
            "NO_RELEVANT_EVIDENCE",
            422,
        )

    context = "\n\n---\n\n".join(
        f"Source: {result['source']}\nPage: {result['page_number']}\n\n{result['content']}"
        for result in relevant
    )
    answer = generate_rag_answer(question=question, context=context, history=history)
    sources = []
    seen = set()
    for result in relevant:
        key = (result["source"], result["page_number"])
        if key in seen:
            continue
        seen.add(key)
        sources.append({
            "document": result["source"],
            "page": result["page_number"],
            "similarity": round(result["similarity"], 4),
        })
    return {"answer": answer, "sources": sources}


def answer_question(question, history=None):
    return answer_with_rag(question, history=history)
