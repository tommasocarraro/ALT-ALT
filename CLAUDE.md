# ALT-ALT: Bike Bearing Press Planner

This file is the context for anyone (human or Claude) picking up this repository. Read it before changing
anything in the rules, the rule engine or the drawings: most of what matters here is domain knowledge that is
not obvious from the code.

## What this is for

A friend of the repository owner (Tommaso) sells **ALT/ALT**, a modular bearing press for mountain bikes
(https://www.altalt.ca/). The tool is a kit of many small pieces; which pieces a customer needs depends on the
bearings in their bike and on how those bearings are arranged. Working that out is expert manual work today.

The app automates it:

1. Take the exploded diagram of a frame or component (a PDF from the bike manufacturer).
2. Find the cartridge bearings in it: codes and dimensions.
3. A person describes each **arrangement** (which bearings sit on one axis, and how) in a questionnaire.
4. A rule engine works out, for every removal and install job, which ALT/ALT pieces are needed and in which sizes.
5. The pieces go into a **cart** (part numbers and prices) so the friend can issue an invoice.
6. The app also produces step-by-step instructions and a section drawing for every job.

Decisions already taken, do not reopen them without being asked:

- **Arrangements are entered by hand, not guessed by a model.** Guessing them from the diagram was tried and
  removed (unstable between runs). The model only reads bearing codes.
- **The rule engine, instructions and drawings are plain code.** No model calls, deterministic, free to run.
- **No real-time stock.** Availability on the website is not integrated; the cart only needs pieces and prices.
- **A person can always override.** Sizes the rules cannot know are left open, and every cart line is editable.

## Domain vocabulary

Bearing dimensions are inner diameter (ID) x outer diameter (OD) x width, in mm. A standard code fixes them:
6902 is 15x28x7 whoever makes it; seals and shields (2RS, 2Z, LLU, MAX) do not change the size; 61804 is the
ISO long form of 6804. Markings like E/EA/EB (extended inner ring) or F/FO (flange) do change the geometry.

The tool works on four ideas the website calls **PLCC**: something PRESSes the bearing, something on the other
side gives LEVERAGE, something CENTERs the tool, and there must be CLEARANCE for whatever moves.

### Pieces

| Piece | What it does | Sized by |
|---|---|---|
| Stud | M8 threaded rod everything sits on; 120, 180 or 240 mm | length chosen by a person with the part in hand |
| Standard Nut / Handle / Stud Stop | fasteners on the Stud's ends. The Handle is a bar across the Stud that is turned. The Stud Stop is a knurled wheel that acts as a stop: never turned, needs a piece larger than 20 mm to sit against, not suitable on the Spacer Tube end | one size |
| O-ring | keeps a pilot from sliding on the Stud | one size |
| Drift RE | presses a bearing, or acts as leverage. One face is flat, the other has a 3 mm relief | OD: 16, 19, 21, 22, 24, 26, 28, 30, 32, 35, 37, 41 |
| Pilot Short / Pilot Long | sits in the bearing bore (or in an axle's end) and centres the tool. The long one also keeps the inner spacer aligned while the second bearing goes in | bearing ID: 10, 11, 12, 15, 17, 18, 20, 25 (23 short aluminium only) |
| Sleeve + Step | leverage with room inside: the bearing is pushed out into the sleeve; the Step is a stepped cap that centres any sleeve | sleeve by bearing OD: 16, 19, 22, 24, 26, 28, 30, 32, 35, 37 |
| Sleeve 6 / Sleeve Long | hub versions of the sleeve: Sleeve 6 rests on a 6-bolt disc mount, Sleeve Long on a centre-lock mount | one size |
| Stop CTR | cone that centres itself in an empty seat and gives leverage on install | one size |
| Stop OAL | leverage on the drive side of a hub, clears a long axle end; also fits XD/XDR freehubs | one size |
| Spacer Tube | extender, reaches through a part to the drift | one size |
| ALT Drift + ALT Rod | removes the first bearing of a pair from behind. The rod goes in from the far side, through the other bearing and the spacer; turned with an Allen key | bearing ID: 15, 17, 18, 20, 25 |
| ALT Extractor | removes a bearing from the front: a collet expands inside it (bolt in its head, Allen key), then Sleeve + Step go on its own stud and a Stud Stop acts as the nut | bearing ID: 10, 12, 15, 17, 18, 20, 25 |
| Over Axle Drift | hollow press piece for installing a bearing over a protruding axle; always pushed by a Drift RE, never by a nut. Sold as one long and one short per size (the long one for the driver side) | axle OD x bearing OD, 14 sizes |

Sizing rules confirmed by the owner:

- Removal drift: the **smallest Drift RE larger than the bearing ID** (it pushes the inner ring).
- Install drift: the Drift RE matching the bearing OD. Which face presses follows the manufacturer: flat side by
  default; relief side when the bearing must be slightly loaded (drift presses only the outer ring while the
  axle holds the inner ring).
- Bearing ID 8 or 9: no pilot, the Stud centres the tool. Pilots 10 to 12 are for centring only.
- Material: acetal for carbon parts, aluminium for alloy. Some pieces exist in one material only (Stop CTR,
  Stop OAL, Sleeve 6 and Over Axle Drifts are acetal; ALT Drift, ALT Rod and ALT Extractor are aluminium).
- Over Axle Drift: sized from the bearing (axle OD = bearing ID) unless the axle is stepped.
- Pilots inside an axle, and the Stud length, cannot be known without the part: left open for a person.

### Arrangements

The website names ten; the app expresses them as a base type plus questionnaire answers.

| Website arrangement | In the app |
|---|---|
| Simple Pivot | type SP, one bearing in the seat |
| Double Stacked Pivot | type SP, two bearings in the seat |
| BSB Pivot (thin spacer ring) | type BSB, frame, spacer shorter than 10 mm |
| BSB Frame | type BSB, frame, spacer at least 10 mm |
| BSB Hub | type BSB, hub, with spacer |
| BSB Hub Variant (No Spacer) | type BSB, hub, no spacer |
| Over Axle (hub, or frame main pivot) | type OA, long axle (sticks out of the bearings) |
| Over Axle Short | type OA, short axle (enters the bearings half-way) |
| BSB Freehub | type BSB, freehub, one bearing from each side |
| BSB Freehub Variant (One Side) | type BSB, freehub, both bearings from the outboard side |

BSB means Bearing / Spacer / Bearing. What tells the types apart is the part the bearings are pressed into:
two bearings on the same bolt but in two separate arms or plates are two simple pivots, not one arrangement.

Key decisions the rules encode:

- **First bearing of a pair cannot be reached from behind.** ALT Drift only if the spacer moves at least 1 mm
  off-axis, is at least 10 mm long, and the bearing ID is 15/17/18/20/25. Otherwise ALT Extractor.
- **A double-stacked seat:** the outer bearing always comes out with the ALT Extractor; the rest follows the
  simple pivot rules.
- **Fewest pieces: reuse the ALT Extractor.** It is the expensive piece. Once any arrangement of the project
  needs one (stacked seat, or a first bearing the ALT Drift cannot do), every other bearing of the same ID in
  the project comes out with it too (Extractor + Step + Sleeve), instead of Drift RE + Spacer Tube or ALT Drift.
  Not applied to the first bearing of an over-axle (the axle is in its bore) nor to the inboard bearing of a
  one-side freehub (assumed out of reach; see the open questions in `build_rules.py`).
- **Hub leverage:** Sleeve 6 for 6-bolt, Sleeve Long for centre-lock, Stop OAL on the drive side. On a frame
  the same job uses Step + Sleeve.
- **Freehub leverage:** Step + Sleeve for HG/Microspline, Stop OAL for XD/XDR.

## Repository layout

```
main.py                         FastAPI app: database models, all endpoints
app/backend/utils.py            PDF download and highlighting
app/backend/llm/                the only code that calls a model
    client.py                   Claude client: model, effort, the two call shapes, token usage counter
    prompts.py                  prompts for reading the diagram, resolving part numbers, finding dimensions
    schemas.py                  Pydantic output formats
    standard_bearings.py        table of standard sizes; sizes spelled in a code (MR 15267, 17x30x7)
    logic.py                    the pipeline: extract -> resolve part references -> dimensions
app/backend/rules/
    engine.py                   rule engine: rule set, jobs, options, sizes, catalogue lookup, cart, instructions
    drawing.py                  SVG section drawing of one job
app/frontend/                   Create React App (TypeScript, Tailwind); nearly everything is in src/App.tsx
data/rules/
    build_rules.py              SOURCE OF TRUTH for the rules. Edit this, then run it.
    rules.json, RULES.md        generated from build_rules.py. Never edit by hand.
    SAMPLE_INSTRUCTIONS.txt     generated by scripts/sample_instructions.py
data/altalt_site/               scraped from altalt.ca on 2026-10-07
    catalog.json                products, variants, SKUs, prices in CAD
    instructions/               31 official instructional diagrams (PDF, extracted text, and png/ for the app)
    arrangements/               the ten arrangement pictures
    pages/                      text of the site's pages (Pieces, System Explained, How-To, ...)
    scraper/                    the Playwright scripts that produced the above
    alt-extractor.png, handle.png, stud-stop.png    reference photos supplied by the owner
data/easy, data/hard            six labelled example diagrams (diagram.png, label.json, sometimes table.png)
scripts/eval_extraction.py      checks diagram reading against the labelled examples (PAID: calls the model)
scripts/sample_instructions.py  writes sample instructions for every arrangement type (free)
additional-files/               an older prototype, untracked (has its own .git and a large .venv)
```

## Running

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt     # once
.venv/bin/uvicorn main:app --port 8000                                 # backend, from the repo root
cd app/frontend && npm install && npm start                            # frontend on :3000, proxies to :8000
```

- `.env` at the repo root must contain `ANTHROPIC_API_KEY`. It is git-ignored. Never print or commit it.
- The database is SQLite at `app/backend/data/db`, created on first start, git-ignored. Tables are created
  with `create_all`: a **new table** appears by itself, but a **changed table** needs the file deleted (there is
  no migration tool).
- The backend reads `data/rules/rules.json`, `data/altalt_site/catalog.json` and the diagram images with paths
  relative to the repo root, so start it from there.

Regenerating generated files:

```
.venv/bin/python data/rules/build_rules.py          # rules.json + RULES.md
.venv/bin/python -m scripts.sample_instructions     # SAMPLE_INSTRUCTIONS.txt
```

## How the pieces fit together

### Reading a diagram (`app/backend/llm/`)

`POST /create_project` with a title and a PDF URL runs `from_url_to_bearings`:

1. **Extract** (one model call): the PDF is sent as a document, so the model sees text and drawings. It
   returns bearing codes (or a size such as `17x30x7` used as the code when the diagram gives only a size),
   bearings that have only a part number, and the manufacturer and model.
2. **Resolve part references** (only if there are any): a web-research call, then a second call that puts the
   findings into the fixed format. "Not found" is an allowed answer.
3. **Dimensions**, from the most reliable source: the database (so a stored value wins and each code is looked
   up once) -> the standard table -> the size spelled in the code -> a web lookup for what is left.

Every bearing is stored with where its code came from (diagram or web, with URL) and where its dimensions came
from. The model is `claude-opus-5-5`, effort high; changing model is one constant in `client.py`.

**Cost:** this is the only part that spends API credit (about $0.44 for the six evaluation examples when
arrangements were still being guessed). Ask before running `scripts/eval_extraction.py` or creating projects
in bulk. On the last measured run all six examples had the right bearing codes.

### Rules (`data/rules/build_rules.py`)

Each of the ten rule sets is a list of **operations** (remove 1st bearing, install 2nd bearing, ...). An
operation has:

- `press`, `center`, `leverage`: each a list of **options**; an option has `pieces`, a human `when` and a
  machine `cond` (`six_bolt`, `center_lock`, `hg`, `xd`, `frame`, `default`, `manual`). `manual` options need
  judgement (clearance, manufacturer's instructions): they are offered as alternatives and never picked.
- `extras`, `hardware`, `notes`.
- `stack`: the order of everything along the Stud from the pressing end to the leverage end, as drawn in the
  official diagrams. Instructions and drawings are both generated from it.
- `action`: the sentence that says what to do once assembled.
- `status`: `diagram` (transcribed from an official diagram), `confirmed` (not drawn on the site, confirmed by
  the tool's owner), `inferred` (assumed; there are none at present, keep it that way or say so clearly).

All 31 official diagrams were read as text and as images. Corrections since then came from the owner; when he
corrects a rule, change `build_rules.py`, regenerate, and keep the status honest.

### Rule engine (`app/backend/rules/engine.py`)

`tools_for_project(specs)` collects the ALT Extractor sizes that any arrangement cannot do without
(`extractors_needed`) and passes them to `tools_for` for each arrangement, which does, in order:

1. `rule_set_for`: questionnaire answers -> one of the ten rule sets, plus a list of assumptions when an
   answer was left blank.
2. `_plan`: the jobs, in order. Removal starts with the first seat of the sequence (disc side on a hub; the
   outboard bearing on a one-side freehub). A double-stacked seat inside a BSB or OA adds an extractor job for
   the outer bearing and a simple-pivot install for it. `_reuse_extractors` then turns every removal that an
   extractor already in the project can do into an extractor job (operation id `reuse:<original id>`).
3. `_job`: for each job, pick the option whose condition holds, size each piece (`_size`), look it up in the
   catalogue, and build the `stack`. Unresolved pieces carry the reason. The two ends of the Stud become a
   Handle (turned) and a Stud Stop (holds), replacing plain nuts.
4. `_scenes`: the state of the part when each job starts (which seats are filled, whether the spacer or axle
   is in). The spacer leaves the picture as soon as one side is open; the axle leaves with the first bearing.

`cart_for` merges all jobs: pieces are reused between jobs, so a quantity is the **most any single job needs**
(a job using two identical drifts needs two), not the sum. `apply_cart_edits` lays the user's saved changes on
top. `instructions_for` renders plain text.

### Drawings (`app/backend/rules/drawing.py`)

One SVG per job, a section cut through the middle. Conventions the owner asked for:

- The **whole part** is shown as it is when the job starts, with all remaining bearings, spacer and axle.
- **The part never turns between drawings:** side A (disc side) on the left, side B on the right, the open end
  of a single seat on the right. The tool changes sides instead, and the pink arrow shows which way the bearing
  travels. (The job is laid out with the bearing travelling right, then the picture is mirrored when needed:
  `_mirrored`. Text must stay out of the mirrored group.)
- **Colour by material:** acetal black, aluminium gold, steel grey; the bike part light blue.
- Each piece carries the **letter** it has in the written steps (a, b, c in stack order). Pieces go above,
  bearings/spacer/axle/pilots below. Leaders end in a dot on the thing itself. Amber badge = size still open.
- The Stud is hatched like a thread. Bearings show a ball between two rings. O-rings are thin black bands.
- **Axle:** a stepped hollow cylinder; shoulders touch the inner rings; journals go through the bearings and
  stick out on both sides (long axle) or stop half-way through them (short axle). Pilots listed next to the
  axle are drawn inside its ends.
- **Handle:** a bar across the Stud with a hex hub. **Stud Stop:** boss towards the tool, knurled wheel outside.
- **Step:** five shoulders. **Drift RE:** relief drawn on one face (flat face on the bearing when pressing).
- **ALT Extractor:** wedge behind the bearing, collet inside it, grooved body, its own threaded stud. The Allen
  key is at the head; when other bearings are behind the head, it is drawn the long way round, through the part.
- **ALT Drift:** the rod passes through the far bearing and the spacer, which is drawn pushed off its axis.
- Diameters are to scale. **Lengths are indicative** (the catalogue has no lengths); the owner said the current
  ones look right, with sleeves, drifts and especially Over Axle Drifts on the long side.

### API (`main.py`)

| Endpoint | Purpose |
|---|---|
| `POST /create_project` | read a diagram and store its bearings (calls the model) |
| `GET /projects`, `GET /projects/{id}` | list; one project with bearings, their sources and its arrangements |
| `POST /arrangements`, `PUT /arrangements/{id}` | save the questionnaire. `slots` is a list of bearing codes per seat: one list for SP, two for BSB and OA; two codes in one seat means double-stacked |
| `GET /projects/{id}/tools` | jobs with pieces, stack, drawing (`svg`) and official diagram URL; and the cart |
| `GET /projects/{id}/instructions` | the same jobs as plain text |
| `GET /catalog` | every individual piece, for the cart's pickers |
| `PUT /projects/{id}/cart`, `DELETE /projects/{id}/cart?key=` | change, add or reset one cart line |

Cart edits are stored per project in `cart_edits`, keyed by the computed line (`<sku>`, `open:<name>|<reason>`
for an unresolved piece, `added:<sku>` for a piece added by hand). Quantity 0 removes a line. An edit whose
line the rules no longer produce is ignored.

### Frontend (`app/frontend/src/App.tsx`)

Project page: the PDF on the left (zoom, drag to pan), on the right "Bearings found" with sources and the
arrangement questionnaire (type, spacer or axle details, component frame/hub/freehub, the bearing sequence
editor, material). Below, "Tools and instructions": the editable cart, then one card per job with the drawing,
the lettered steps, the action, alternatives, notes and the official diagram folded away.

## Working conventions

- **Never edit `rules.json`, `RULES.md` or `SAMPLE_INSTRUCTIONS.txt` by hand.** Change `build_rules.py` (or
  the engine) and regenerate.
- **Rules come from the owner, not from guesses.** If a rule is unclear, ask; if something has to be assumed,
  give it status `inferred` and list it under the open questions in `build_rules.py`.
- **After changing the engine or the drawing,** check that every sample job still works:
  ```
  .venv/bin/python -c "import scripts.sample_instructions as si; from app.backend.rules.engine import tools_for; \
  from app.backend.rules.drawing import svg_for; [svg_for(j) for s in si.SAMPLES for j in tools_for(s)['jobs']]; print('ok')"
  ```
  and look at a few drawings (render the SVGs in a browser): drawing bugs are visual and do not raise errors.
- **Do not kill processes by port.** The owner often has the backend on 8000 and the frontend on 3000. To test,
  start your own on other ports and stop only your own process IDs.
- **Model calls cost the owner money.** Say what a run will cost and get a go-ahead first.
- **Commits:** the work is on the `press-planner` branch, in small commits, not pushed. `main` is untouched.
- There are no automated tests. Verification so far has been by scripts and by looking at the page.

## Open points

- The pilot on a hub's first-bearing install: the official diagram shows a Pilot Long, without a reason.
- O-ring quantities were counted from the official drawings.
- Bearings without known dimensions are stored as "dimensions not found"; there is no screen to enter them yet.
- Creating a project through the app's "New Project" button has not been run end to end against the real
  model; only the evaluation script has.
- The cart is a list with prices; nothing sends it to the shop or produces an invoice yet.
- `additional-files/` (old Pillow/Tkinter prototype and hand-made 2D piece images) is not committed and was
  superseded by the generated drawings.
