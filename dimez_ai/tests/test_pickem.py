from engine.pickem import find_line_advantages,generate_pickem_cards

def offer(book,player,side,line,event="g1",market="player_pass_yds"):
    return {"event_id":event,"home_team":"Home","away_team":"Away","commence_time":"2030-01-01T00:00:00Z",
            "market_key":market,"market_type":"player_prop","sportsbook":book,"player_name":player,"side":side,
            "selection":side,"line":line,"american_odds":-110,"decimal_odds":1.91,"retrieved_at":"2030-01-01T00:00:00Z"}

def test_line_advantage_requires_two_sportsbooks_and_rejects_extreme_promo():
    rows=[offer("draftkings","QB","Over",250.5),offer("fanduel","QB","Over",250.5),offer("underdog","QB","Over",247.5),
          offer("draftkings","Promo QB","Over",250.5),offer("fanduel","Promo QB","Over",250.5),offer("prizepicks","Promo QB","Over",0.5)]
    found=find_line_advantages(rows)
    assert len(found)==1 and found[0]["operator"]=="underdog" and found[0]["line_advantage"]==3

def test_cards_stay_on_one_operator_and_use_distinct_players():
    rows=[]
    for index in range(4):
        player=f"Player {index}"
        rows.extend([offer("draftkings",player,"Over",50.5,event=f"g{index}"),offer("fanduel",player,"Over",50.5,event=f"g{index}"),offer("underdog",player,"Over",49.5,event=f"g{index}")])
    cards=generate_pickem_cards(rows)
    assert {card["leg_count"] for card in cards}=={2,3,4}
    assert all(card["operator"]=="underdog" and len({leg["player_name"] for leg in card["legs"]})==card["leg_count"] for card in cards)
