import nltk
from sentence_transformers import SentenceTransformer, util

try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    nltk.download("punkt_tab", quiet=True)
from nltk.tokenize import sent_tokenize

model = SentenceTransformer("all-MiniLM-L6-v2")

conditions = {
    "muddy":
        [
            "the trail was muddy",
            "so much mud out there today, bring waterproof boots",
            "muddy conditions underfoot",
            "is the trail still muddy after all the rain?",
            "boots sank into the mud in several spots",
        ],
    "slippery":
        [
            "watch your step, it's super slick out there",
            "slippery when wet",
            "lost my footing a couple times",
            "kept sliding and almost fell several times",
            "hard to keep your balance, very slick underfoot",
        ],
    "icy":
        [
            "the trail was icy in the shaded sections",
            "watch out, there's ice near the summit",
            "icy patches made the descent tricky",
            "do we need microspikes for the ice right now?",
            "black ice on the boardwalk caught us off guard",
        ],
    "snowy":
        [
            "the trail was covered in snow",
            "deep snow made the hike slow going",
            "snowshoes recommended, it's snowy up there",
            "is there still snow on the trail this time of year?",
            "packed snow the whole way up, bring traction",
        ],
    "flooded":
        [
            "the creek crossing was flooded",
            "parts of the trail were underwater after the storm",
            "flooded out near the bridge, had to turn back",
            "is the low section still flooded?",
            "water was ankle deep across the path in a few spots",
        ],
}

conditions_embeddings = {
    condition: model.encode(phrases, convert_to_tensor=True)
    for condition, phrases in conditions.items()
}

# Baseline reference phrases - things reviews commonly say that have nothing to
# do with trail conditions. A sentence only counts as a condition match if it
# beats its best baseline score by MARGIN, not just clears some absolute cutoff.
# See LABEL_CONDITIONS.md: raw thresholds let irrelevant sentences ("Great
# trail...") score deceptively close to true condition mentions, since general
# sentence embeddings aren't well-calibrated in absolute terms.
#
# Split into neutral (positive/unremarkable) and negative (complaints unrelated
# to mud/ice/slippery conditions) - a negative-but-unrelated sentence like "the
# bugs were unbearable" wouldn't be caught by neutral phrases alone, since it
# shares negative tone with condition phrases without sharing their content.
neutral_phrases = [
    "nice views along the trail",
    "great hike overall",
    "not many people out today",
    "took a nice detour to the lookout",
    "would recommend this trail",
]
negative_phrases = [
    "the bugs were unbearable",
    "trail was way too crowded",
    "parking lot was a mess",
    "signage was confusing and we got lost",
    "the heat was brutal",
]
baseline_phrases = neutral_phrases + negative_phrases
baseline_embeddings = model.encode(baseline_phrases, convert_to_tensor=True)

MARGIN = 0.1


def best_match(sentence_embedding, reference_embeddings, reference_phrases):
    scores = util.cos_sim(sentence_embedding, reference_embeddings)[0]
    best_idx = int(scores.argmax())
    return float(scores[best_idx]), reference_phrases[best_idx]


def label_comment(comment):
    """Return ({category: bool}, [match detail dicts]) for one review comment.

    A category is True if any sentence in the comment beats its best baseline
    score by MARGIN against that category's reference phrases.
    """
    matched = {condition: False for condition in conditions}
    details = []

    sentences = [s.strip() for s in sent_tokenize(comment or "") if s.strip()]
    if not sentences:
        return matched, details

    sentence_embeddings = model.encode(sentences, convert_to_tensor=True)

    for i, sentence in enumerate(sentences):
        baseline_score, _ = best_match(sentence_embeddings[i], baseline_embeddings, baseline_phrases)

        for condition, phrases in conditions.items():
            condition_score, condition_phrase = best_match(
                sentence_embeddings[i], conditions_embeddings[condition], phrases
            )
            margin = condition_score - baseline_score
            if margin >= MARGIN:
                matched[condition] = True
                details.append({
                    "category": condition,
                    "sentence": sentence,
                    "matched_phrase": condition_phrase,
                    "score": condition_score,
                    "margin": margin,
                })

    # Mud and ice are common direct causes of slippery footing - treat a mud
    # or ice match as implying slippery too, rather than relying on the
    # embedding model to independently rediscover that correlation (it does
    # so inconsistently - see LABEL_CONDITIONS.md).
    if matched["muddy"] or matched["icy"]:
        matched["slippery"] = True

    return matched, details


if __name__ == "__main__":
    comment = (
        "Great trail, not many people, we took the detour to see the lookout and that was great. \n"
        "As of April 25, there’s still some ice on the trail but totally manageable, especially "
        "with hiking shoes . Some parts are muddy from the melting ice and running water."
    )
    sentences = [s.strip() for s in sent_tokenize(comment) if s.strip()]
    sentence_embeddings = model.encode(sentences, convert_to_tensor=True)

    for i, sentence in enumerate(sentences):
        baseline_score, baseline_phrase = best_match(sentence_embeddings[i], baseline_embeddings, baseline_phrases)

        print(f"\n{sentence}")
        print(f"  baseline: {baseline_score:.4f}  (\"{baseline_phrase}\")")

        for condition, phrases in conditions.items():
            condition_score, condition_phrase = best_match(
                sentence_embeddings[i], conditions_embeddings[condition], phrases
            )
            margin = condition_score - baseline_score
            is_match = margin >= MARGIN
            flag = "MATCH" if is_match else "no match"
            print(
                f"  {condition:10s} {condition_score:.4f}  margin={margin:+.4f}  "
                f"[{flag}]  (\"{condition_phrase}\")"
            )
