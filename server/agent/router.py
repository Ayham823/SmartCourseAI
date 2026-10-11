"""Explainable, deterministic routing before every chat model invocation."""
import re


def _contains(text, pattern):
    return bool(re.search(pattern, text, re.IGNORECASE))


class AgentRouter:
    """Prefer explicit intent; inherit recent routing only for a real follow-up."""

    def route(self, query, history=None):
        text = query.strip().casefold() if isinstance(query, str) else ""
        decision = self._explicit(text)
        if decision:
            return decision
        if self._is_followup(text):
            for message in reversed(list(history or [])[-12:]):
                if not isinstance(message, dict):
                    continue
                metadata = message.get("metadata") or {}
                previous_route = metadata.get("route", message.get("route"))
                previous_tool = metadata.get("tool", message.get("tool"))
                if message.get("role") == "assistant" and previous_route in {"RAG", "TOOL", "DIRECT_LLM"}:
                    if previous_route != "TOOL" or previous_tool in {"grade_calculator", "course_information_lookup"}:
                        return self._decision(previous_route, previous_tool, "Follow-up to the recent conversation topic.")
                if message.get("role") == "user":
                    prior = self._explicit(str(message.get("content", ""))[:4000].casefold())
                    if prior:
                        prior["routing_reason"] = "Follow-up to the recent user topic."
                        return prior
        return self._decision("DIRECT_LLM", None, "General study assistance without a document or tool request.")

    @staticmethod
    def _decision(route, tool, reason):
        return {"route": route, "tool": tool, "routing_reason": reason}

    def _explicit(self, text):
        if _contains(text, r"\b(according to|based on|from the|in the)\b.{0,50}\b(lecture|document|pdf|slides?|material|notes?)\b|\b(uploaded|course)\s+(documents?|materials?|pdf|notes?)\b|לפי.{0,40}(הרצאה|מסמך|חומר|סיכום)|בחומר הקורס|במצגת|בקובץ|במסמך"):
            return self._decision("RAG", None, "The question explicitly asks for course document evidence.")
        grade_intent = _contains(text, r"\b(calculate|compute|weighted|final|overall)\b.{0,35}\b(grade|score|average)\b|\b(grade|score)\b.{0,30}\b(calculate|compute|weighted|average)\b|חשב.{0,25}(ציון|ממוצע)|ציון.{0,20}(סופי|משוקלל)|ממוצע משוקלל")
        numerical_grade = _contains(text, r"\b(grade|score|exam|project)\b.{0,20}\d.{0,40}(weight|worth|%)|ציון.{0,20}\d.{0,40}(משקל|אחוז|%)")
        if grade_intent or numerical_grade:
            return self._decision("TOOL", "grade_calculator", "Weighted grade calculation requires the Python calculator.")
        lookup_intent = _contains(text, r"\b(deadline|due date|due|exam date|assignment|final project|final exam)\b|מועד|תאריך|דדליין|מטלה|עבודת סיום|פרויקט גמר|מבחן")
        lookup_request = _contains(text, r"\b(when|deadline|due|date|weight|worth|schedule|how much|percentage)\b|מתי|מועד|תאריך|משקל|אחוז|דדליין")
        if lookup_intent and lookup_request:
            return self._decision("TOOL", "course_information_lookup", "Structured course scheduling or grading information lookup.")
        if _contains(text, r"^(hi|hello|hey|good (morning|evening)|שלום|היי|בוקר טוב)(\b|[!,?.\s])|^(thanks|thank you|תודה)(\b|[!.\s])"):
            return self._decision("DIRECT_LLM", None, "Greeting or conversational acknowledgement.")
        if _contains(text, r"\b(anthropic|sdk|api|embedding[s]?|rag|retrieval augmented|lecture|syllabus|course material|pdf)\b|אמבדינג|הטמעות|הרצאה|סילבוס|חומר הקורס|אנתרופיק"):
            return self._decision("RAG", None, "Question about the subject covered by the course knowledge base.")
        return None

    @staticmethod
    def _is_followup(text):
        return _contains(text, r"\b(it|its|that|those|them|this|instead|again|more|same|what about|and the|change|replace)\b|^(and|also|why|how so)\b|זה|זאת|שלו|שלה|שוב|עוד|במקום|ומה|למה|שנה|תחליף")
