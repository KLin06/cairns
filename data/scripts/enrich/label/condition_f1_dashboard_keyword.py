import json
import os

import matplotlib.pyplot as plt

from scripts.paths import DATASETS_DIR
from scripts.enrich.label.label_conditions_keyword import label_comment, conditions, MODEL_NAME

TRAIL_ID = "10268327"

CATEGORIES = list(conditions.keys())


def evaluate(labeled_reviews):
    """Run label_comment on each manually-labeled comment, compare against its
    manual ground truth, and return per-category confusion counts plus a few
    example sentences for each of TP / FP / FN.
    """
    counts = {category: {"TP": 0, "FP": 0, "FN": 0, "TN": 0} for category in CATEGORIES}
    examples = {category: {"TP": [], "FP": [], "FN": []} for category in CATEGORIES}

    for review in labeled_reviews:
        truth = review["labels"]
        predicted, details = label_comment(review.get("comment"))

        sentence_by_category = {}
        for d in details:
            sentence_by_category.setdefault(d["category"], d["sentence"])

        for category in CATEGORIES:
            is_true = truth[category]
            is_pred = predicted[category]

            if is_true and is_pred:
                outcome = "TP"
            elif is_pred and not is_true:
                outcome = "FP"
            elif is_true and not is_pred:
                outcome = "FN"
            else:
                outcome = "TN"

            counts[category][outcome] += 1

            if outcome in ("TP", "FP") and len(examples[category][outcome]) < 3:
                examples[category][outcome].append(sentence_by_category.get(category, review.get("comment", "")))
            elif outcome == "FN" and len(examples[category]["FN"]) < 3:
                examples[category]["FN"].append(review.get("comment", ""))

    return counts, examples


def precision_recall_f1(c):
    tp, fp, fn = c["TP"], c["FP"], c["FN"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def build_dashboard(counts, examples, sample_size, out_path):
    categories = list(counts.keys())
    metrics = {c: precision_recall_f1(counts[c]) for c in categories}

    fig = plt.figure(figsize=(12, 9))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.1, 1])

    # --- Top: grouped bar chart of precision/recall/F1 per category ---
    ax = fig.add_subplot(gs[0])
    x = range(len(categories))
    width = 0.25

    precisions = [metrics[c][0] for c in categories]
    recalls = [metrics[c][1] for c in categories]
    f1s = [metrics[c][2] for c in categories]

    ax.bar([i - width for i in x], precisions, width, label="Precision", color="#6ba3d6")
    ax.bar(x, recalls, width, label="Recall", color="#f4a261")
    bars_f1 = ax.bar([i + width for i in x], f1s, width, label="F1", color="#2a9d8f")

    for bar, f1 in zip(bars_f1, f1s):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02, f"{f1:.2f}",
                 ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax.set_xticks(list(x))
    ax.set_xticklabels(categories)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("score")
    ax.set_title(
        f"Condition detector ({MODEL_NAME} + negation-aware keyword check) vs manually labeled reviews — "
        f"trail {TRAIL_ID}, n={sample_size} reviews"
    )
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.3)

    for i, category in enumerate(categories):
        c = counts[category]
        ax.text(i, -0.09, f"TP={c['TP']} FP={c['FP']} FN={c['FN']}",
                 ha="center", va="top", fontsize=8, color="#555555", transform=ax.get_xaxis_transform())

    # --- Bottom: example reviews of different match types, per category ---
    ax2 = fig.add_subplot(gs[1])
    ax2.axis("off")

    lines = ["Example matches (sentence-level) and misses (review-level):", ""]
    for category in categories:
        lines.append(f"[{category}]")
        for outcome, label in (("TP", "hit"), ("FP", "false alarm"), ("FN", "missed")):
            ex = examples[category][outcome]
            if not ex:
                continue
            snippet = ex[0]
            if len(snippet) > 90:
                snippet = snippet[:87] + "..."
            lines.append(f"  {label:12s}: \"{snippet}\"")
        lines.append("")

    ax2.text(0.01, 0.98, "\n".join(lines), transform=ax2.transAxes,
              va="top", ha="left", fontsize=9, family="monospace")

    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"saved dashboard to {out_path}")


if __name__ == "__main__":
    labels_path = os.path.join(DATASETS_DIR, "manual_labels", f"{TRAIL_ID}.json")
    with open(labels_path, "r", encoding="utf-8") as f:
        labeled_reviews = json.load(f)

    print(f"evaluating on {len(labeled_reviews)} manually labeled reviews")

    counts, examples = evaluate(labeled_reviews)

    for category, c in counts.items():
        p, r, f1 = precision_recall_f1(c)
        print(f"{category:10s} P={p:.2f} R={r:.2f} F1={f1:.2f}  (TP={c['TP']} FP={c['FP']} FN={c['FN']} TN={c['TN']})")

    out_path = os.path.join(DATASETS_DIR, "dashboards", "condition_f1_dashboard_keyword.png")
    build_dashboard(counts, examples, len(labeled_reviews), out_path)
