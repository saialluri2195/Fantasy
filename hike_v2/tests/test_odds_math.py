import pytest
from engine.odds_math import *
def test_conversions():
    assert american_to_decimal(150)==2.5; assert american_to_decimal(-200)==1.5
    assert decimal_to_american(2.5)==150; assert decimal_to_american(1.5)==-200
    assert american_to_implied_probability(100)==.5; assert american_to_implied_probability(-200)==pytest.approx(2/3)
def test_vig_consensus_edge():
    fair=remove_vig([.55,.55]); assert fair==[.5,.5]
    assert consensus_probability([.48,.52])==.5; assert edge(.5,.45)==pytest.approx(.05)
def test_parlay_math():
    assert parlay_decimal_odds([2,2])==4; assert independent_probability([.5,.5])==.25; assert expected_value(.3,4)==pytest.approx(.2)
def test_invalid():
    for fn,args in [(american_to_decimal,(0,)),(decimal_to_american,(1,)),(remove_vig,([.5],)),(consensus_probability,([.5],))]:
        with pytest.raises(ValueError): fn(*args)
