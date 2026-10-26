import json
from pathlib import Path
import pytest
from evaluation.metrics import summarize


def test_ranks_and_page_recall_are_not_inflated_by_duplicate_chunks():
    cases = [{"expected_pages": [1, 3], "results": [
        {"page": 2, "similarity": .9}, {"page": 1, "similarity": .8}, {"page": 1, "similarity": .7}
    ]}]
    result = summarize(cases, 3, .25)
    assert result["hit_at_k"] == 1
    assert result["page_recall_at_k"] == .5
    assert result["mrr_at_k"] == .5
    assert result["unanswerable_abstention_rate"] is None


def test_recall_does_not_hide_false_accepts_or_filter_relevant_evidence():
    cases = [
        {"expected_pages": [1], "results": [{"page": 1, "similarity": .2}]},
        {"expected_pages": [], "results": [{"page": 2, "similarity": .8}]},
        {"expected_pages": [], "results": [{"page": 3, "similarity": .1}]},
    ]
    result = summarize(cases)
    assert result["hit_at_k"] == 1 and result["accepted_evidence_rate"] == 0
    assert result["unanswerable_abstention_rate"] == .5
    assert result["unanswerable_false_accept_count"] == 1


@pytest.mark.parametrize("k,threshold", [(0,.25), (True,.25), (2,float("nan"))])
def test_invalid_metrics_parameters_fail(k, threshold):
    with pytest.raises(ValueError):
        summarize([], k, threshold)


def test_dataset_has_unique_labels_followups_multihop_and_unanswerable_cases():
    data = json.loads((Path(__file__).resolve().parents[1]/"evaluation/retrieval_cases.json").read_text())
    cases = data["cases"]
    assert len({case["id"] for case in cases}) == len(cases) == 24
    assert sum(not case["pages"] for case in cases) == 8
    assert any(case.get("history") for case in cases)
    assert any(len(case["pages"]) > 1 for case in cases)
    assert all(set(case["pages"]) <= {1,2,3} for case in cases)
