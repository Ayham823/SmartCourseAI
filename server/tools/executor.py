from server.tools.grade_calculator import calculate_final_grade
from server.tools.course_lookup import lookup_course_information


ALLOWED_TOOLS = frozenset({"grade_calculator", "course_information_lookup"})


def execute_tool(tool_name, tool_input):
    if tool_name not in ALLOWED_TOOLS:
        raise ValueError("Unknown or unauthorized tool.")
    if not isinstance(tool_input, dict):
        raise ValueError("Tool arguments must be a JSON object.")
    required_key = "components" if tool_name == "grade_calculator" else "query"
    if set(tool_input) != {required_key}:
        raise ValueError(f"Tool arguments require only {required_key}.")
    if tool_name == "grade_calculator":
        return calculate_final_grade(tool_input["components"])
    return lookup_course_information(tool_input["query"])
