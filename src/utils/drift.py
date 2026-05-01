"""Model drift detection using Population Stability Index (PSI).

Used in the develop→main CI pipeline to detect distribution shifts
between training data and new production data.
"""
import numpy as np
import pandas as pd


def compute_psi(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """Compute Population Stability Index between two distributions.

    PSI < 0.1  → no significant shift
    PSI 0.1–0.2 → moderate shift (monitor)
    PSI > 0.2  → significant shift (investigate)

    Args:
        reference: Array of values from reference (training) distribution.
        current: Array of values from current (new) distribution.
        bins: Number of bins for histogram.

    Returns:
        PSI value (float).
    """
    # Create bins based on reference distribution
    min_val = min(reference.min(), current.min())
    max_val = max(reference.max(), current.max())
    bin_edges = np.linspace(min_val, max_val, bins + 1)

    # Compute histograms as proportions
    ref_counts, _ = np.histogram(reference, bins=bin_edges)
    cur_counts, _ = np.histogram(current, bins=bin_edges)

    # Convert to proportions, avoid zero
    ref_pct = (ref_counts + 1e-6) / (ref_counts.sum() + bins * 1e-6)
    cur_pct = (cur_counts + 1e-6) / (cur_counts.sum() + bins * 1e-6)

    # PSI formula
    psi = np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct))
    return float(psi)


def compute_categorical_psi(reference: pd.Series, current: pd.Series) -> float:
    """Compute PSI for categorical features.

    Uses frequency distributions instead of histogram bins.
    """
    all_cats = set(reference.unique()) | set(current.unique())

    ref_counts = reference.value_counts(normalize=True)
    cur_counts = current.value_counts(normalize=True)

    psi = 0.0
    for cat in all_cats:
        ref_pct = ref_counts.get(cat, 1e-6)
        cur_pct = cur_counts.get(cat, 1e-6)
        psi += (cur_pct - ref_pct) * np.log(cur_pct / ref_pct)

    return float(psi)


def check_drift(reference_path: str, current_path: str,
                threshold: float = 0.2,
                numeric_cols: list = None,
                categorical_cols: list = None) -> dict:
    """Check for data drift between reference and current datasets.

    Args:
        reference_path: Path to reference CSV (e.g., training data).
        current_path: Path to current CSV (e.g., new production data).
        threshold: PSI threshold above which drift is flagged.
        numeric_cols: List of numeric columns to check.
        categorical_cols: List of categorical columns to check.

    Returns:
        dict with 'passed', 'details' per feature, and 'summary'.
    """
    if numeric_cols is None:
        numeric_cols = ['duration', 'days_left', 'price']
    if categorical_cols is None:
        categorical_cols = ['airline', 'source_city', 'destination_city',
                            'class', 'stops', 'departure_time', 'arrival_time']

    ref_df = pd.read_csv(reference_path)
    cur_df = pd.read_csv(current_path)

    details = {}
    drifted_features = []

    # Check numeric features
    for col in numeric_cols:
        if col in ref_df.columns and col in cur_df.columns:
            psi = compute_psi(
                ref_df[col].dropna().values,
                cur_df[col].dropna().values
            )
            status = "DRIFT" if psi > threshold else "OK"
            details[col] = {"psi": round(psi, 4), "status": status, "type": "numeric"}
            if psi > threshold:
                drifted_features.append(col)

    # Check categorical features
    for col in categorical_cols:
        if col in ref_df.columns and col in cur_df.columns:
            psi = compute_categorical_psi(ref_df[col], cur_df[col])
            status = "DRIFT" if psi > threshold else "OK"
            details[col] = {"psi": round(psi, 4), "status": status, "type": "categorical"}
            if psi > threshold:
                drifted_features.append(col)

    passed = len(drifted_features) == 0
    return {
        "passed": passed,
        "threshold": threshold,
        "drifted_features": drifted_features,
        "details": details,
        "summary": f"{'PASSED' if passed else 'FAILED'}: "
                   f"{len(drifted_features)}/{len(details)} features show drift"
    }


if __name__ == "__main__":
    import sys
    import json
    ref = sys.argv[1] if len(sys.argv) > 1 else "data/dev_train.csv"
    cur = sys.argv[2] if len(sys.argv) > 2 else "data/staging_train.csv"
    result = check_drift(ref, cur)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['passed'] else 1)
