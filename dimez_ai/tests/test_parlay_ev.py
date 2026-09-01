import pytest
from engine.odds_math import expected_value,independent_probability,parlay_decimal_odds
def test_reproducible_parlay_ev():
    p=independent_probability([.55,.6]); odds=parlay_decimal_odds([2,1.8]); assert p==.33 and expected_value(p,odds)==pytest.approx(.188)
