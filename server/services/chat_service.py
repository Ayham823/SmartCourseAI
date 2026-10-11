"""Router -> RAG/tool/direct LCEL processing. HTTP owns message persistence."""
import json
import logging
import math
import re

from langchain_core.messages import ToolMessage
from server.agent.router import AgentRouter
from server.database import db
from server.errors import AppError
from server.llm import chain
from server.rag import service as rag_service
from server.services.response_formatter import format_response
from server.tools.executor import execute_tool
from server.tools.schemas import TOOLS


logger = logging.getLogger(__name__)
MAX_TOOL_ROUNDS = 2
MAX_TOOL_CALLS = 3


def _audit_json(value):
    """Keep invalid numeric arguments auditable as valid JSONB, without repr()."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _audit_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_audit_json(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return "<unsupported value>"


def _log_call(session_id, name, arguments, result):
    try:
        recorded_name = name[:100] if isinstance(name, str) and name else "invalid_tool"
        db.save_tool_call(session_id, recorded_name, _audit_json(arguments), _audit_json(result))
    except AppError:
        raise
    except Exception:
        # Do not return an unlogged tool result as a successful request.
        raise AppError("Could not save the tool call. Please try again.", code="database_unavailable", status=503) from None


def _validate_grade_provenance(arguments, question, history):
    """Reject provider-invented grades or weights absent from bounded user input."""
    components = arguments.get("components", []) if isinstance(arguments, dict) else []
    if not isinstance(components, list):
        return  # Executor supplies the consistent structural validation error.
    texts = [str(row.get("content", ""))[:4000] for row in list(history or [])[-12:] if isinstance(row, dict) and row.get("role") == "user"]
    texts.append(question)
    numbers = {float(value.replace(",", ".")) for value in re.findall(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w.])", "\n".join(texts))}
    for component in components:
        if not isinstance(component, dict):
            continue
        for key in ("grade", "weight"):
            value = component.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value not in numbers:
                raise ValueError("Provide each component's grade and percentage weight explicitly; values cannot be assumed.")


def _process_tool(question, session_id, history, tool_name):
    allowed = [schema for schema in TOOLS if schema["name"] == tool_name]
    if len(allowed) != 1:
        raise AppError("The requested tool is unavailable.", code="tool_unavailable", status=503)
    llm = chain.get_llm()
    selection = chain.build_tool_selection_chain(llm, allowed)
    scratchpad = []
    total_calls = 0
    for _ in range(MAX_TOOL_ROUNDS):
        response = chain.invoke_checked(selection, {
            "question": question, "tool_name": tool_name,
            "history": chain.bounded_history(history), "scratchpad": scratchpad,
        })
        calls = getattr(response, "tool_calls", []) or []
        if not calls:
            if getattr(response, "invalid_tool_calls", None):
                raise AppError("The AI service returned invalid tool arguments. Please try again.", code="invalid_tool_call", status=502)
            # A clarification answer is valid when the user's tool input is incomplete.
            from langchain_core.output_parsers import StrOutputParser
            answer = StrOutputParser().invoke(response).strip()
            if not answer:
                raise AppError("The AI service returned an empty answer.", code="llm_empty_answer", status=502)
            return answer
        if total_calls + len(calls) > MAX_TOOL_CALLS:
            raise AppError("The AI service requested too many tool calls. Please simplify the question.", code="tool_call_limit", status=502)
        scratchpad.append(response)
        all_successful = True
        for call in calls:
            total_calls += 1
            name = call.get("name", "")
            arguments = call.get("args", {})
            call_id = call.get("id")
            if not isinstance(call_id, str) or not call_id:
                raise AppError("The AI service returned an invalid tool call.", code="invalid_tool_call", status=502)
            try:
                if name != tool_name:
                    raise ValueError("The requested tool is not authorized for this question.")
                if name == "grade_calculator":
                    _validate_grade_provenance(arguments, question, history)
                output = {"status": "success", "result": execute_tool(name, arguments)}
            except ValueError as error:
                all_successful = False
                output = {"status": "error", "error": str(error), "code": "invalid_tool_arguments"}
            except Exception:
                logger.warning("Tool execution failed: tool=%s", tool_name)
                all_successful = False
                output = {"status": "error", "error": "The tool could not complete the request.", "code": "tool_execution_error"}
            _log_call(session_id, name, arguments, output)
            scratchpad.append(ToolMessage(content=json.dumps(output, ensure_ascii=False, allow_nan=False), tool_call_id=call_id, name=name))
        if all_successful:
            break
    # No tools are bound for this final LCEL completion: the model cannot loop.
    return chain.generate_tool_answer(llm, question, tool_name, history, scratchpad)


def process_message(message, session_id, history=None):
    decision = AgentRouter().route(message, history)
    route, tool = decision["route"], decision["tool"]
    sources = []
    if route == "RAG":
        result = rag_service.answer_question(message, history=history)
        answer, sources = result["answer"], result.get("sources", [])
    elif route == "TOOL":
        answer = _process_tool(message, session_id, history, tool)
    else:
        answer = chain.generate_direct_answer(message, history=history)
    return format_response(session_id, answer, route, tool, sources, decision["routing_reason"])
