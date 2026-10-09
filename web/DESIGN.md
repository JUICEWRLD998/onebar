# OneBar web UI: design plan

Written 2026-10-09, before any code. Pipeline: `ui-studio` (ground, explore, structure, build, motion, verify, review).

## Subject, audience, jobs

**Subject.** A hiker with one bar of signal texts a question and gets one 160-character reply. The code computes
every fact, a small tuned model words the reply, and a checker refuses any reply with an invented number.

**Audience.** First, a judge with 20 seconds who must see that this is real and checkable. Then a hiker, then a
reader who wants the numbers behind the claim.

**The one job of the first screen.** Show a question becoming a checked reply, and let the reader see where every
number in it came from.

## Vocabulary sheet (from the subject's own world, not from "tech")

| World | Things we take |
|---|---|
| Topographic maps | contour lines (every fifth one heavier), spot heights, neatline border with coordinate ticks, leader-line callouts to a legend, map-print colours: grey-white paper, brown contours, glacier blue, trail red |
| Trail waymarks and signs | painted blazes, fingerpost plates with a time and a direction, enamel lettering from Highway Gothic (which Overpass descends from) |
| Handsets that work on one bar | a 160 counter, signal bars, a status strip. Not a drawn phone: no bezel, no notch |
| Field notes | time column, observation column, tick marks |
| Mountain bulletins | a hazard scale where colour means a job, and the source is cited on the same line |

## Hierarchy contract (first viewport, 1280 wide)

| Question | Answer on screen |
|---|---|
| Where am I? | Wordmark, "Ask" current in the nav, the place chip in the handset header |
| What matters most? | The latest reply in the handset, and beside it the audit of that reply (map, hourly strip, numbers traced) |
| What can I do? | Type a question, tap an example, switch between Tuned and Base model |
| What just happened? | One status line under the thread: "Checked. 4 of 4 numbers traced to the forecast. 158 of 160 characters." |
| What next? | Example questions, "Results" and "How it works" in the nav |

The blind critic must name: a product that answers hiking weather questions in 160 characters with every number
checked; the primary action, asking a question; the most important thing, the reply and its proof.

## Memorable detail (the one boldness)

**The leader lines.** On a map, a callout is a thin line from a label to the thing it names. Here every number in
the reply gets one: from the number, through the fact it came from, down to the forecast hour it was read at. The
reply is something you can follow back to the data with your eye. Everything else on the page stays quiet.

## Signature moment: the reply gets audited

```
Trigger:   a reply arrives in the handset
t=0        the reply text is on screen; its numbers carry a dashed muted underline (not yet checked)
t=120ms    the length meter fills from 0 to N of 160
t=240ms    first number: underline turns solid teal, its leader line draws (pathLength 0 to 1, 260ms) from the
           number to its fact chip to its hour column; that column lifts 4px and gains a teal cap
+180ms     each further number does the same (at most four animate; the rest snap)
t~900ms    the checks list ticks, row by row, 60ms apart
t~1000ms   the verdict line appears as text: "Checked. 4 of 4 numbers traced to the forecast. 158 of 160 characters."
The eye follows: number in the reply, fact chip, hour column, verdict.
End state: the verdict is on screen as text and announced through aria-live="polite".
Reduced motion: everything verified at once with a 150ms crossfade; same verdict text.
Never blocks input: sending another message jumps this to its end state.
Thumbnail frame: t~650ms, two leader lines drawn and the third mid-stroke.
Overshoot: none. Controls and this moment settle without bounce.
```

## Review against the generated-design defaults

| Default | Where this plan could have fallen into it | What was changed |
|---|---|---|
| Cream, high-contrast serif, terracotta | "Field notebook" reads that way | Paper is a cool grey-white tinted toward the accent hue, not cream. No serif anywhere. No terracotta: the warm hue is map-contour ochre and is used for terrain only |
| Near-black with one acid accent | The dark theme is exactly this, and it is also the SIGNAL DECK taste | Dark surfaces are a visibly blue ink (chroma about 0.02), not a neutral #111. The accent is teal, not acid green. Three support hues each have a job. Collision stated below |
| Broadsheet hairlines, zero radius | Map sheets invite it | Hairlines only where a map would have a neatline. Radius varies by role |
| Identical rounded cards with the same shadow | A two-column dashboard drifts there | No card kit. The audit is one continuous "sheet" with a map margin; blocks differ in structure, not just content |
| Eyebrow labels, middle-dot metadata, mono small labels, arrow suffixes | Easy to add to every section | None. Mono is used only where the text is literally a code identifier (`storm_first`) |
| Gradient wash, glow, glass | Hero art | None. One quiet contour field, graded to the tokens |

**Collision with the SIGNAL DECK taste (one line, his call).** The dark theme keeps the deep blue-black and the
mint-teal accent; the light "map paper" theme leads because a hiker reads this in daylight. The first-visit theme
follows the system setting; flipping the default is one token.

## Colour plan (OKLCH, measured by `scripts/palette-check.mjs`)

Roles: `ground`, `surface`, `surface-sunk`, `line`, `ink`, `ink-muted`, ONE accent (the signal, hue about 168),
and three support hues, each with a job:

| Hue | Job |
|---|---|
| Accent teal, hue 168 | "checked", the one filled action, the lit signal bar |
| Glacier blue, hue 245 | data and sources: fact chips, the forecast strip |
| Contour ochre, hue 68 | terrain only: map lines, spot heights |
| Trail red, hue 28 | rejected: an invented number, a failed check, an error |

Surfaces carry chroma 0.006 to 0.03 toward the palette. Both themes are designed, not inverted.

## Type

One family, two cuts. **Overpass** (variable): a Highway Gothic descendant, so the lettering has the authority of
a trail sign and plays well at small sizes. **Overpass Mono** only for code identifiers. Scale 13, 15, 17, 21, 28,
40 on a 1.25 ratio, line length under 68ch, `text-wrap: balance` on headings, `tabular-nums` on every number that
updates. Sentence case everywhere.

## Layout

Ask (1280): handset column 24rem on the left, audit sheet fills the rest; leader lines cross the gutter.
Below 1024: stacked; the audit sits under the reply, and number-to-fact links become linked highlights.
Results: one primary chart (first-try pass rate by system) with the full table beneath.
How it works: the pipeline as one drawn diagram, then what the product is not.
Trace: `/trace/:id`, the audit sheet alone, opened from the footer line of an email reply.

## Image plan

| Route | Image | Rung | Source |
|---|---|---|---|
| Ask | Contour map of the place, with pin and spot height | R2 from real data | Open-Meteo elevation grid, contours computed in the browser (marching squares); a pre-built sample for first paint |
| Results | The same contour field as a quiet header texture | R2 | build-time sample |
| How it works | The pipeline diagram and the contour field | R2 | hand-built SVG |
| Trace | The map of that trace's place | R2 | as Ask |

Images are graded to tokens (`currentColor` and CSS variables). Alt text says what the map is for the reader.

## Principles

1. The product's proof is the interface: show the source of every number, never claim it.
2. One boldness: the leader lines. Everything else is quiet and ruled like a map margin.
3. Words are for the person on the trail: sentence case, plain verbs, errors say what broke and what to do.

## Phase 2: three directions, rendered and looked at (2026-10-09)

Screenshots at 1280 and 375 are in `data/ui-shots/explore/`. All three use the same real data: the "ridge ok by
3:30pm then car?" row from the test set, its real hourly forecast, and real contours from the Open-Meteo elevation
grid around Punta Salarioli.

| Direction | Axis | What worked | What did not |
|---|---|---|---|
| A. Survey sheet | Two columns, handset beside an audit sheet; light "map paper" | Answers the whole hierarchy contract in one viewport. The contour map is the best image of the three | Three leader lines drawn at once cut across the chips and the Send button |
| B. Trail sign | One column; the reply set huge on a dark enamel plate, numbers as fingerpost tabs | The most striking single moment. Reading order is unmistakable | Loses the message thread; the map and composer fall below the first viewport; a one-off layout for a product that is asked repeatedly |
| C. Night log | Dark; a chronological field log where an entry expands into its audit | Dense, good for repeat use; the dark map is lovely | A first visit looks like a spreadsheet; the proof is under a table |

**Pick: A.** It is the only one that puts the reply, its proof, the place and the next action in one viewport,
which is what the hierarchy contract asks for.

**Change made to A after looking at it.** Orthogonal or curved leaders from several numbers on one text line cannot
be drawn without crossings. The fix is in how the idea works, not in routing: the number in the reply and the number
in the table are the same string, which already is the key. A leader is drawn for **one number at a time**: the
one being hovered, focused, or (during the signature moment) the one being verified. One line can never cross
another. Below 1024 px there are no lines; the active row highlights instead.

**Borrowed.** From B: the reply is set larger than the thread around it, because it is the thing being judged.
From C: the dark theme's treatment of the contours (ochre on blue ink), which is the strongest image in the set.

**Runner-up.** B, as a candidate for a future share card (OG image) cut from the same data.

## Phase 3: structure (Hallmark, custom-theme route, 2026-10-09)

**Pre-flight.** No existing UI in this repo (`web/` is new). Preserved from elsewhere in the project: the house stack
(CSS Modules, one tokens file, `motion` from `motion/react`, no Tailwind) and the SIGNAL DECK dark palette idea.
Introduced: macrostructure, micro-interaction discipline, slop-test gates. Framework: Vite + React 19 + TypeScript,
not Next.js: the plan (`implementation.md` section 1) specifies Vite, and the product deploys as a static build behind
Caddy next to the FastAPI service with no Node server to run on the droplet. Motion stance: motion-on.

**Design context (answers to Hallmark's three questions, taken from the plan).**
Audience: a judge in the first 20 seconds, then hikers and curious readers. Use case: ask one question and see the
reply's proof. Tone: utilitarian, close to signage; not editorial, not playful.

**Picks.**
- Macrostructure: **19 Map / Diagram.** The audit sheet is one spatial composition (terrain map, hour strip, source
  rows), and the handset beside it is the orientation. Stamped in `tokens.css` as `--macrostructure`.
- Nav: a flat top bar, text links with an underline on the current route, theme switch and a live-status word at
  the right. No hamburger above 768 px; below it the same four items wrap.
- Footer: one-line colophon saying what the product is not, with links to Results, How it works and the source.
- Theme route: **custom, tuned** (OKLCH palette in `tokens.css`, measured by `palette-check`). Not a catalog theme.
- Heading placement: left-aligned above content. Dividers: one hairline where a map would have a neatline.
  Button voice: filled accent for the single primary action, outlined for the rest. Reveal: none on load; the one
  moving thing is the signature moment.
- Locked tokens: every colour, size and duration is a `var(--...)`; a grep for raw colours in `src/` runs in phase 6.

**Preview (what gets built).**

```
ASK 1280                                              ASK 375
+--------------------------------------------------+  +----------------------+
| OneBar  Ask Results How it works     live   theme |  | OneBar   live  theme |
+----------------------+---------------------------+  | Ask Results How      |
| |||. 1 bar   [Place] | [Tuned | Base]            |  +----------------------+
| ------------------   | +-----------------------+ |  | |||. 1 bar [Place]   |
|        you: question | |  contour map, pin,    | |  |       you: question  |
| +------------------+ | |  spot height          | |  | +------------------+ |
| | Reply with 3     | | +-----------------------+ |  | | Reply, 3 numbers | |
| | numbers marked   | | hour strip 13 14 ... 00   |  | +------------------+ |
| +------------------+ | where each number came    |  | Checked. 3 of 3 ...  |
| Checked. 3 of 3 ...  | from: rows, one lit       |  | [ask...........][Send]|
| [examples]           | checks: length, chars,... |  | ------------------   |
| [ask..........][Send]|                           |  | map                  |
+----------------------+---------------------------+  | hour strip           |
  one leader line, for the number in focus only        | number rows          |
                                                       +----------------------+
RESULTS: heading, one bar chart (first-try pass by system), the full table, what the checker does not measure.
HOW IT WORKS: one drawn pipeline, the trip timer, the five checks in plain words, what it is not.
TRACE /trace/:id: the audit sheet alone with the question and reply above it.
```

**Pre-emit self-critique (Hallmark axes, 1 to 5).** Philosophy 4 (proof as the interface), Hierarchy 4, Execution
pending, Specificity 5 (real terrain, real forecast hours, real test rows), Restraint 4, Variety 4. Execution is
scored after the build, in phase 6.

## Phase 4 to 7: build record (2026-10-09)

**Built as planned.** Macrostructure 19 Map / Diagram; direction A with one leader line at a time; the signature
audit sequence; real contour terrain; a Tuned/Base toggle; light and dark. Routes: Ask, Results, How it works, Trace.

**Changed after looking at the rendered page.**

| Found in the browser | Fix |
|---|---|
| The leader line ran through the second text line of the reply (a button's box is as tall as its line, so the drop landed on the next line) | Anchor to the text's vertical centre: start 0.55em under it, run 0.9em under it; reply line-height 1.75 so the gap exists |
| A comma after a number wrapped onto its own line (buttons are atomic inline boxes) | Trailing punctuation is drawn inside the same no-wrap span as its number |
| Number rows stopped short of the sheet (`li` inherits the 66ch reading measure) | `max-width: none` on rows |
| The map at 320 px was 90 px tall, with the caption laid over it and the place name clipped | Caption below the map; on a phone the crop is the whole grid (3:2) and the name sits under the pin |
| ui-score auto-fail tells: side stripe on rows and cards, a bordered toggle and picker inside bordered sheets, three equal columns on How it works, check glyphs read as emoji, a width transition on the bars | Wash instead of stripe, borderless sunk segmented control and picker, a legend list and flex flow, SVG ticks, `scaleX` bars |
| axe: the place button's accessible name did not contain its visible text | Visible words are the name; "place" is added with visually-hidden text |

**Measured (see DECISIONS.md Phase 7 for the caveats).** Palette gate holds in all three theme blocks. axe: 0 violations
across 12 runs (planted control caught). ui-score on Ask: light 86, dark 77, no auto-fail tell. 117 web tests. No raw colour
outside `tokens.css`. Screenshots at 320, 375, 414, 768, 1024, 1280, 1440 and 1920 were looked at for the Ask journey; the
other routes were looked at at 1280 and 375 in both schemes.

**Not done.** `better-writing` and `better-interface` passes per route, the blind critic, and a screen-reader run.
Route-level code splitting. A real-device check on a phone.
