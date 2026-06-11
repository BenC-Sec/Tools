# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pixel-aware label deconfliction — the core of the rework (D4, D5, D6).

The old code stacked labels with a fixed index sawtooth (``2 + (i*2) % 20``),
which collides by design past ten labels and ignores actual time proximity.
This module replaces it with a genuinely correct algorithm:

  * Project each event's timestamp to an x-pixel for a SPECIFIC axis scale.
  * Estimate each label's pixel bounding box (wrap, font metrics, padding).
  * Treat the labels as intervals on the x-axis and solve INTERVAL-GRAPH
    COLOURING: the "colour" is the vertical level, so two labels whose pixel
    boxes overlap horizontally are placed on different levels (stacked
    vertically). This is exactly why near-simultaneous events — which share an
    x-pixel and so cannot be separated horizontally — get stacked.

KEEP EVERY LABEL is sacrosanct: nothing is ever dropped. When stacking would
exceed the height cap, the figure is reported as over-cap with suggested split
windows (D6) rather than rendered unusable.

The module is PURE: no matplotlib. Text width is estimated with a conservative,
over-biased per-glyph estimator by default; an accurate matplotlib-backed
``measurer`` can be injected at export time so the vector SVG is collision-free
against true font metrics. (Over-estimation costs whitespace; under-estimation
costs a real overlap — so the estimator always rounds up.)
"""

from __future__ import annotations

import itertools
import textwrap
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta


# --- text geometry ----------------------------------------------------------

def _build_default_char_widths() -> dict[str, float]:
    """Relative glyph advance widths (× font size). Hand-tuned, conservative."""
    widths: dict[str, float] = {}
    for ch in "iljI.,;:'!|` ":
        widths[ch] = 0.30
    for ch in "ftr()[]{}-":
        widths[ch] = 0.40
    for ch in "0123456789":
        widths[ch] = 0.58
    for ch in "abcdeghknopqsuvxyz":
        widths[ch] = 0.55
    for ch in "ABCDEFGHKNOPQRSUVXYZ":
        widths[ch] = 0.72
    for ch in "mwMW@%":
        widths[ch] = 0.95
    return widths


DEFAULT_CHAR_WIDTHS: dict[str, float] = _build_default_char_widths()


@dataclass(frozen=True)
class FontSpec:
    size_px: float = 8.0
    line_height_px: float = 11.0  # ~1.35 × size
    char_width_table: Mapping[str, float] | None = None
    avg_char_width_ratio: float = 0.6  # fallback for glyphs not in the table


def default_font(size_px: float = 8.0) -> FontSpec:
    return FontSpec(
        size_px=size_px,
        line_height_px=round(size_px * 1.35, 3),
        char_width_table=DEFAULT_CHAR_WIDTHS,
    )


@dataclass(frozen=True)
class LayoutParams:
    wrap_chars: int = 50
    box_h_pad_px: float = 4.0       # horizontal padding each side of text
    box_v_pad_px: float = 2.0       # vertical padding each side of text
    inter_box_vgap_px: float = 3.0  # min vertical gap between stacked levels
    width_fudge: float = 1.10       # >= 1.0 over-estimate bias (estimator only)
    max_fig_height_px: float = 30 * 96.0   # growth cap (~30in at 96dpi); render overrides
    baseline_offset_px: float = 12.0       # gap between the axis and the first level
    marker_gap_px: float = 6.0             # gap from anchor x to the box edge


Measurer = Callable[[str, FontSpec], float]


def estimate_text_width(text: str, font: FontSpec, width_fudge: float = 1.0) -> float:
    """Pure, over-biased single-line width estimate in pixels."""
    table = font.char_width_table
    if table is not None:
        ratio_sum = sum(table.get(ch, font.avg_char_width_ratio) for ch in text)
    else:
        ratio_sum = len(text) * font.avg_char_width_ratio
    return ratio_sum * font.size_px * width_fudge


# --- axis projection --------------------------------------------------------

@dataclass(frozen=True)
class AxisProjection:
    """Linear datetime <-> x-pixel mapping for one axis scale/window.

    matplotlib's date->pixel mapping is linear, so this is exact (not an
    approximation), and being self-inverting lets the layout suggest split
    windows in datetime terms without importing matplotlib.
    """

    x_min_dt: datetime
    x_max_dt: datetime
    pixel_width: float

    @property
    def _span_seconds(self) -> float:
        return (self.x_max_dt - self.x_min_dt).total_seconds()

    @property
    def is_degenerate(self) -> bool:
        return self._span_seconds <= 0

    def to_px(self, dt: datetime) -> float:
        span = self._span_seconds
        if span <= 0:
            return self.pixel_width / 2.0
        frac = (dt - self.x_min_dt).total_seconds() / span
        return frac * self.pixel_width

    def to_dt(self, px: float) -> datetime:
        span = self._span_seconds
        frac = (px / self.pixel_width) if self.pixel_width else 0.0
        return self.x_min_dt + timedelta(seconds=frac * span)


# --- layout inputs / outputs ------------------------------------------------

@dataclass(frozen=True)
class LayoutEvent:
    id: str
    anchor_dt: datetime
    label: str
    end_dt: datetime | None = None
    placement: str = "right"  # "right" | "left"

    @property
    def is_span(self) -> bool:
        return self.end_dt is not None


@dataclass(frozen=True)
class PlacedLabel:
    id: str
    anchor_x_px: float
    box_left_px: float
    box_right_px: float
    level: int
    box_bottom_px: float
    box_top_px: float
    n_lines: int
    wrapped_text: str


@dataclass(frozen=True)
class PlacedBar:
    id: str
    start_x_px: float
    end_x_px: float
    lane: int


@dataclass(frozen=True)
class SplitSuggestion:
    window_start_dt: datetime
    window_end_dt: datetime
    peak_levels: int


@dataclass(frozen=True)
class LayoutResult:
    placed: list[PlacedLabel]
    bars: list[PlacedBar]
    n_levels: int
    n_bar_lanes: int
    required_height_px: float
    exceeds_cap: bool
    split_suggestions: list[SplitSuggestion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --- internal box representation --------------------------------------------

@dataclass
class _Box:
    id: str
    anchor_x: float
    left: float
    right: float
    width: float
    height: float
    n_lines: int
    wrapped_text: str
    anchor_iso: str
    level: int = -1


def _wrap_to_fit(label: str, font: FontSpec, params: LayoutParams,
                 pixel_width: float) -> tuple[list[str], int]:
    """Wrap a label, capping the wrap width so a line cannot exceed the canvas.

    Returns (lines, effective_wrap_chars). A single very long token is broken
    rather than allowed to overflow invisibly (RISK 3 — KEEP EVERY LABEL).
    """
    usable = max(1.0, pixel_width - 2 * params.box_h_pad_px - params.marker_gap_px)
    per_char = max(1e-6, font.avg_char_width_ratio * font.size_px * params.width_fudge)
    max_chars_canvas = max(1, int(usable / per_char))
    effective_wrap = max(1, min(params.wrap_chars, max_chars_canvas))
    lines = textwrap.wrap(label, effective_wrap, break_long_words=True,
                          break_on_hyphens=True) or [""]
    return lines, effective_wrap


def _build_box(event: LayoutEvent, projection: AxisProjection, font: FontSpec,
               params: LayoutParams, measurer: Measurer | None) -> tuple[_Box, list[str]]:
    warnings: list[str] = []
    lines, _ = _wrap_to_fit(event.label, font, params, projection.pixel_width)

    if measurer is not None:
        line_width = max(measurer(line, font) for line in lines)
    else:
        line_width = max(estimate_text_width(line, font, params.width_fudge) for line in lines)

    box_w = line_width + 2 * params.box_h_pad_px
    box_h = len(lines) * font.line_height_px + 2 * params.box_v_pad_px

    if box_w > projection.pixel_width:
        warnings.append(
            f"label '{event.id}' is wider than the view even when wrapped; "
            "widen the window or reduce wrap width."
        )

    anchor_x = projection.to_px(event.anchor_dt)
    if event.placement == "left" and not event.is_span:
        right = anchor_x - params.marker_gap_px
        left = right - box_w
    else:  # right-placed point, or span label hanging off the start
        left = anchor_x + params.marker_gap_px
        right = left + box_w

    box = _Box(
        id=event.id, anchor_x=anchor_x, left=left, right=right, width=box_w,
        height=box_h, n_lines=len(lines), wrapped_text="\n".join(lines),
        anchor_iso=event.anchor_dt.isoformat(),
    )
    return box, warnings


def _colour_levels(boxes: list[_Box], h_pad: float) -> int:
    """Assign each box a level (interval-graph colouring). Mutates box.level.

    Boxes must be sorted by left edge. Each level stores its running rightmost
    occupied edge; a box takes the lowest level whose edge clears its left.
    """
    level_right_edge: list[float] = []
    for box in boxes:
        assigned = None
        for level in range(len(level_right_edge)):
            if box.left >= level_right_edge[level]:
                assigned = level
                break
        if assigned is None:
            assigned = len(level_right_edge)
            level_right_edge.append(0.0)
        level_right_edge[assigned] = box.right + h_pad
        box.level = assigned
    return len(level_right_edge)


def _stack_vertically(boxes: list[_Box], n_levels: int, params: LayoutParams) -> float:
    """Place each box's y-extent. Per-level height = tallest box on that level.

    Returns the total required figure height in pixels. Levels are stacked
    cumulatively so a tall box never bleeds into the next level (RISK 1).
    """
    level_height = [0.0] * n_levels
    for box in boxes:
        level_height[box.level] = max(level_height[box.level], box.height)

    level_bottom = [0.0] * n_levels
    running = params.baseline_offset_px
    for level in range(n_levels):
        level_bottom[level] = running
        running += level_height[level] + params.inter_box_vgap_px

    for box in boxes:
        box.bottom = level_bottom[box.level]      # type: ignore[attr-defined]
        box.top = box.bottom + box.height          # type: ignore[attr-defined]

    if n_levels == 0:
        return params.baseline_offset_px
    return level_bottom[-1] + level_height[-1] + params.inter_box_vgap_px


def _lane_pack_bars(events: Sequence[LayoutEvent], projection: AxisProjection,
                    gap_px: float = 4.0) -> tuple[list[PlacedBar], int]:
    """Pack span bars into non-overlapping horizontal lanes (RISK 2).

    Bars are colour-keyed separately from labels: only LABEL boxes drive the
    vertical level stack; the bars get their own simple lane packing so
    overlapping spans don't draw on top of each other.
    """
    spans = sorted(
        (e for e in events if e.is_span),
        key=lambda e: (projection.to_px(e.anchor_dt), e.id),
    )
    lane_right_edge: list[float] = []
    bars: list[PlacedBar] = []
    for event in spans:
        start_x = projection.to_px(event.anchor_dt)
        end_x = max(start_x, projection.to_px(event.end_dt))  # type: ignore[arg-type]
        assigned = None
        for lane in range(len(lane_right_edge)):
            if start_x >= lane_right_edge[lane]:
                assigned = lane
                break
        if assigned is None:
            assigned = len(lane_right_edge)
            lane_right_edge.append(0.0)
        lane_right_edge[assigned] = end_x + gap_px
        bars.append(PlacedBar(event.id, start_x, end_x, assigned))
    return bars, len(lane_right_edge)


def _suggest_splits(boxes: list[_Box], projection: AxisProjection,
                    params: LayoutParams, max_levels_fit: int) -> list[SplitSuggestion]:
    """Greedily cut the timeline into windows that each fit under the cap.

    Works entirely on clones so it never disturbs the real boxes' levels.
    """
    suggestions: list[SplitSuggestion] = []
    window: list[_Box] = []

    def close_window() -> None:
        if not window:
            return
        local_levels = _colour_levels([_clone(b) for b in window], params.box_h_pad_px)
        left = min(b.left for b in window)
        right = max(b.right for b in window)
        suggestions.append(SplitSuggestion(
            window_start_dt=projection.to_dt(left),
            window_end_dt=projection.to_dt(right),
            peak_levels=local_levels,
        ))

    for box in (_clone(b) for b in boxes):  # already sorted by left
        trial = sorted(window + [box], key=lambda b: b.left)
        trial_levels = _colour_levels([_clone(b) for b in trial], params.box_h_pad_px)
        if window and trial_levels > max_levels_fit:
            close_window()
            window = [box]
        else:
            window.append(box)
    close_window()
    return suggestions


def _clone(box: _Box) -> _Box:
    return _Box(box.id, box.anchor_x, box.left, box.right, box.width, box.height,
                box.n_lines, box.wrapped_text, box.anchor_iso)


def compute_layout(events: Sequence[LayoutEvent], projection: AxisProjection,
                   font: FontSpec | None = None, params: LayoutParams | None = None,
                   measurer: Measurer | None = None) -> LayoutResult:
    """Compute a collision-free placement of every label for one axis scale."""
    font = font or default_font()
    params = params or LayoutParams()
    warnings: list[str] = []

    if projection.is_degenerate:
        warnings.append(
            "all events share one instant (zero-width window); "
            "labels are stacked vertically at the centre."
        )

    boxes: list[_Box] = []
    for event in events:
        box, box_warnings = _build_box(event, projection, font, params, measurer)
        boxes.append(box)
        warnings.extend(box_warnings)

    # Deterministic order: left edge, then anchor time, then id.
    boxes.sort(key=lambda b: (round(b.left, 6), b.anchor_iso, b.id))

    n_levels = _colour_levels(boxes, params.box_h_pad_px)
    required_height_px = _stack_vertically(boxes, n_levels, params)

    bars, n_bar_lanes = _lane_pack_bars(events, projection)

    exceeds_cap = required_height_px > params.max_fig_height_px
    split_suggestions: list[SplitSuggestion] = []
    if exceeds_cap and boxes:
        tallest = max(b.height for b in boxes)
        usable = max(1.0, params.max_fig_height_px - params.baseline_offset_px)
        max_levels_fit = max(1, int(usable / (tallest + params.inter_box_vgap_px)))
        split_suggestions = _suggest_splits(boxes, projection, params, max_levels_fit)
        warnings.append(
            f"{n_levels} stacked levels need {required_height_px:.0f}px, over the "
            f"{params.max_fig_height_px:.0f}px cap; suggest splitting into "
            f"{len(split_suggestions)} window(s)."
        )

    placed = [
        PlacedLabel(
            id=box.id, anchor_x_px=box.anchor_x, box_left_px=box.left,
            box_right_px=box.right, level=box.level,
            box_bottom_px=box.bottom, box_top_px=box.top,  # type: ignore[attr-defined]
            n_lines=box.n_lines, wrapped_text=box.wrapped_text,
        )
        for box in boxes
    ]
    placed.sort(key=lambda p: (p.level, round(p.box_left_px, 6), p.id))

    return LayoutResult(
        placed=placed, bars=bars, n_levels=n_levels, n_bar_lanes=n_bar_lanes,
        required_height_px=required_height_px, exceeds_cap=exceeds_cap,
        split_suggestions=split_suggestions, warnings=warnings,
    )


# --- adapter from the data model -------------------------------------------

def layout_events_from(events: Sequence, placement: str = "right") -> list[LayoutEvent]:
    """Build LayoutEvents from :class:`timeline_creator.models.Event` objects."""
    out: list[LayoutEvent] = []
    for index, event in enumerate(events):
        out.append(LayoutEvent(
            id=f"{index}",
            anchor_dt=event.datetime,
            label=event.message,
            end_dt=event.end,
            placement=placement,
        ))
    return out


def overlapping_x(a: PlacedLabel, b: PlacedLabel) -> bool:
    return not (a.box_right_px <= b.box_left_px or b.box_right_px <= a.box_left_px)


def overlapping_y(a: PlacedLabel, b: PlacedLabel) -> bool:
    return not (a.box_top_px <= b.box_bottom_px or b.box_top_px <= a.box_bottom_px)


def assert_no_overlaps(result: LayoutResult) -> None:
    """Raise AssertionError if any two placed boxes overlap. Test helper."""
    for a, b in itertools.combinations(result.placed, 2):
        if overlapping_x(a, b) and overlapping_y(a, b):
            raise AssertionError(
                f"labels '{a.id}' and '{b.id}' overlap "
                f"(levels {a.level}/{b.level})"
            )
