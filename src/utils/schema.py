"""Schema validation for flight pricing datasets.

Used in production CI to ensure data integrity before training.
"""
import pandas as pd


EXPECTED_COLUMNS = [
    'airline', 'flight_id', 'source_city', 'departure_time',
    'stops', 'arrival_time', 'destination_city', 'class',
    'duration', 'days_left', 'price', 'event_timestamp', 'route'
]

CATEGORICAL_COLUMNS = [
    'airline', 'source_city', 'departure_time',
    'stops', 'arrival_time', 'destination_city', 'class', 'route'
]

NUMERIC_COLUMNS = ['duration', 'days_left', 'price']

# Valid value ranges / known categories
VALID_AIRLINES = [
    'Vistara', 'Air_India', 'Indigo', 'GO_FIRST', 'AirAsia', 'SpiceJet'
]

VALID_CITIES = [
    'Delhi', 'Mumbai', 'Bangalore', 'Kolkata', 'Hyderabad', 'Chennai'
]

VALID_STOPS = ['zero', 'one', 'two_or_more']

VALID_TIMES = ['Early_Morning', 'Morning', 'Afternoon', 'Evening', 'Night', 'Late_Night']

VALID_CLASSES = ['Economy', 'Business']


class SchemaValidationError(Exception):
    """Raised when data fails schema validation."""
    pass


def validate_columns(df: pd.DataFrame) -> list:
    """Check that all expected columns are present."""
    errors = []
    missing = set(EXPECTED_COLUMNS) - set(df.columns)
    extra = set(df.columns) - set(EXPECTED_COLUMNS) - {'Unnamed: 0'}
    if missing:
        errors.append(f"Missing columns: {missing}")
    if extra:
        errors.append(f"Unexpected columns: {extra}")
    return errors


def validate_dtypes(df: pd.DataFrame) -> list:
    """Check numeric columns are numeric."""
    errors = []
    for col in NUMERIC_COLUMNS:
        if col in df.columns and not pd.api.types.is_numeric_dtype(df[col]):
            errors.append(f"Column '{col}' should be numeric, got {df[col].dtype}")
    return errors


def validate_categories(df: pd.DataFrame) -> list:
    """Check categorical values are within known sets."""
    errors = []
    checks = {
        'airline': VALID_AIRLINES,
        'source_city': VALID_CITIES,
        'destination_city': VALID_CITIES,
        'stops': VALID_STOPS,
        'departure_time': VALID_TIMES,
        'arrival_time': VALID_TIMES,
        'class': VALID_CLASSES,
    }
    for col, valid_values in checks.items():
        if col in df.columns:
            invalid = set(df[col].unique()) - set(valid_values)
            if invalid:
                errors.append(f"Column '{col}' has invalid values: {invalid}")
    return errors


def validate_ranges(df: pd.DataFrame) -> list:
    """Check numeric values are within reasonable ranges."""
    errors = []
    if 'duration' in df.columns:
        if df['duration'].min() < 0:
            errors.append(f"'duration' has negative values (min={df['duration'].min()})")
        if df['duration'].max() > 100:
            errors.append(f"'duration' exceeds 100 hours (max={df['duration'].max()})")

    if 'days_left' in df.columns:
        if df['days_left'].min() < 0:
            errors.append(f"'days_left' has negative values")
        if df['days_left'].max() > 365:
            errors.append(f"'days_left' exceeds 365 days")

    if 'price' in df.columns:
        if df['price'].min() < 0:
            errors.append(f"'price' has negative values")
    return errors


def validate_nulls(df: pd.DataFrame) -> list:
    """Check for null values in critical columns."""
    errors = []
    present_cols = [c for c in EXPECTED_COLUMNS if c in df.columns]
    if not present_cols:
        return errors
    null_counts = df[present_cols].isnull().sum()
    cols_with_nulls = null_counts[null_counts > 0]
    if len(cols_with_nulls) > 0:
        for col, count in cols_with_nulls.items():
            errors.append(f"Column '{col}' has {count} null values")
    return errors


def validate_schema(df: pd.DataFrame, strict: bool = False) -> dict:
    """Run all schema validations.

    Args:
        df: DataFrame to validate.
        strict: If True, raise SchemaValidationError on any failure.

    Returns:
        dict with 'valid' bool and 'errors' list.
    """
    all_errors = []
    all_errors.extend(validate_columns(df))
    all_errors.extend(validate_dtypes(df))
    all_errors.extend(validate_categories(df))
    all_errors.extend(validate_ranges(df))
    all_errors.extend(validate_nulls(df))

    result = {
        "valid": len(all_errors) == 0,
        "errors": all_errors,
        "rows": len(df),
        "columns": list(df.columns),
    }

    if strict and not result["valid"]:
        raise SchemaValidationError(
            f"Schema validation failed with {len(all_errors)} error(s):\n"
            + "\n".join(f"  - {e}" for e in all_errors)
        )

    return result


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/dev_train.csv"
    df = pd.read_csv(path)
    result = validate_schema(df)
    print(f"Valid: {result['valid']}")
    for err in result['errors']:
        print(f"  ERROR: {err}")
    sys.exit(0 if result['valid'] else 1)
