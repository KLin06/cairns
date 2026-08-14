import re

import nltk
from sentence_transformers import SentenceTransformer, util

try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    nltk.download("punkt_tab", quiet=True)
from nltk.tokenize import sent_tokenize

# Adds a negation-aware keyword check on top of label_conditions.py's
# margin-based embedding approach, and splits the single label_comment
# function into smaller single-purpose pieces. Same MiniLM model/reference
# phrases/margin as the baseline - kept as a separate file rather than
# editing label_conditions.py so the two can be compared independently.
# See LABEL_CONDITIONS.md "keyword + negation experiment".
MODEL_NAME = "all-MiniLM-L6-v2"
model = SentenceTransformer(MODEL_NAME)

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

# Direct-mention keywords per category. Deliberately narrow (word stems, not
# phrasing variety) - broad paraphrase coverage is the embedding check's job;
# this is a cheap, high-precision net for blunt mentions the embedding
# sometimes misses, e.g. "Mud everywhere" scoring lower than expected.
KEYWORDS = {
    "muddy": ["mud", "muddy", "muddier", "muddiest"],
    "slippery": ["slippery", "slick", "slippy"],
    "icy": ["ice", "icy", "iced"],
    "snowy": ["snow", "snowy", "snowing", "snowed"],
    "flooded": ["flood", "flooded", "flooding", "underwater"],
}

# Negation cues checked in the NEGATION_WINDOW tokens before a keyword, e.g.
# "not muddy", "wasn't icy", "no snow to speak of". Not exhaustive (misses
# "far from muddy", scope-crossing negation, etc.) - a cheap heuristic, not a
# full negation parser.
NEGATION_WORDS = {"not", "no", "never", "without", "hardly", "cannot"}
NEGATION_WINDOW = 4


def _is_negation_cue(token):
    return token in NEGATION_WORDS or token.endswith("n't")


def _tokenize_words(sentence):
    return re.findall(r"[a-zA-Z']+", sentence.lower())


def best_match(sentence_embedding, reference_embeddings, reference_phrases):
    scores = util.cos_sim(sentence_embedding, reference_embeddings)[0]
    best_idx = int(scores.argmax())
    return float(scores[best_idx]), reference_phrases[best_idx]


def keyword_signal(sentence, category):
    """Check `sentence` for a direct keyword mention of `category`.

    Returns ("positive", keyword) if a non-negated keyword is found,
    ("negated", keyword) if the nearest keyword is negated, or (None, None)
    if the category's keywords don't appear at all - in which case the
    caller should fall back to the embedding check.
    """
    tokens = _tokenize_words(sentence)
    for i, token in enumerate(tokens):
        if token not in KEYWORDS[category]:
            continue
        window = tokens[max(0, i - NEGATION_WINDOW):i]
        if any(_is_negation_cue(t) for t in window):
            return "negated", token
        return "positive", token
    return None, None


def embedding_signal(sentence_embedding, baseline_score, category):
    """Margin-based embedding check for one category on one sentence -
    the same comparison label_conditions.py uses. Returns (is_match, score,
    matched_phrase, margin)."""
    condition_score, condition_phrase = best_match(
        sentence_embedding, conditions_embeddings[category], conditions[category]
    )
    margin = condition_score - baseline_score
    return margin >= MARGIN, condition_score, condition_phrase, margin


def label_sentence(sentence, sentence_embedding, baseline_score):
    """Evaluate one sentence against every category. For each category:
    - a non-negated keyword hit matches immediately (skips the embedding
      check - keyword evidence is direct, no need to also clear the margin)
    - a negated keyword hit vetoes a match for that category from this
      sentence, even if the embedding would otherwise have matched (bi-encoder
      cosine similarity is known to be weak at negation - "not muddy" can
      still score close to "the trail was muddy")
    - otherwise, fall back to the embedding margin check

    Returns ({category: bool}, [detail dicts]).
    """
    matched = {}
    details = []

    for category in conditions:
        sign, keyword = keyword_signal(sentence, category)

        if sign == "positive":
            matched[category] = True
            details.append({
                "category": category,
                "sentence": sentence,
                "method": "keyword",
                "matched_keyword": keyword,
            })
        elif sign == "negated":
            matched[category] = False
            details.append({
                "category": category,
                "sentence": sentence,
                "method": "negated_keyword",
                "matched_keyword": keyword,
            })
        else:
            is_match, score, phrase, margin = embedding_signal(sentence_embedding, baseline_score, category)
            matched[category] = is_match
            if is_match:
                details.append({
                    "category": category,
                    "sentence": sentence,
                    "method": "embedding",
                    "matched_phrase": phrase,
                    "score": score,
                    "margin": margin,
                })

    return matched, details


def apply_implied_rules(matched):
    """Mud and ice are common direct causes of slippery footing - treat a
    mud or ice match as implying slippery too, rather than relying on the
    embedding model to independently rediscover that correlation."""
    if matched["muddy"] or matched["icy"]:
        matched["slippery"] = True
    return matched


def label_comment(comment):
    """Return ({category: bool}, [match detail dicts]) for one review
    comment. A category is True if any sentence matches it via keyword or
    embedding signal (see label_sentence)."""
    matched = {condition: False for condition in conditions}
    details = []

    sentences = [s.strip() for s in sent_tokenize(comment or "") if s.strip()]
    if not sentences:
        return matched, details

    sentence_embeddings = model.encode(sentences, convert_to_tensor=True)

    for i, sentence in enumerate(sentences):
        baseline_score, _ = best_match(sentence_embeddings[i], baseline_embeddings, baseline_phrases)
        sentence_matched, sentence_details = label_sentence(sentence, sentence_embeddings[i], baseline_score)

        for category, is_match in sentence_matched.items():
            if is_match:
                matched[category] = True
        details.extend(d for d in sentence_details if d["method"] != "negated_keyword")

    return apply_implied_rules(matched), details


if __name__ == "__main__":
    test_sentences = [
        "Some parts are muddy from the melting ice and running water.",
        "The trail was not muddy at all, totally dry.",
        "Great trail, not many people, we took the detour to see the lookout.",
        "No snow on the trail yet this year.",
        "Watch out, there's ice near the summit.",
    ]
    for sentence in test_sentences:
        [embedding] = model.encode([sentence], convert_to_tensor=True)
        baseline_score, _ = best_match(embedding, baseline_embeddings, baseline_phrases)
        matched, details = label_sentence(sentence, embedding, baseline_score)
        hits = [c for c, v in matched.items() if v]
        print(f"\n{sentence}\n  matched: {hits or 'none'}")
        for d in details:
            print(f"  [{d['category']}] via {d['method']}: {d.get('matched_keyword') or d.get('matched_phrase')}")
