"""Authoritative odds, probability, vig, and expected-value calculations."""
from __future__ import annotations
import math
from functools import reduce
from operator import mul
from typing import Iterable, Sequence

def _finite(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value): raise ValueError(f"{name} must be finite")
    return value

def american_to_decimal(odds: float) -> float:
    odds = _finite(odds, "American odds")
    if odds == 0: raise ValueError("American odds cannot be zero")
    return 1 + (odds / 100 if odds > 0 else 100 / abs(odds))

def decimal_to_american(odds: float) -> int:
    odds = _finite(odds, "Decimal odds")
    if odds <= 1: raise ValueError("Decimal odds must be greater than 1")
    return round((odds - 1) * 100) if odds >= 2 else round(-100 / (odds - 1))

def american_to_implied_probability(odds: float) -> float:
    return decimal_to_implied_probability(american_to_decimal(odds))

def decimal_to_implied_probability(odds: float) -> float:
    odds = _finite(odds, "Decimal odds")
    if odds <= 1: raise ValueError("Decimal odds must be greater than 1")
    return 1 / odds

def remove_vig(probabilities: Sequence[float]) -> list[float]:
    if len(probabilities) < 2: raise ValueError("A complete market needs at least two outcomes")
    values = [_finite(p, "Probability") for p in probabilities]
    if any(p <= 0 or p >= 1 for p in values): raise ValueError("Probabilities must be between 0 and 1")
    total = sum(values)
    return [p / total for p in values]

def consensus_probability(probabilities: Sequence[float], min_books: int = 2) -> float:
    values = [_finite(p, "Probability") for p in probabilities]
    if len(values) < min_books: raise ValueError(f"Consensus requires at least {min_books} books")
    if any(p <= 0 or p >= 1 for p in values): raise ValueError("Probabilities must be between 0 and 1")
    return sum(values) / len(values)

def edge(consensus: float, offered_implied: float) -> float:
    consensus, offered_implied = _finite(consensus, "Consensus probability"), _finite(offered_implied, "Offered implied probability")
    if not 0 <= consensus <= 1 or not 0 < offered_implied < 1: raise ValueError("Probabilities are outside valid bounds")
    return consensus - offered_implied

def parlay_decimal_odds(decimal_odds: Iterable[float]) -> float:
    values = [_finite(o, "Decimal odds") for o in decimal_odds]
    if not values or any(o <= 1 for o in values): raise ValueError("Parlay needs valid decimal odds")
    return reduce(mul, values, 1.0)

def independent_probability(probabilities: Iterable[float]) -> float:
    values = [_finite(p, "Probability") for p in probabilities]
    if not values or any(p < 0 or p > 1 for p in values): raise ValueError("Parlay needs valid probabilities")
    return reduce(mul, values, 1.0)

def expected_value(probability: float, decimal_odds: float) -> float:
    probability, decimal_odds = _finite(probability, "Probability"), _finite(decimal_odds, "Decimal odds")
    if not 0 <= probability <= 1 or decimal_odds <= 1: raise ValueError("Invalid probability or odds")
    return probability * decimal_odds - 1

expected_profit = expected_value
