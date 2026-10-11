"""Look up explicitly verified course records; never infer academic dates."""
import json
from pathlib import Path
import re


COURSE_INFO_PATH = Path(__file__).resolve().parents[2] / "knowledge" / "course_info.json"


def load_course_info():
    with COURSE_INFO_PATH.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("Course information is not configured correctly.")
    return data


def _tokens(value):
    return re.findall(r"\w+", value.casefold(), flags=re.UNICODE)


def _phrase_present(phrase, query):
    tokens = _tokens(phrase)
    return bool(tokens) and any(query[index:index + len(tokens)] == tokens for index in range(len(query) - len(tokens) + 1))


def lookup_course_information(query):
    if not isinstance(query, str) or not query.strip() or len(query) > 2000:
        raise ValueError("Course lookup query must contain between 1 and 2000 characters.")
    data = load_course_info()
    query_tokens = _tokens(query)
    results = []
    for collection, record_type in (("assignments", "assignment"), ("exams", "exam")):
        records = data.get(collection, [])
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("name"), str):
                continue
            if record.get("verified", data.get("verified", False)) is not True:
                continue
            aliases = record.get("aliases", [])
            labels = [record["name"]] + ([alias for alias in aliases if isinstance(alias, str)] if isinstance(aliases, list) else [])
            if any(_phrase_present(label, query_tokens) for label in labels) or query.strip().casefold() == collection:
                results.append({"type": record_type, **record})
    return {
        "course": data.get("course_name"),
        "available": bool(results),
        "status": "verified" if results else "unavailable",
        "results": results,
        "message": "Verified course records found." if results else "Verified information for this course item is not available. Check the official syllabus or course portal.",
    }
