"""Parlay Value Finder Page — Edge detection with model vs market probabilities."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd

from config import RESPONSIBLE_GAMBLING_NOTE
from optimizer.parlay import ParlayValueFinder


def render_parlay_page():
    st.title("Parlay Value Finder")
    st.markdown(
        "Finds props where the model's calibrated win probability exceeds "
        "the sportsbook's implied probability."
    )
    st.warning(RESPONSIBLE_GAMBLING_NOTE)

    min_edge = st.slider(
        "Minimum Edge (%)", min_value=1, max_value=15, value=3,
        help="Only show legs where model prob exceeds market by at least this much",
    ) / 100

    if st.button("Find Value Edges", type="primary"):
        with st.spinner("Running win-probability models..."):
            try:
                edges = _run_parlay_finder(min_edge)
                _display_parlay_results(edges)
            except Exception as e:
                st.error(f"Model computation failed: {e}")
                st.info("Ensure odds ingestion and model training have been run.")


def _run_parlay_finder(min_edge):
    """Run the deterministic parlay value finder."""
    from ingestion.odds import pull_player_props
    from features.builder import build_feature_table
    from models.win_probability import WinProbabilityModel
    from config import MODEL_ARTIFACTS_DIR, CURRENT_SEASON

    props = pull_player_props(CURRENT_SEASON)

    # Build features for all positions (props can be for any position)
    features = build_feature_table("WR", [CURRENT_SEASON], mode="inference")
    for pos in ["QB", "RB", "TE"]:
        pos_df = build_feature_table(pos, [CURRENT_SEASON], mode="inference")
        features = pd.concat([features, pos_df], ignore_index=True)

    # Deduplicate: each player appears once (keep most recent week)
    features = features.sort_values("week").groupby("player_id", as_index=False).last()

    models = {}
    for prop_type in ["player_over_receiving_yards", "player_over_rushing_yards"]:
        model_path = MODEL_ARTIFACTS_DIR / f"winprob_{prop_type}.pkl"
        if model_path.exists():
            models[prop_type] = WinProbabilityModel.load(model_path)

    if not models:
        st.info("Win probability models not yet trained. Showing sample edges.")
        return _sample_edges()

    finder = ParlayValueFinder(models, min_edge=min_edge)
    edges = finder.find_edges(props, features)
    return edges


def _sample_edges():
    """Return sample edges when models aren't trained yet."""
    return pd.DataFrame([
        {
            "rank": 1, "player_name": "Patrick Mahomes", "prop_type": "player_pass_yds",
            "line": 275.5, "model_prob": 0.62, "market_prob": 0.524,
            "edge": 0.096, "edge_pct": 9.6, "bookmaker": "draftkings", "confidence": "high",
        },
        {
            "rank": 2, "player_name": "Christian McCaffrey", "prop_type": "player_rush_yds",
            "line": 85.5, "model_prob": 0.58, "market_prob": 0.512,
            "edge": 0.068, "edge_pct": 6.8, "bookmaker": "fanduel", "confidence": "medium",
        },
        {
            "rank": 3, "player_name": "Tyreek Hill", "prop_type": "player_reception_yds",
            "line": 75.5, "model_prob": 0.55, "market_prob": 0.508,
            "edge": 0.042, "edge_pct": 4.2, "bookmaker": "draftkings", "confidence": "medium",
        },
    ])


def _display_parlay_results(edges):
    if edges.empty:
        st.info("No edges found above the minimum threshold.")
        return

    st.subheader(f"Found {len(edges)} Value Edges")

    for _, row in edges.iterrows():
        with st.expander(
            f"#{row['rank']} {row['player_name']} — "
            f"Edge: {row['edge_pct']}% ({row['confidence']} confidence)"
        ):
            col1, col2, col3 = st.columns(3)
            col1.metric("Model Probability", f"{row['model_prob']:.1%}")
            col2.metric("Market Probability", f"{row['market_prob']:.1%}")
            col3.metric("Edge", f"{row['edge_pct']:+.1f}%")
            st.markdown(f"**Prop:** {row['prop_type']} (line: {row.get('line', 'N/A')})")
            st.markdown(f"**Book:** {row.get('bookmaker', 'N/A')}")

    st.markdown("---")
    st.subheader("Build a Parlay")
    selected = st.multiselect(
        "Select legs for parlay evaluation",
        edges["player_name"].tolist(),
    )

    if selected and st.button("Evaluate Parlay"):
        legs = edges[edges["player_name"].isin(selected)].to_dict("records")
        st.json({
            "legs": len(legs),
            "note": "Full parlay evaluation requires trained win-probability models",
            "responsible_gambling_note": RESPONSIBLE_GAMBLING_NOTE,
        })

    st.warning(RESPONSIBLE_GAMBLING_NOTE)
