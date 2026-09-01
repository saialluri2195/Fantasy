"""
Ingestion Utilities — Data quality, versioning, idempotency helpers.

Every ingestion script uses these shared utilities to ensure:
- Versioned output paths (season + week stamped)
- Data quality logging (row counts, null rates)
- Loud failures on empty/stale data (never silently return empty)
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger("dimez_ai.ingestion")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)


class DataQualityError(Exception):
    """Raised when data quality checks fail."""
    pass


class DataSourceError(Exception):
    """Raised when a data source is unreachable or returns invalid data."""
    pass


def version_path(
    base_dir: Path,
    prefix: str,
    season: int,
    week: Optional[int] = None,
    ext: str = ".parquet",
) -> Path:
    """
    Generate a versioned file path.

    Examples:
        version_path(dir, "weekly_stats", 2023, 5)  -> dir/weekly_stats_2023_w05.parquet
        version_path(dir, "adp", 2023)               -> dir/adp_2023.parquet
    """
    if week is not None:
        filename = f"{prefix}_{season}_w{week:02d}{ext}"
    else:
        filename = f"{prefix}_{season}{ext}"
    return base_dir / filename


def ensure_not_empty(df: pd.DataFrame, source_name: str) -> None:
    """
    Raise DataQualityError if the DataFrame is empty.

    This is critical: we never silently return empty data from a failed pull.
    A failed pull must be distinguishable from a pull that legitimately
    returned no rows.
    """
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        raise DataQualityError(
            f"Data source '{source_name}' returned empty data. "
            f"This may indicate a failed pull or an API/source issue. "
            f"Refusing to proceed with stale data."
        )


def log_data_quality(df: pd.DataFrame, source_name: str) -> dict:
    """
    Log and return data quality metrics for a pulled DataFrame.

    Returns a dict with quality metrics for downstream logging/auditing.
    """
    n_rows = len(df)
    n_cols = len(df.columns)

    # Null rates per column
    null_rates = (df.isnull().sum() / max(n_rows, 1)).to_dict()
    high_null_cols = {
        col: rate for col, rate in null_rates.items() if rate > 0.5
    }

    # Column types
    dtypes = df.dtypes.astype(str).to_dict()

    quality_report = {
        "source": source_name,
        "rows": n_rows,
        "columns": n_cols,
        "null_rates": null_rates,
        "high_null_columns": high_null_cols,
        "dtypes": dtypes,
    }

    logger.info(
        f"[{source_name}] Pulled {n_rows} rows, {n_cols} columns. "
        f"High-null columns (>50%): {list(high_null_cols.keys()) or 'none'}"
    )

    if high_null_cols:
        logger.warning(
            f"[{source_name}] Columns with >50% nulls: {high_null_cols}"
        )

    return quality_report


def is_stale(filepath: Path, max_age_hours: float = 168.0) -> bool:
    """
    Check if a file is older than max_age_hours (default: 1 week).
    Returns True if the file doesn't exist or is stale.
    """
    if not filepath.exists():
        return True

    import time
    age_hours = (time.time() - filepath.stat().st_mtime) / 3600
    return age_hours > max_age_hours


def save_versioned(
    df: pd.DataFrame,
    base_dir: Path,
    prefix: str,
    season: int,
    week: Optional[int] = None,
    overwrite: bool = False,
) -> Path:
    """
    Save a DataFrame to a versioned parquet file.

    Returns the path where the file was saved.
    Skips if file already exists and overwrite=False (idempotency).
    """
    filepath = version_path(base_dir, prefix, season, week)

    if filepath.exists() and not overwrite:
        logger.info(
            f"[{prefix}] File already exists: {filepath}. "
            f"Skipping (idempotent). Set overwrite=True to force."
        )
        return filepath

    filepath.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(filepath, index=False, engine="pyarrow")
    logger.info(f"[{prefix}] Saved {len(df)} rows to {filepath}")
    return filepath


def load_versioned(
    base_dir: Path,
    prefix: str,
    season: int,
    week: Optional[int] = None,
) -> pd.DataFrame:
    """
    Load a versioned parquet file.

    Raises FileNotFoundError if the file doesn't exist.
    """
    filepath = version_path(base_dir, prefix, season, week)

    if not filepath.exists():
        raise FileNotFoundError(
            f"Versioned data file not found: {filepath}. "
            f"Run the corresponding ingestion script first."
        )

    df = pd.read_parquet(filepath, engine="pyarrow")
    logger.info(f"[{prefix}] Loaded {len(df)} rows from {filepath}")
    return df
