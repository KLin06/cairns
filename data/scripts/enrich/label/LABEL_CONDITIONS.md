# Label Conditions — Design Notes

## Goal

Flag which sentences in a review's `comment` describe trail conditions (mud, ice,
snow, flooding, etc.), for reviews where `obstacles`/`trailConditions` tags are
missing or too sparse to use directly. See `../../../TRAIL_CONDITIONS_PLAN.md` for
the broader project context this feeds into.

## Approach

Sentence-level embeddings + cosine similarity, not single-word or whole-comment
matching:

1. Split each review's `comment` into sentences with `nltk.sent_tokenize`
   (not naive `.split(".")` — informal review text breaks that: abbreviations,
   decimals like "2.5 mi.", missing punctuation, etc.).
2. Embed each sentence with `all-MiniLM-L6-v2` (`sentence-transformers`) — local,
   offline, no API cost.
3. For each condition category (`muddy`, `slippery`, ...), embed a small set of
   reference phrases in different phrasing styles (formal, casual, short) rather
   than one anchor word/phrase, to catch wording variety.
4. Compare each sentence against each category's reference phrases with cosine
   similarity (`sentence_transformers.util.cos_sim`).

## Problem found while testing: absolute thresholds aren't reliable

Manual test against a sample comment (three sentences: one irrelevant, one about
ice, one about mud) showed:

- The true positive scored **0.6620** — `"Some parts are muddy from the melting
  ice and running water."` vs `"muddy conditions underfoot"`.
- An irrelevant sentence scored **0.5169** — `"Great trail, not many people..."`
  vs `"the trail was muddy"` — despite not mentioning mud at all.

A flat threshold (e.g. `0.6`) happens to separate these two specific examples,
but only by a ~0.07-0.15 margin, which won't generalize across more reviews.

**Why this happens:** general-purpose sentence embedding models aren't
well-calibrated in absolute terms. Two sentences that just share domain
vocabulary (e.g. "trail") tend to score moderately similar (0.2-0.5) even when
semantically unrelated, which compresses the useful range between "irrelevant"
and "relevant." This is a known limitation of bi-encoder cosine similarity, not
a bug in the setup.

## Implemented fix: margin-based comparison, not a fixed cutoff

Added a set of **baseline** reference phrases — things reviews commonly say
that have nothing to do with trail conditions — embedded the same way as
condition phrases. A sentence only counts as a match if its best
condition-category score **beats its best baseline score by `MARGIN`** (0.1),
not just clears an absolute number. See `label_conditions.py`.

This directly targets the false positive above: `"Great trail..."` scores high
against `"the trail was muddy"` (0.5169) but scores *even higher* against a
baseline phrase like `"took a nice detour to the lookout"` (0.7107), so it
doesn't win the comparison.

**Baseline is split into two groups, not just "neutral":**
- **Neutral** — positive/unremarkable review chatter (`"nice views along the
  trail"`, `"great hike overall"`).
- **Negative-but-unrelated** — genuine complaints that aren't about mud/ice/
  slippery conditions (`"the bugs were unbearable"`, `"trail was way too
  crowded"`, `"parking lot was a mess"`).

The negative group matters because condition phrases (`"the trail was muddy"`)
are themselves negative in tone. A sentence like "the bugs were unbearable" is
negative but off-topic — comparing it only against *positive* neutral phrases
wouldn't give it a fair baseline, since it shares tone with condition phrases
without sharing content. Comparing against negative-but-unrelated phrases too
closes that gap.

Verified on the test comment: "Some parts are muddy..." picked a *negative*
baseline phrase (`"trail was way too crowded"`) as its closest baseline match,
not a neutral one — and the margin still held (+0.4459), confirming the split
baseline doesn't accidentally make matching harder for genuine condition
sentences.

## Future upgrade path: cross-encoder reranking

If margin-based bi-encoder comparison isn't precise enough once tested on more
reviews: add a cross-encoder (e.g. `cross-encoder/stsb-roberta-base`) as a
second stage. Bi-encoders (current approach) embed each sentence independently
then compare vectors — fast, but less accurate for fine-grained similarity.
Cross-encoders score a sentence *pair* jointly through the model — significantly
more accurate, but slower (no precomputed/reusable embeddings; every pair needs
its own forward pass).

Standard pattern: use the current bi-encoder to cheaply narrow down candidate
sentences, then re-score only those candidates with a cross-encoder for the
final yes/no decision. Only worth the added complexity if margin-based
bi-encoder comparison demonstrably isn't precise enough.

## Dashboard progress

Evaluated against `datasets/manual_labels/10268327.json` (145 manually
labeled reviews), via `precision_recall_f1` per category (TP/(TP+FP) etc.):

| script | model | dashboard output |
|---|---|---|
| `condition_f1_dashboard.py` | `all-MiniLM-L6-v2` (baseline, `label_conditions.py`) | `datasets/dashboards/condition_f1_dashboard.png` |
| `condition_f1_dashboard_mpnet.py` | `all-mpnet-base-v2` (`label_conditions_mpnet.py`) | `datasets/dashboards/condition_f1_dashboard_mpnet.png` |

Filenames now carry the model name so it's clear at a glance which dashboard
is which without opening the script.

### Experiment: all-mpnet-base-v2 (stronger model) vs all-MiniLM-L6-v2 (baseline)

Tried swapping in `all-mpnet-base-v2` (768-dim, higher STS benchmark scores,
slower) for `all-MiniLM-L6-v2` (384-dim, current baseline) with the margin-based
approach otherwise unchanged (same `MARGIN=0.1`, same reference/baseline
phrases). New model + dashboard live in `label_conditions_mpnet.py` /
`condition_f1_dashboard_mpnet.py`, kept separate from the baseline rather than
overwriting it.

**Result: mpnet performed worse on every category, F1-wise:**

| category | MiniLM F1 | mpnet F1 | delta |
|---|---|---|---|
| muddy | 0.81 | 0.73 | -0.08 |
| slippery | 0.83 | 0.84 | +0.01 |
| icy | 0.73 | 0.66 | -0.07 |
| snowy | 0.69 | 0.55 | -0.14 |
| flooded | 0.36 | 0.30 | -0.06 |

Recall was flat-to-slightly-better with mpnet, but precision dropped hard
(e.g. `snowy` P=0.62→0.41, `muddy` P=0.81→0.66) — more false positives, not
more false negatives. `flooded` stayed the weakest category on both models
(too few positive examples in the label set — 11 total — for the score to be
reliable either way).

**Why mpnet did worse here:** a stronger general-purpose STS model doesn't
mean a better score *distribution* for this specific margin-based setup — the
`MARGIN=0.1` cutoff was implicitly tuned against MiniLM's score spread.
mpnet's embedding space compresses/spreads scores differently, so the same
margin lets more borderline off-topic sentences through as false positives.
This isn't necessarily a dead end — the margin (and reference/baseline
phrases) would need to be re-tuned specifically for mpnet's score
distribution before it's a fair comparison — but out of the box, **baseline
MiniLM is the better model for this task and remains the one used in
production (`label_conditions.py`, unchanged).**

### Margin retuning for mpnet

Since the mpnet result above used MiniLM's `MARGIN=0.1` unchanged, retuned it
properly: `tune_margin_mpnet.py` embeds each labeled review's sentences once,
then sweeps candidate margins from -0.10 to +0.30 (step 0.02) against the
same 145-review label set, re-applying the muddy/icy→slippery implication
rule at each threshold, and reports macro-F1 (mean F1 across the 5
categories) per candidate.

**Result: `MARGIN=0.12` is the best single global value for mpnet**
(macro-F1 0.641, vs 0.617 at the untuned 0.1). Updated `label_conditions_mpnet.py`
to use it. Per-category F1 at 0.12: muddy 0.75, slippery 0.83, icy 0.70,
snowy 0.57, flooded 0.35.

**Still doesn't beat MiniLM even after tuning.** MiniLM's macro-F1 (from the
baseline dashboard) is ≈0.684 — noticeably above mpnet's best of 0.641. The
sweep curve is also informative: F1 rises steadily from -0.10 up to a broad
plateau around 0.12-0.20, then falls off sharply past ~0.22, so the margin
concept clearly works for mpnet (it's not noise) — the model's ceiling for
this task is just lower than MiniLM's with this reference-phrase-based
approach, not a tuning problem.

**Conclusion: MiniLM (`MARGIN=0.1`, baseline) remains the model used in
production.** mpnet was kept as a documented, retuned comparison point; since
it didn't beat the baseline, `label_conditions_mpnet.py` / `condition_f1_dashboard_mpnet.py`
/ `tune_margin_mpnet.py` were later deleted (the tables/conclusions above are
kept as the record of the experiment; `condition_f1_dashboard_mpnet.png` is
still in `datasets/dashboards/` if you want the visual).

### Negation-aware keyword check — beats the baseline

Idea: bi-encoder cosine similarity is known to be weak at negation ("not
muddy" can still score close to "the trail was muddy"), and can also just
plain miss blunt direct mentions that don't phrase like any reference phrase.
Added a keyword layer on top of the baseline's margin-based embedding check,
in a new file (`label_conditions_keyword.py`) rather than editing
`label_conditions.py` directly, plus split the previous single `label_comment`
function into smaller pieces per concern:

- `keyword_signal(sentence, category)` — regex-tokenizes the sentence and
  checks for a direct keyword (`mud`/`muddy`, `ice`/`icy`, `snow`/`snowy`,
  `flood`/`flooded`/`underwater`, `slippery`/`slick`). Looks for a negation
  cue (`not`, `no`, `never`, `without`, `hardly`, or any `*n't`) in the
  `NEGATION_WINDOW` (4) tokens before the keyword. Returns `"positive"`,
  `"negated"`, or `None` (no keyword present at all).
- `embedding_signal(...)` — the baseline's margin-based check, unchanged,
  used only as a fallback.
- `label_sentence(...)` — combines the two per category: a non-negated
  keyword hit matches immediately (skips the embedding check entirely); a
  negated keyword hit **vetoes** a match for that category from that
  sentence, even overriding what the embedding check would have said, since
  the keyword is direct textual evidence and the embedding is known to be
  negation-blind; otherwise falls back to the embedding margin check.
- `apply_implied_rules(...)` — the existing muddy/icy→slippery implication,
  pulled out unchanged.
- `label_comment(...)` — orchestrates the above per sentence and aggregates
  across the comment, same public interface as the baseline.

Manually verified negation handling (`python label_conditions_keyword.py`):
`"The trail was not muddy at all, totally dry."` no longer matches `muddy`,
and `"No snow on the trail yet this year."` no longer matches `snowy` — both
via `negated_keyword` veto rather than falling through to a false positive
embedding match.

**Result: beats the MiniLM baseline on every category**, not just the mpnet
comparison:

| category | baseline F1 | keyword+negation F1 | delta |
|---|---|---|---|
| muddy | 0.81 | 0.91 | +0.10 |
| slippery | 0.83 | 0.91 | +0.08 |
| icy | 0.73 | 0.79 | +0.06 |
| snowy | 0.69 | 0.81 | +0.12 |
| flooded | 0.36 | 0.41 | +0.05 |

`muddy` and `snowy` hit recall 1.00 (FN=0) — the keyword net catches every
direct mention the embedding was missing on its own. Precision held or
improved too (it's not just trading FN for FP): keyword hits are a strong,
narrow signal, so they add true positives without adding much noise.
`flooded` is still the weakest category by a wide margin (P=0.30) — same
root cause as before, only 11 positive examples in the label set, independent
of which detection method is used.

**Caveat: the negation heuristic is simple** (fixed 4-token window, a fixed
cue list) — it will miss scope-crossing negation ("not even a little
muddy"), negation via clause structure without a cue word ("far from
muddy"), and double negatives. It only needs to catch the *common* cases to
be a net win, which the dashboard confirms it does, but it isn't a full
negation parser.

**This is now the strongest variant tested and a reasonable candidate to
promote to production**, pending a decision on whether to fold it into
`label_conditions.py` directly or keep it as the separate file it's grown
into (`label_conditions_keyword.py`, dashboard at
`datasets/dashboards/condition_f1_dashboard_keyword.png`).

## Open questions / next steps

- [x] Implement margin-based scoring (neutral reference phrases + margin
      requirement) in place of the current raw-threshold approach
- [x] Test against a larger, more varied sample of real reviews (145 manually
      labeled reviews, see Dashboard progress above)
- [x] Try a stronger embedding model (`all-mpnet-base-v2`) — see experiment
      above; worse out of the box, not adopted
- [ ] Decide the final storage format/location for labeled output — see
      `../../../TRAIL_CONDITIONS_PLAN.md` for the `conditionMentions` field proposal
- [ ] `flooded` category is weak on both models (P=0.21-0.27) — likely needs
      more positive examples in `manual_labels` before either model can be
      fairly judged on it
- [x] If revisiting mpnet: re-tune `MARGIN` (and/or reference phrases)
      specifically for its score distribution rather than reusing MiniLM's
      — done (`MARGIN=0.12`, see "Margin retuning for mpnet" above); still
      doesn't beat MiniLM, so not adopted
- [ ] Revisit cross-encoder reranking only if margin-based scoring
      underperforms on real data
- [x] Try negation handling + a direct-keyword check, split into smaller
      functions — done (`label_conditions_keyword.py`); beats the baseline
      on every category, see "Negation-aware keyword check" above
- [ ] Decide whether to promote `label_conditions_keyword.py` to production
      (replace/merge into `label_conditions.py`) or keep it separate
- [ ] Broaden the negation heuristic if FN/FP examples on more data show it
      missing common patterns (scope-crossing negation, cue-less negation)
