"""Deterministic month allocation. Locked allocations are reservations, never moved."""
import calendar
from datetime import date
from math import floor, isfinite


def month_range(start, count):
    if not isinstance(start, date) or start.day != 1:
        raise ValueError('Use the first day of the start month.')
    if type(count) is not int or not 1 <= count <= 24:
        raise ValueError('Choose between 1 and 24 months.')
    return [date(start.year + (start.month - 1 + i) // 12, (start.month - 1 + i) % 12 + 1, 1) for i in range(count)]


def suggest_plan(books, months, pages_per_day, locked, *, month_budgets=None):
    if type(pages_per_day) is not int or not 1 <= pages_per_day <= 2000:
        raise ValueError('Daily reading capacity must be between 1 and 2000 pages.')
    if len(set(months)) != len(months) or months != sorted(months) or any(m.day != 1 for m in months):
        raise ValueError('Choose distinct calendar months in chronological order.')
    if len({b['id'] for b in books}) != len(books):
        raise ValueError('Choose each work once.')
    for book in books:
        pages = book['remaining_pages']
        if pages is not None and (type(pages) is not int or pages < 0):
            raise ValueError('Remaining pages must be a nonnegative whole number.')
    capacities = dict(month_budgets) if month_budgets is not None else {month: calendar.monthrange(month.year, month.month)[1] * pages_per_day for month in months}
    if set(capacities) != set(months) or any(not isfinite(v) or v <= 0 for v in capacities.values()):
        raise ValueError('Each month needs a positive finite reading budget.')
    for item in [*books, *locked]:
        factor = item.get('effort_per_page', 1)
        if not isinstance(factor, (float, int)) or isinstance(factor, bool) or not isfinite(factor) or factor <= 0:
            raise ValueError('Reading effort must be a positive finite number.')
    reservations = {}
    warnings = []
    for item in locked:
        if item['month'] not in capacities:
            continue
        if item['pages'] is None:
            raise ValueError('Add page allocations to locked books before generating a plan.')
        if type(item['pages']) is not int or item['pages'] < 1:
            raise ValueError('Locked page allocations must be positive whole numbers.')
        capacities[item['month']] -= item['pages'] * item.get('effort_per_page', 1)
        reservations[item['work']] = reservations.get(item['work'], 0) + item['pages']
    for month, capacity in capacities.items():
        if capacity < 0:
            warnings.append(f'Locked books exceed {month:%B %Y} capacity by {-capacity:g} budget units.')
    proposed, unscheduled = [], []
    for book in books:
        if book['remaining_pages'] is None:
            unscheduled.append({'work': book['id'], 'reason': 'Add an edition page count.'})
            continue
        remaining = max(0, book['remaining_pages'] - reservations.get(book['id'], 0))
        for month in months:
            if not remaining:
                break
            # Keep one work/month record; preserve the locked allocation exactly.
            if any(x['work'] == book['id'] and x['month'] == month for x in locked):
                continue
            factor = book.get('effort_per_page', 1)
            allocated = min(remaining, max(0, floor((capacities[month] + 1e-9) / factor)))
            if allocated:
                proposed.append({'work': book['id'], 'month': month.isoformat(), 'pages': allocated, 'locked': False})
                capacities[month] -= allocated * factor
                remaining -= allocated
        if remaining:
            unscheduled.append({'work': book['id'], 'reason': f'{remaining} pages exceed available capacity.'})
    return {'items': proposed, 'unscheduled': unscheduled, 'warnings': warnings,
            'capacity_remaining': {m.isoformat(): n for m, n in capacities.items()}}
