"""Personal scoring is independent from publisher positions and shared assessments."""
from math import isfinite


def validate_scores(values, allowed, maximum=None):
    if not isinstance(values, dict) or set(values) - set(allowed):
        raise ValueError('Scores must use the defined criterion IDs.')
    for value in values.values():
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError('Values must be finite nonnegative numbers.')
        try:
            finite = isfinite(value)
        except OverflowError:
            finite = False
        if not finite or value < 0:
            raise ValueError('Values must be finite nonnegative numbers.')
        if maximum is not None and value > maximum:
            raise ValueError(f'Values must be at most {maximum}.')


def weighted_score(assessments, weights, overrides=None):
    if not isinstance(assessments, dict) or not isinstance(weights, dict):
        raise ValueError('Assessments and weights must be objects.')
    validate_scores(weights, weights, 100)
    if overrides is not None:
        validate_scores(overrides, overrides, 10)
    active = {key: value for key, value in weights.items() if value > 0}
    if not active:
        return {'score': None, 'reason': 'Choose at least one positive weight.', 'contributions': {}}
    values = {**assessments, **(overrides or {})}
    if any(values.get(key) is None for key in active):
        return {'score': None, 'reason': 'Assessment needed', 'contributions': {}}
    validate_scores({key: values[key] for key in active}, active, 10)
    total = sum(active.values())
    contributions = {key: values[key] * weight / total * 10 for key, weight in active.items()}
    return {'score': sum(contributions.values()), 'reason': None, 'contributions': contributions}
