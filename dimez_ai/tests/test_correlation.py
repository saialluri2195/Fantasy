from engine.recommendations import generate_parlays
def test_same_game_gets_conservative_discount():
    legs=[]
    for i in range(2): legs.append({"candidate_key":str(i),"event_id":"g","market_key":"x"+str(i),"selection":"A","edge":.1,"consensus_probability":.6,"decimal_odds":2,"american_odds":100,"raw_implied_probability":.5,"sportsbook":"x"})
    result=generate_parlays(legs)[0]; assert result["correlation_adjustment"]<1 and result["estimated_probability"]<result["independent_probability"]
