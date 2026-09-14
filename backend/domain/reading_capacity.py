"""Versioned provisional effort and flexible reading-budget calculations.

Targets express baseline (leisure-reading) pages when effort adjustment is on.
The existing reading-time heuristic supplies effort, including edition word density.
These are assumptions, not measurements. They never modify physical page progress.
"""
import calendar
from math import isfinite
from .reading_time import EstimationPolicy, ReadingLoad, ReadingMaterial, estimate_reading_time

CAPACITY_VERSION = 'reading-capacity-v1-provisional'


def effort_per_page(work, edition=None, enabled=True):
    if not enabled:
        return 1.0
    policy = EstimationPolicy()
    estimate = estimate_reading_time(ReadingMaterial(
        load=ReadingLoad(work.reading_load), load_multiplier_override=work.reading_effort_override), policy=policy)
    density = edition.word_count / edition.pages / policy.words_per_page if edition and edition.word_count and edition.pages else 1.0
    result = estimate.load_multiplier * density
    if not isfinite(result) or result <= 0:
        raise ValueError('The edition and reading-effort inputs must produce a positive finite estimate.')
    return result


def reading_budget(user, month):
    days = calendar.monthrange(month.year, month.month)[1]
    if user.reading_target_period == 'day':
        weekly = user.pages_per_day * user.reading_days_per_week
        monthly = weekly * days / 7
    elif user.reading_target_period == 'week':
        weekly = user.pages_per_week
        monthly = weekly * days / 7
    else:
        monthly = user.pages_per_month
        weekly = monthly * 7 / days
    return {'month': month.isoformat(), 'budget': round(monthly, 4), 'weekly_equivalent': round(weekly, 2),
            'per_reading_day': round(weekly / user.reading_days_per_week, 2),
            'unit': 'baseline_pages' if user.difficulty_aware_planning else 'pages',
            'algorithm_version': CAPACITY_VERSION,
            'assumptions': 'Weekly budgets are prorated by calendar days. Reading days describe a flexible rhythm, not fixed weekdays.'}
