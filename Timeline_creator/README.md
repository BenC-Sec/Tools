# Timeline Creator

A Jupyter tool that helps DFIR analysts build and visualise investigation
timelines. Enter events (manually or in bulk), filter them, and render a
report-ready timeline whose labels **never overlap and are never dropped** — the
figure grows and stacks instead.

Originally based on IBM's
[timeline-generator](https://github.com/IBM/timeline-generator); reworked into a
clean, layered, unit-tested package.

## Highlights

- **Pixel-aware deconfliction.** Near-simultaneous events (a common DFIR case)
  are stacked vertically using interval-graph colouring on the projected pixel
  geometry, so labels don't collide. Stacking is zoom-aware — a **Re-layout for
  current view** button recomputes it for whatever window you're looking at.
- **Keep every label.** Density is solved by growing/stacking the figure (capped,
  with split-window suggestions when a burst is too dense), never by dropping or
  merging labels.
- **Timesketch-aligned storage.** Each investigation is `<name>.jsonl`
  (one event per line) + `<name>.meta.json`. Spans serialise as two linked
  point records and reconstitute on load. Field names follow Timesketch
  (`datetime`, `message`, `timestamp_desc`).
- **One validation gate.** Every input path (manual form, CSV paste, xlsx upload,
  file load) is validated through a single pydantic `Event` model. Timestamps are
  timezone-aware UTC.
- **SVG-first export** (crisp in reports), with PNG as a fallback.

## Architecture

The core is pure Python (no matplotlib/ipywidgets/pandas) and unit-tested in
isolation. Only the render and UI layers pull in the heavy stack.

| Module        | Responsibility                                                    |
|---------------|-------------------------------------------------------------------|
| `models.py`   | pydantic `Event` / `Investigation` / `AccountType` — the gate     |
| `io.py`       | JSONL + meta sidecar; span decompose/reconstitute                 |
| `importers.py`| CSV / xlsx bulk import, all-or-nothing row-aggregated validation  |
| `filters.py`  | endpoint / user / time-window filtering (defaults: all selected)  |
| `colour.py`   | account-type → hue family, username → shade/marker (symbolic)     |
| `layout.py`   | **pixel-aware label deconfliction** (pure, the centrepiece)       |
| `render.py`   | matplotlib: draw the layout, legend, SVG/PNG export, ipympl view  |
| `app.py`      | thin ipywidgets three-panel controller                            |

## Usage

```bash
pip install -r requirements.txt
jupyter lab        # open Timeline_create.ipynb and run the two code cells
```

Then work through the three panels:

1. **Setup** — name/open an investigation; list endpoints and users.
2. **Events** — add events (host/user/type stay sticky) or bulk-import; the
   table is the single source of truth (edit/delete there).
3. **Display** — filter, render, zoom, **Re-layout for current view**, export SVG/PNG.

Timestamps are entered and stored in UTC.

## Tests

The pure core is covered by `pytest`:

```bash
pip install pytest
python -m pytest timeline_creator/tests/ -v
```

The layout suite asserts the headline guarantee — *no two label boxes overlap* —
across the hard cases (identical timestamps, mixed label heights, dense bursts).
