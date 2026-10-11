"""Validated arithmetic, independent of the language model."""
from decimal import Decimal, ROUND_HALF_UP
import math


def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number.")
    if not 0 <= value <= 100:
        raise ValueError(f"{field} must be between 0 and 100.")
    return Decimal(str(value))


def _rounded(value):
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calculate_final_grade(components):
    if not isinstance(components, list) or not 1 <= len(components) <= 30:
        raise ValueError("Provide between 1 and 30 grade components.")
    total_weight = Decimal(0)
    weighted_sum = Decimal(0)
    breakdown = []
    for component in components:
        if not isinstance(component, dict) or set(component) != {"name", "grade", "weight"}:
            raise ValueError("Each component requires only name, grade and weight.")
        name = component["name"]
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError("Component name must contain between 1 and 120 characters.")
        grade = _number(component["grade"], "Grade")
        weight = _number(component["weight"], "Weight")
        weighted_value = grade * weight / Decimal(100)
        weighted_sum += weighted_value
        total_weight += weight
        breakdown.append({"name": name.strip(), "grade": float(grade), "weight": float(weight), "weighted_value": _rounded(weighted_value)})
    if abs(total_weight - Decimal(100)) > Decimal("0.000001"):
        raise ValueError("The total component weight must equal 100%.")
    return {"final_grade": _rounded(weighted_sum), "total_weight": float(total_weight), "breakdown": breakdown}
