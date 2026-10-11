"""Python tool validation and honest course lookup without external services."""
import copy

import pytest

from server.tools import course_lookup
from server.tools.executor import ALLOWED_TOOLS, execute_tool
from server.tools.grade_calculator import calculate_final_grade
from server.tools.schemas import TOOLS


COMPONENTS = [
    {"name": "Exam", "grade": 82, "weight": 70},
    {"name": "Project", "grade": 95, "weight": 30},
]


def test_weighted_grade_example():
    result = calculate_final_grade(COMPONENTS)
    assert result["final_grade"] == 85.9
    assert result["total_weight"] == 100
    assert [row["weighted_value"] for row in result["breakdown"]] == [57.4, 28.5]


def test_decimal_weights_and_rounding():
    result = calculate_final_grade([
        {"name": "A", "grade": 90, "weight": 33.33},
        {"name": "B", "grade": 90, "weight": 33.33},
        {"name": "C", "grade": 90, "weight": 33.34},
    ])
    assert result["final_grade"] == 90
    assert calculate_final_grade([{"name": "Only", "grade": 85.555, "weight": 100}])["final_grade"] == 85.56


@pytest.mark.parametrize("field,value", [
    ("grade", -1), ("grade", 101), ("grade", True),
    ("grade", "82"), ("grade", None), ("grade", float("nan")),
    ("grade", float("inf")), ("grade", float("-inf")),
    ("weight", -1), ("weight", 101), ("weight", False),
    ("weight", "70"), ("weight", None), ("weight", float("nan")),
    ("weight", float("inf")),
])
def test_rejects_invalid_numbers(field, value):
    components = copy.deepcopy(COMPONENTS)
    components[0][field] = value
    with pytest.raises(ValueError):
        calculate_final_grade(components)


def test_rejects_weights_that_do_not_total_one_hundred():
    components = copy.deepcopy(COMPONENTS)
    components[1]["weight"] = 20
    with pytest.raises(ValueError, match="100%"):
        calculate_final_grade(components)


@pytest.mark.parametrize("components", [
    [], None, {}, "grades", [None], [82],
    [{"name": "Exam", "grade": 82}],
    [{"name": "", "grade": 82, "weight": 100}],
    [{"name": True, "grade": 82, "weight": 100}],
    [{"name": "Exam", "grade": 82, "weight": 100, "code": "run()"}],
    [{"name": "A", "grade": 82, "weight": 100}] * 31,
])
def test_rejects_malformed_components(components):
    with pytest.raises(ValueError):
        calculate_final_grade(components)


def test_executor_allowlist_and_argument_contract():
    assert execute_tool("grade_calculator", {"components": COMPONENTS})["final_grade"] == 85.9
    with pytest.raises(ValueError, match="Unknown or unauthorized"):
        execute_tool("run_python", {"code": "print('unsafe')"})
    for arguments in (None, [], {}, {"components": COMPONENTS, "extra": "ignored"}):
        with pytest.raises(ValueError):
            execute_tool("grade_calculator", arguments)


@pytest.fixture
def verified_course(monkeypatch):
    # All dates here are explicitly artificial unit-test fixtures.
    data = {
        "course_name": "Test fixture course",
        "verified": True,
        "assignments": [
            {"name": "Assignment 1", "deadline": "2099-01-01", "weight": 10, "aliases": ["מטלה 1"]},
            {"name": "Assignment 10", "deadline": "2099-02-01", "weight": 20},
            {"name": "Unverified Project", "deadline": "2099-03-01", "verified": False},
        ],
        "exams": [{"name": "Final Exam", "date": "2099-04-01", "aliases": ["מבחן סופי"]}],
    }
    monkeypatch.setattr(course_lookup, "load_course_info", lambda: data)
    return data


def test_verified_lookup_returns_structured_data(verified_course):
    result = execute_tool("course_information_lookup", {"query": "When is Assignment 1 due?"})
    assert result["available"] is True
    assert result["status"] == "verified"
    assert result["course"] == "Test fixture course"
    assert result["results"][0]["type"] == "assignment"
    assert result["results"][0]["deadline"] == "2099-01-01"


def test_lookup_token_boundaries_do_not_match_assignment_one_to_ten(verified_course):
    result = course_lookup.lookup_course_information("Assignment 10 deadline")
    assert [row["name"] for row in result["results"]] == ["Assignment 10"]
    assert course_lookup.lookup_course_information("Assignment 100 deadline")["results"] == []


def test_lookup_supports_explicit_hebrew_aliases(verified_course):
    assert course_lookup.lookup_course_information("מתי מגישים מטלה 1?")["results"][0]["name"] == "Assignment 1"
    assert course_lookup.lookup_course_information("מתי מבחן סופי?")["results"][0]["type"] == "exam"


def test_unverified_records_and_unknown_items_are_unavailable(verified_course):
    for query in ("Unverified Project", "Unknown Assignment"):
        result = course_lookup.lookup_course_information(query)
        assert result["available"] is False
        assert result["status"] == "unavailable"
        assert result["results"] == []
        assert "not available" in result["message"]


def test_course_without_verification_never_presents_dates_as_facts(monkeypatch):
    monkeypatch.setattr(course_lookup, "load_course_info", lambda: {
        "course_name": "Fixture", "assignments": [{"name": "Project", "deadline": "2099-01-01"}],
    })
    assert course_lookup.lookup_course_information("Project")["results"] == []


@pytest.mark.parametrize("query", ["", "   ", None, 123, "x" * 2001])
def test_lookup_rejects_invalid_queries(query):
    with pytest.raises(ValueError):
        course_lookup.lookup_course_information(query)


def test_anthropic_schemas_match_the_execution_allowlist():
    assert {schema["name"] for schema in TOOLS} == ALLOWED_TOOLS
    for schema in TOOLS:
        assert schema["input_schema"]["type"] == "object"
        assert schema["input_schema"]["additionalProperties"] is False
        assert schema["input_schema"]["required"]
