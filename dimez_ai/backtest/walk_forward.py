"""
Walk-Forward Backtesting Engine — Train on past, test on future, never leak.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import (
    BACKTEST_REPORTS_DIR,
    BACKTEST_TRAIN_SEASONS,
    BACKTEST_TEST_SEASONS,
    POSITION_GROUPS,
    SEASONS,
)
from features.builder import build_feature_table, TARGET_COL, get_feature_columns
from models.projection import ProjectionModel
from models.win_probability import WinProbabilityModel, create_prop_labels
from backtest.metrics import (
    evaluate_projection_model,
    evaluate_win_probability_model,
    format_projection_report,
    format_winprob_report,
)
from backtest.baselines import (
    naive_rolling_average_baseline,
    season_average_baseline,
    market_implied_probability_baseline,
)

logger = logging.getLogger("dimez_ai.backtest.walk_forward")


def run_walk_forward_backtest(
    all_seasons: List[int] = None,
    train_window: int = None,
    position_groups: List[str] = None,
) -> Dict:
    """
    Run full walk-forward backtest for projection models.

    Train on seasons N..N+k, test on season N+k+1.
    Roll forward and aggregate results.

    Returns dict with per-position and aggregate metrics.
    """
    all_seasons = all_seasons or SEASONS
    train_window = train_window or BACKTEST_TRAIN_SEASONS
    position_groups = position_groups or POSITION_GROUPS

    all_results = {}
    report_lines = [
        f"# Walk-Forward Backtest Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Seasons: {all_seasons}",
        f"Train window: {train_window} seasons",
        "",
    ]

    for pos in position_groups:
        pos_results = []
        report_lines.append(f"## {pos} Projection Model")
        report_lines.append("")

        for i in range(train_window, len(all_seasons)):
            test_season = all_seasons[i]
            train_seasons = all_seasons[i - train_window:i]

            logger.info(
                f"[{pos}] Train: {train_seasons}, Test: {test_season}"
            )

            # Build features
            train_df = build_feature_table(pos, train_seasons, mode="train")
            test_df = build_feature_table(pos, [test_season], mode="train")

            if train_df.empty or test_df.empty:
                logger.warning(f"[{pos}] Empty data for season {test_season}")
                continue

            feature_cols = get_feature_columns(train_df)
            if not feature_cols:
                continue

            # Train model
            model = ProjectionModel(pos)
            y_train = train_df[TARGET_COL]
            model.fit(train_df, y_train, feature_cols)

            # Predict on test set
            y_test = test_df[TARGET_COL].values
            preds = model.predict(test_df)
            y_pred = preds["p50"].values

            # Baselines
            naive_pred = naive_rolling_average_baseline(test_df)
            season_pred = season_average_baseline(test_df)

            # Evaluate
            eval_result = evaluate_projection_model(
                y_test, y_pred, naive_pred,
                model_name=f"{pos} (test={test_season})",
            )
            eval_result["test_season"] = test_season
            eval_result["position"] = pos
            pos_results.append(eval_result)

            report_lines.append(format_projection_report(eval_result))
            report_lines.append("")

        if pos_results:
            # Aggregate across test seasons
            avg_mae = np.mean([r["mae"] for r in pos_results])
            avg_rmse = np.mean([r["rmse"] for r in pos_results])
            avg_baseline_mae = np.mean([r.get("baseline_mae", 0) for r in pos_results])
            beats = sum(1 for r in pos_results if r.get("beats_baseline_mae", False))

            summary = {
                "position": pos,
                "avg_mae": avg_mae,
                "avg_rmse": avg_rmse,
                "avg_baseline_mae": avg_baseline_mae,
                "seasons_tested": len(pos_results),
                "seasons_beating_baseline": beats,
                "passes_validation": beats >= len(pos_results) // 2,
            }
            all_results[pos] = summary

            report_lines.append(f"**Summary:** Avg MAE={avg_mae:.3f}, "
                                f"Avg RMSE={avg_rmse:.3f}, "
                                f"Beats baseline {beats}/{len(pos_results)} seasons")
            report_lines.append("")

    # Save report
    report_path = _save_report(report_lines)
    all_results["report_path"] = str(report_path)

    return all_results


def run_sentiment_ablation(
    position: str = "WR",
    train_seasons: List[int] = None,
    test_season: int = None,
) -> Dict:
    """
    Backtest with and without sentiment features to validate their value.

    Returns comparison showing whether sentiment improves predictions.
    """
    train_seasons = train_seasons or [2021, 2022, 2023]
    test_season = test_season or 2024

    # Full features (with sentiment)
    train_df = build_feature_table(position, train_seasons, mode="train")
    test_df = build_feature_table(position, [test_season], mode="train")

    if train_df.empty or test_df.empty:
        return {"error": "Insufficient data for sentiment ablation"}

    all_features = get_feature_columns(train_df)
    no_sentiment = [f for f in all_features if "sentiment" not in f]

    results = {}

    for label, features in [("with_sentiment", all_features), ("without_sentiment", no_sentiment)]:
        model = ProjectionModel(position)
        model.fit(train_df, train_df[TARGET_COL], features)
        preds = model.predict(test_df)
        y_test = test_df[TARGET_COL].values
        y_pred = preds["p50"].values

        eval_result = evaluate_projection_model(
            y_test, y_pred,
            naive_rolling_average_baseline(test_df),
            model_name=f"{position} {label}",
        )
        results[label] = eval_result

    results["sentiment_helps"] = (
        results["with_sentiment"]["mae"] < results["without_sentiment"]["mae"]
    )
    results["mae_delta"] = (
        results["without_sentiment"]["mae"] - results["with_sentiment"]["mae"]
    )

    logger.info(
        f"Sentiment ablation for {position}: "
        f"helps={results['sentiment_helps']}, "
        f"MAE delta={results['mae_delta']:+.3f}"
    )
    return results


def run_win_probability_backtest(
    all_seasons: List[int] = None,
    train_window: int = None,
    prop_types: List[str] = None,
) -> Dict:
    """
    Walk-forward backtest for win-probability (prop) models.

    Train on seasons N..N+k, test on season N+k+1, evaluate with Brier score
    and a calibration curve. This mirrors run_walk_forward_backtest but for
    the classification (prop-hit) models instead of point projections.

    NOTE: Real sportsbook lines are only available for a single sample week
    right now (see ingestion/odds.py fallback data). Until real historical
    odds are ingested for every week, labels are generated against each
    player's median stat value for the fold (see create_prop_labels), and
    there is no real market-probability baseline to compare against — that
    comparison is skipped here rather than faked.
    """
    from models.win_probability import WinProbabilityModel, create_prop_labels
    from models.retrain import _prop_type_to_stat, _prop_type_to_position

    all_seasons = all_seasons or SEASONS
    train_window = train_window or BACKTEST_TRAIN_SEASONS
    prop_types = prop_types or [
        "player_over_receiving_yards",
        "player_over_rushing_yards",
        "player_over_passing_yards",
        "player_over_receptions",
    ]

    all_results = {}
    report_lines = ["## Win-Probability (Prop) Models", ""]

    for prop_type in prop_types:
        stat_col = _prop_type_to_stat(prop_type)
        pos = _prop_type_to_position(prop_type)
        prop_results = []

        for i in range(train_window, len(all_seasons)):
            test_season = all_seasons[i]
            train_seasons = all_seasons[i - train_window:i]

            train_df = build_feature_table(pos, train_seasons, mode="train")
            test_df = build_feature_table(pos, [test_season], mode="train")

            if train_df.empty or test_df.empty:
                logger.warning(f"[{prop_type}] Empty data for season {test_season}")
                continue

            train_labels = create_prop_labels(train_df, "over", stat_col=stat_col)
            test_labels = create_prop_labels(test_df, "over", stat_col=stat_col)

            if train_labels.sum() == 0 or test_labels.nunique() < 2:
                logger.warning(f"[{prop_type}] Degenerate labels for season {test_season}, skipping")
                continue

            model = WinProbabilityModel(prop_type)
            model.fit(train_df, train_labels)
            y_prob = model.predict_proba(test_df)

            eval_result = evaluate_win_probability_model(
                test_labels.values, y_prob,
                model_name=f"{prop_type} (test={test_season})",
            )
            eval_result["test_season"] = test_season
            prop_results.append(eval_result)

            report_lines.append(format_winprob_report(eval_result))
            report_lines.append("")

        if prop_results:
            avg_brier = float(np.mean([r["brier_score"] for r in prop_results]))
            all_results[prop_type] = {
                "prop_type": prop_type,
                "avg_brier_score": avg_brier,
                "seasons_tested": len(prop_results),
            }
            report_lines.append(f"**Summary:** {prop_type} Avg Brier Score={avg_brier:.4f} "
                                 f"(0=perfect, 0.25=uninformed coin-flip)")
            report_lines.append("")
        else:
            report_lines.append(f"**{prop_type}:** insufficient data to backtest — skipped.")
            report_lines.append("")

    all_results["report_lines"] = report_lines
    return all_results


def run_full_backtest(all_seasons: List[int] = None, train_window: int = None) -> Dict:
    """
    Run projection backtest + win-probability backtest + sentiment ablation,
    and persist ALL of it into a single versioned report file.

    Previously these ran as separate, disconnected pieces and the
    win-probability and sentiment results were never actually written to
    a report — this is the entry point that fixes that.
    """
    all_seasons = all_seasons or SEASONS
    train_window = train_window or BACKTEST_TRAIN_SEASONS

    combined_lines = [
        "# Walk-Forward Backtest Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Seasons: {all_seasons}",
        f"Train window: {train_window} seasons",
        "",
    ]

    # --- Projection models ---
    proj_results = run_walk_forward_backtest(all_seasons, train_window)
    # run_walk_forward_backtest already wrote its own report; reuse its lines
    # by re-reading them so everything ends up in one combined file.
    proj_report_path = Path(proj_results.get("report_path", ""))
    if proj_report_path.exists():
        combined_lines.append(proj_report_path.read_text().split("\n\n", 1)[-1])

    # --- Win-probability models ---
    winprob_results = run_win_probability_backtest(all_seasons, train_window)
    combined_lines.append("\n".join(winprob_results.pop("report_lines", [])))

    # --- Sentiment ablation ---
    combined_lines.append("## Sentiment Feature Ablation")
    combined_lines.append("")
    sentiment_result = run_sentiment_ablation()
    if "error" in sentiment_result:
        combined_lines.append(f"Skipped: {sentiment_result['error']}")
    else:
        helps = sentiment_result["sentiment_helps"]
        delta = sentiment_result["mae_delta"]
        combined_lines.append(f"- With sentiment MAE: {sentiment_result['with_sentiment']['mae']:.3f}")
        combined_lines.append(f"- Without sentiment MAE: {sentiment_result['without_sentiment']['mae']:.3f}")
        combined_lines.append(f"- MAE delta (positive = sentiment helps): {delta:+.3f}")
        combined_lines.append(f"- **Sentiment feature decision: {'KEEP' if helps else 'EXCLUDE'}**")
    combined_lines.append("")

    report_path = _save_report(combined_lines)

    return {
        "projection": proj_results,
        "win_probability": winprob_results,
        "sentiment_ablation": sentiment_result,
        "report_path": str(report_path),
    }


def _save_report(lines: List[str]) -> Path:
    """Save backtest report to versioned markdown file."""
    timestamp = datetime.now().strftime("%Y-W%W")
    report_path = BACKTEST_REPORTS_DIR / f"{timestamp}.md"

    with open(report_path, "w") as f:
        f.write("\n".join(lines))

    logger.info(f"Backtest report saved to {report_path}")
    return report_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run walk-forward backtest")
    parser.add_argument("--seasons", nargs="+", type=int, default=SEASONS)
    parser.add_argument("--train-window", type=int, default=BACKTEST_TRAIN_SEASONS)
    parser.add_argument("--sentiment-ablation", action="store_true")
    args = parser.parse_args()

    if args.sentiment_ablation:
        result = run_sentiment_ablation()
        print(f"Sentiment helps: {result.get('sentiment_helps')}")
        print(f"MAE delta: {result.get('mae_delta', 0):+.3f}")
    else:
        results = run_walk_forward_backtest(args.seasons, args.train_window)
        for pos, summary in results.items():
            if pos == "report_path":
                continue
            print(f"{pos}: MAE={summary['avg_mae']:.3f}, "
                  f"passes={summary['passes_validation']}")
        print(f"Report: {results.get('report_path')}")