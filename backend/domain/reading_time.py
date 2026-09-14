"""Replaceable reading-time heuristic, not an empirically calibrated model.

All default rates, multipliers, and ranges below are provisional product
assumptions. They must not be described as measured averages or confidence
intervals. Edition-specific length and individual reading history can replace
these defaults later without changing the result contract.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class ReadingLoad(str, Enum):
    LEISURE = "leisure"
    CLASSIC_LITERATURE = "classic_literature"
    DEMANDING_LITERATURE = "demanding_literature"
    PHILOSOPHY = "philosophy"


@dataclass(frozen=True)
class ReadingMaterial:
    # Prefer a verified word count for the chosen edition/translation.
    word_count: int | None = None
    page_count: int | None = None
    load: ReadingLoad = ReadingLoad.LEISURE
    # One override replaces the profile multiplier, avoiding double-counting
    # overlapping tags such as "classic", "difficult", and "philosophy".
    load_multiplier_override: float | None = None


@dataclass(frozen=True)
class ReaderProfile:
    baseline_words_per_minute: float = 250.0
    # Additional rereading, annotation, and reflection: 0.5 means 50% extra.
    study_overhead_fraction: float = 0.0


@dataclass(frozen=True)
class EstimationPolicy:
    version: str = "reading-time-v0-uncalibrated"
    words_per_page: float = 300.0
    leisure_multiplier: float = 1.0
    classic_multiplier: float = 1.5
    demanding_multiplier: float = 2.0
    philosophy_multiplier: float = 2.5
    range_low_multiplier: float = 0.75
    range_high_multiplier: float = 1.5


@dataclass(frozen=True)
class ReadingTimeEstimate:
    status: str
    estimated_hours: float | None
    low_hours: float | None
    high_hours: float | None
    length_basis: str | None
    load_multiplier: float
    algorithm_version: str
    calibrated: bool
    assumptions: tuple[str, ...]


def _positive_finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")


def estimate_reading_time(
    material: ReadingMaterial,
    reader: ReaderProfile = ReaderProfile(),
    policy: EstimationPolicy = EstimationPolicy(),
) -> ReadingTimeEstimate:
    """Estimate total hours with transparent, replaceable difficulty factors.

    The planner may explicitly use this same effort multiplier for baseline-page
    budgets. Physical page counts and reading progress always remain unchanged.
    Missing length returns an unavailable estimate instead of a made-up length.
    """
    for name, value in (("word_count", material.word_count), ("page_count", material.page_count)):
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"{name} must be a nonnegative integer or None")
    _positive_finite("baseline_words_per_minute", reader.baseline_words_per_minute)
    _positive_finite("words_per_page", policy.words_per_page)
    for name in ("leisure_multiplier", "classic_multiplier", "demanding_multiplier", "philosophy_multiplier",
                 "range_low_multiplier", "range_high_multiplier"):
        _positive_finite(name, getattr(policy, name))
    if not 0 < policy.range_low_multiplier <= 1 <= policy.range_high_multiplier:
        raise ValueError("The estimate range must bracket the central estimate")
    if (isinstance(reader.study_overhead_fraction, bool)
            or not isfinite(reader.study_overhead_fraction)
            or reader.study_overhead_fraction < 0):
        raise ValueError("study_overhead_fraction must be a nonnegative finite number")

    profile_factors = {
        ReadingLoad.LEISURE: policy.leisure_multiplier,
        ReadingLoad.CLASSIC_LITERATURE: policy.classic_multiplier,
        ReadingLoad.DEMANDING_LITERATURE: policy.demanding_multiplier,
        ReadingLoad.PHILOSOPHY: policy.philosophy_multiplier,
    }
    if not isinstance(material.load, ReadingLoad):
        raise ValueError("load must be a ReadingLoad value")
    multiplier = material.load_multiplier_override
    if multiplier is None:
        multiplier = profile_factors[material.load]
    _positive_finite("load_multiplier", multiplier)

    assumptions = [
        "Uncalibrated heuristic; the range is illustrative, not a confidence interval.",
        f"Reader baseline: {reader.baseline_words_per_minute:g} words per minute.",
        f"Reading load multiplier: {multiplier:g}; study overhead: {reader.study_overhead_fraction:g}.",
    ]
    if material.word_count is not None:
        words, basis = material.word_count, "word_count"
    elif material.page_count is not None:
        words, basis = material.page_count * policy.words_per_page, "page_count_estimate"
        assumptions.append(f"Estimated {policy.words_per_page:g} words per page; layout and translation vary.")
    else:
        return ReadingTimeEstimate(
            "unavailable", None, None, None, None, multiplier, policy.version, False,
            tuple(assumptions + ["Add an edition word count or page count to estimate duration."]),
        )

    hours = words / reader.baseline_words_per_minute / 60 * multiplier * (1 + reader.study_overhead_fraction)
    if not isfinite(hours) or not isfinite(hours * policy.range_high_multiplier):
        raise ValueError("Inputs produce a nonfinite duration")
    return ReadingTimeEstimate(
        "provisional", hours, hours * policy.range_low_multiplier,
        hours * policy.range_high_multiplier, basis, multiplier, policy.version,
        False, tuple(assumptions),
    )
