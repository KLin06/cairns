import os
import sys

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import classification_report, precision_recall_curve, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

from scripts.paths import DATASETS_DIR

TABLE_PATH = os.path.join(DATASETS_DIR, "training_table", "reviews.csv")
MODEL_DIR = os.path.join(DATASETS_DIR, "models")

# Columns that identify a row rather than describe it - never a feature,
# never a target. trailId still gets pulled out separately for the
# group-aware train/test split (see split_by_trail), just not fed to the
# model as an input.
ID_COLUMNS = ["reviewId", "trailId"]

# String columns HistGradientBoostingClassifier needs as pandas `category`
# dtype (not raw object/str) to use its native categorical_features="from_dtype"
# support - everything else in the table is already numeric or bool.
CATEGORICAL_COLUMNS = ["terrain_rockSlipRisk", "terrain_soilTextureGroup"]

# Canonical condition categories - matches CONDITION_CATEGORY_MAP's mapped
# values in enrich_review.py exactly (dusty already excluded there - too
# few positive examples to learn or evaluate anything meaningful from,
# see MODEL_NOTES.md), which is the actual source of truth for what
# conditions exist. Hardcoded rather than discovered by scanning
# df.columns for a "condition_" prefix - that was just re-deriving this
# same fixed list with extra code and an extra df argument on every
# caller.
CONDITIONS = ["bugs", "flooded", "icy", "muddy", "slippery", "snow"]
CONDITION_COLUMNS = [f"condition_{c}" for c in CONDITIONS]


def load_training_table():
    df = pd.read_csv(TABLE_PATH)
    for col in CATEGORICAL_COLUMNS:
        if col in df.columns:
            df[col] = df[col].astype("category")
    return df


def feature_columns(df):
    return [c for c in df.columns if c not in ID_COLUMNS and c not in CONDITION_COLUMNS]


def split_by_trail(df, test_size=0.2, random_state=0):
    """Hold out whole trails, not random rows - reviews on the same trail
    share near-identical weather/terrain, so a random row split lets a
    model see near-duplicates of held-out rows during training and
    overstates how well it'll generalize to a trail it's never seen.

    Falls back to a plain random row split when df only has one trail in
    it (nothing to hold a whole trail out from yet) - not a real
    generalization test, just enough to sanity-check the training code
    while more trails are still being enriched."""
    if df["trailId"].nunique() < 2:
        print(
            "warning: only one trail in this split - falling back to a random row "
            "split, which does NOT test generalization to a new trail"
        )
        return train_test_split(df, test_size=test_size, random_state=random_state)

    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
    train_idx, test_idx = next(splitter.split(df, groups=df["trailId"]))
    return df.iloc[train_idx], df.iloc[test_idx]


def _drop_zero_variance(train_df, features):
    """A column with fewer than 2 distinct non-null values (fully
    constant, or fully NaN) carries no information for a tree to split on
    - and HistGradientBoostingClassifier's binning step crashes outright
    on an all-NaN/all-constant column rather than ignoring it, so this
    isn't optional. Still happens routinely even with 63 trails in the
    table (feature_Caves, feature_Dog-friendly, feature_Lakes, etc. are
    each only present on a handful of trails)."""
    kept = []
    for col in features:
        if train_df[col].nunique(dropna=True) < 2:
            print(f"dropping {col}: no variance in the training split")
            continue
        kept.append(col)
    return kept


def _best_threshold(y_true, proba):
    """Pick the probability cutoff that maximizes F1 on the
    precision-recall curve, instead of assuming 0.5. With positive rates
    as low as 7-8% for some conditions, 0.5 makes the model demand
    near-certainty before predicting "yes," which tanks recall even when
    the model is ranking correctly (the gap between decent ROC-AUC and
    very low recall at 0.5 in the eval that prompted this)."""
    precision, recall, thresholds = precision_recall_curve(y_true, proba)
    # precision_recall_curve returns one more precision/recall point than
    # thresholds (the last point is recall=0 with no corresponding
    # threshold) - drop it so the arrays line up.
    f1 = 2 * precision[:-1] * recall[:-1] / (precision[:-1] + recall[:-1] + 1e-12)
    return float(thresholds[f1.argmax()])


def train_condition_models(df):
    """One binary HistGradientBoostingClassifier per condition (see
    CONDITION_COLUMNS), not one shared multi-class model - mud,
    ice, and slippery don't necessarily depend on the same features the
    same way, and training them as separate yes/no questions keeps each
    one free to learn its own decision boundary instead of a single model
    having to compromise across every condition at once.

    Three-way split, all grouped by trail: fit (train the model) / val
    (pick each condition's probability threshold off its own
    precision-recall curve) / test (final, never-touched-until-now
    evaluation). Picking the threshold from the same data used to
    evaluate it would make the reported metrics optimistic - val exists
    specifically so test stays honest.

    Returns ({condition: fitted_model}, feature_columns_used,
    {condition: threshold})."""
    train_df, test_df = split_by_trail(df)
    fit_df, val_df = split_by_trail(train_df, random_state=1)
    features = _drop_zero_variance(fit_df, feature_columns(df))

    X_fit, X_val, X_test = fit_df[features], val_df[features], test_df[features]

    models = {}
    thresholds = {}
    for condition in CONDITION_COLUMNS:
        y_fit, y_val, y_test = fit_df[condition], val_df[condition], test_df[condition]

        if y_fit.nunique() < 2:
            print(f"skipping {condition}: only one class present in the fit split ({y_fit.iloc[0]})")
            continue

        # class_weight="balanced" reweights the loss so a missed positive
        # costs as much as a missed negative - without it, a condition
        # with a 7-8% positive rate lets the model minimize loss by
        # defaulting to "False" almost everywhere.
        model = HistGradientBoostingClassifier(
            categorical_features="from_dtype", class_weight="balanced", random_state=0
        )
        model.fit(X_fit, y_fit)

        if y_val.nunique() == 2:
            val_proba = model.predict_proba(X_val)[:, 1]
            threshold = _best_threshold(y_val, val_proba)
        else:
            print(f"{condition}: only one class in the val split, falling back to threshold=0.5")
            threshold = 0.5

        print(f"\n=== {condition} (threshold={threshold:.3f}) ===")
        if y_test.nunique() == 2:
            test_proba = model.predict_proba(X_test)[:, 1]
            pred = test_proba >= threshold
            print(classification_report(y_test, pred, zero_division=0))
            print(f"ROC-AUC: {roc_auc_score(y_test, test_proba):.3f}")
        else:
            print(f"only one class in the test split ({y_test.iloc[0]}) - can't evaluate")

        models[condition] = model
        thresholds[condition] = threshold

    return models, features, thresholds


def save_models(models, features, thresholds):
    os.makedirs(MODEL_DIR, exist_ok=True)
    path = os.path.join(MODEL_DIR, "condition_models.joblib")
    joblib.dump({"models": models, "features": features, "thresholds": thresholds}, path)
    print(f"\nsaved {len(models)} condition model(s) to {path}")
    return path


# test: python -m scripts.model.train_model
if __name__ == "__main__":
    if not os.path.exists(TABLE_PATH):
        sys.exit(f"no training table at {TABLE_PATH} - run scripts.model.build_training_table first")

    df = load_training_table()
    models, features, thresholds = train_condition_models(df)
    save_models(models, features, thresholds)
