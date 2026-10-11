"""The mandatory router stays deterministic and independent of paid APIs."""
import pytest

from server.agent.router import AgentRouter


@pytest.mark.parametrize("question,route,tool", [
    ("Explain embeddings according to lecture 3.", "RAG", None),
    ("Summarize the uploaded documents.", "RAG", None),
    ("How do I authenticate with the Anthropic Python SDK?", "RAG", None),
    ("הסבר את הנושא לפי ההרצאה", "RAG", None),
    ("My exam grade is 82 worth 70%. My project grade is 95 worth 30%. Calculate my final grade.", "TOOL", "grade_calculator"),
    ("חשב את הציון הסופי", "TOOL", "grade_calculator"),
    ("When is the Final Project deadline?", "TOOL", "course_information_lookup"),
    ("What is the weight of the Final Project?", "TOOL", "course_information_lookup"),
    ("מתי מועד הגשת מטלה 2?", "TOOL", "course_information_lookup"),
    ("Hello, what can you help me with?", "DIRECT_LLM", None),
    ("שלום", "DIRECT_LLM", None),
    ("Suggest a study routine.", "DIRECT_LLM", None),
    ("", "DIRECT_LLM", None),
    (None, "DIRECT_LLM", None),
])
def test_explicit_intent(question, route, tool):
    result = AgentRouter().route(question)
    assert result["route"] == route
    assert result["tool"] == tool
    assert isinstance(result["routing_reason"], str)
    assert result["routing_reason"]


@pytest.mark.parametrize("previous_route,previous_tool", [
    ("RAG", None),
    ("TOOL", "grade_calculator"),
    ("TOOL", "course_information_lookup"),
    ("DIRECT_LLM", None),
])
def test_followup_inherits_recent_persisted_metadata(previous_route, previous_tool):
    history = [
        {"role": "user", "content": "Explain this subject."},
        {"role": "assistant", "content": "Previous answer.", "metadata": {"route": previous_route, "tool": previous_tool}},
    ]
    result = AgentRouter().route("What is its main advantage?", history)
    assert result["route"] == previous_route
    assert result["tool"] == previous_tool
    assert "Follow-up" in result["routing_reason"]


def test_followup_uses_legacy_history_without_routing_metadata():
    history = [
        {"role": "user", "content": "Explain the Anthropic SDK."},
        {"role": "assistant", "content": "It is a client library."},
    ]
    assert AgentRouter().route("What about its authentication?", history)["route"] == "RAG"


def test_hebrew_followup_preserves_document_route():
    history = [{"role": "assistant", "content": "הסבר", "metadata": {"route": "RAG", "tool": None}}]
    assert AgentRouter().route("מה היתרון שלו?", history)["route"] == "RAG"


def test_greeting_and_explicit_topic_override_previous_tool():
    history = [{"role": "assistant", "content": "85.9", "metadata": {"route": "TOOL", "tool": "grade_calculator"}}]
    assert AgentRouter().route("Hello!", history)["route"] == "DIRECT_LLM"
    assert AgentRouter().route("Explain embeddings according to the lecture.", history)["route"] == "RAG"


def test_document_grounding_has_priority_over_calculation_words():
    result = AgentRouter().route("Explain final grade calculation according to the course documents.")
    assert result["route"] == "RAG"


def test_recent_history_is_bounded():
    history = [{"role": "user", "content": "Explain the Anthropic SDK."}]
    history.extend({"role": "assistant", "content": "Study tip.", "metadata": {"route": "DIRECT_LLM"}} for _ in range(13))
    assert AgentRouter().route("Explain that further.", history)["route"] == "DIRECT_LLM"


def test_invalid_previous_tool_cannot_enter_execution_path():
    history = [{"role": "assistant", "content": "Untrusted metadata.", "metadata": {"route": "TOOL", "tool": "run_python"}}]
    assert AgentRouter().route("Do that again.", history)["route"] == "DIRECT_LLM"
