"""Compatibility exports for the Odds API source."""
from ingestion.odds_source import OddsSource, OddsSourceError
from engine.odds_math import american_to_implied_probability as american_to_implied, remove_vig
def remove_vig_multiplicative(probabilities): return remove_vig(probabilities)
def remove_vig_power(probabilities, power=1.0):
    adjusted = [float(p) ** power for p in probabilities]; total = sum(adjusted)
    return [p / total for p in adjusted] if total else adjusted
