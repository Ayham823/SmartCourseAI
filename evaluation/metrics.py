"""Page-based retrieval metrics, with unanswerable cases reported separately."""
import math


def summarize(cases, k=3, threshold=0.25):
    if isinstance(k, bool) or not isinstance(k, int) or k < 1 or not math.isfinite(threshold):
        raise ValueError("Require a positive k and finite threshold")
    positives, negatives = [], []
    for case in cases:
        expected = set(case["expected_pages"])
        retrieved = case["results"][:k]
        accepted = [row for row in retrieved if row["similarity"] >= threshold]
        if expected:
            ranks = [rank for rank, row in enumerate(retrieved, 1) if row["page"] in expected]
            positives.append({
                "hit": bool(ranks), "recall": len(expected & {r["page"] for r in retrieved}) / len(expected),
                "rr": 1 / min(ranks) if ranks else 0,
                "accepted_evidence": bool(expected & {r["page"] for r in accepted}),
            })
        else:
            negatives.append(not accepted)
    mean = lambda values: sum(values) / len(values) if values else None
    return {
        "answerable_count": len(positives), "unanswerable_count": len(negatives),
        "hit_at_k": mean([p["hit"] for p in positives]),
        "page_recall_at_k": mean([p["recall"] for p in positives]),
        "mrr_at_k": mean([p["rr"] for p in positives]),
        "accepted_evidence_rate": mean([p["accepted_evidence"] for p in positives]),
        "unanswerable_abstention_rate": mean(negatives),
        "unanswerable_false_accept_count": sum(not n for n in negatives),
    }
