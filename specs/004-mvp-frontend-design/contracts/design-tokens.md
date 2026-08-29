# Contract: Design Tokens

Every component built or modified in this feature MUST consume these tokens rather than
hardcoding colors, radii, spacing, or font values. This is what makes spec.md's FR-014
(consistent rounding), FR-015 (limited color palette), FR-016 (single typography scale), FR-017
(spacious density), and FR-018 (consistent elevation) actually enforceable rather than aspirational.

Defined in `client/src/theme/tokens.css` as a Tailwind v4 `@theme` block plus two daisyUI theme
definitions (`cairns-light`, `cairns-dark`).

## Color

Two token groups: a neutral slate scale (backgrounds, borders, text) and exactly one accent hue
(amber/orange), each with light-theme and dark-theme values - not one palette with a blanket
invert.

| Token | Purpose | FR |
|---|---|---|
| `--color-base-100` / `-200` / `-300` | Page/card/panel background layers, lightest to slightly recessed | FR-015 |
| `--color-base-content` | Primary body text, must meet readable contrast against `base-100` in both themes | FR-015, FR-022 |
| `--color-neutral-content` | Secondary/meta text (e.g. difficulty/length captions) | FR-015 |
| `--color-border` | The thin borders used for elevation (contract below) | FR-018 |
| `--color-accent` | The single warm amber/orange hue - primary actions, active/selected states, map route line, nothing else | FR-015 |
| `--color-accent-content` | Text/icon color placed on top of an accent-filled surface (e.g. a filled button's label) | FR-015 |

**Rule**: if a color other than a neutral-scale value or `--color-accent` (and its `-content`
pairing) appears anywhere in a component's styling, that's a contract violation - flag it in review
rather than assuming it's intentional.

**Exception**: the trail overview's surface-mix bar (`TrailOverview.tsx`) is a categorical chart -
each `surfaceTypes` entry is a distinct category, not a state or action, so it uses a small
qualitative palette (`amber-500`/`emerald-500`/`sky-500`/`violet-500`/`rose-500`) instead of the
site accent, the same way a dashboard's chart legend would. This is deliberately scoped to that one
chart - don't extend it to buttons, links, or anything actionable, which stay accent-only.

## Corner radius (daisyUI v5 native variables)

| Token | Applies to | Target value |
|---|---|---|
| `--radius-field` | Buttons, text inputs, the theme toggle | ~12-16px, but buttons additionally use `rounded-full` (pill) per spec's "pill-shaped buttons where applicable" |
| `--radius-box` | Cards, the trail panel container, map popups | ~20-24px |
| `--radius-selector` | Chips/tags (feature list), toggle-style controls | Fully pill (`rounded-full`) - chips are short enough that box-radius would look identical to pill anyway |

**Exception, spelled out explicitly**: the trail panel's outer edge - the one flush against the
browser viewport edge - is NOT rounded, only its map-facing inner corners are. This is a
deliberate exception to "every element uses pronounced rounding" (FR-014), justified by how docked
side panels conventionally read (an edge-to-edge flush panel looks structurally wrong with a
rounded outer corner floating in the middle of the viewport edge). Document this exception at the
component level (`TrailPanel.tsx`) so it doesn't get "fixed" into a floating rounded corner later
by someone pattern-matching FR-014 too literally.

**Second exception**: the trail photo (`TrailOverview.tsx`) is square-cornered and bleeds full-width
to the panel's edges, not `rounded-box`-clipped and inset like other cards. This matches AllTrails'
own trail-photo treatment and is intentional - don't "fix" it into a rounded, inset image either.

## Typography

| Token | Value |
|---|---|
| `--font-sans` | Inter (variable, via `@fontsource-variable/inter`) |
| Heading scale | Trail name / section headings: one weight+size step, e.g. `font-semibold text-lg` |
| Body scale | Field labels/values: default weight, e.g. `text-base` |
| Meta scale | Secondary text (units, captions): muted color (`--color-neutral-content`), smaller size, e.g. `text-sm` |

## Spacing (density)

No new token needed beyond Tailwind's default spacing scale - the "spacious/airy" requirement
(FR-017) is a *usage* convention, not a new token: prefer `p-6`/`gap-6`-class values for card and
panel-section padding rather than `p-2`/`p-3`-class tight spacing. Document this as a review
checklist item (components using conspicuously tight padding should be flagged), not as a separate
CSS variable.

## Elevation

| Treatment | Applies to |
|---|---|
| `border border-[--color-border]`, no shadow (or a barely-visible `shadow-sm` at most) | Trail panel, cards, popups - per FR-018's "thin border, minimal shadow" |

**Rule**: don't mix - a component either uses the border treatment or (rarely, if ever) a shadow,
never both stacked on the same element, to keep the elevation language consistent per FR-018.
