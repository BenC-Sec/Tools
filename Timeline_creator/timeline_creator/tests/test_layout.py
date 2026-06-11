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

"""Invariant tests for the deconfliction layout — the heart of the rework.

The headline guarantee is: NO TWO PLACED LABEL BOXES OVERLAP. These tests prove
it across the hard cases (identical timestamps, mixed label heights, dense
bursts) using pure geometry, with no matplotlib involved.
"""

from datetime import timedelta

from timeline_creator import layout
from timeline_creator.layout import (
    AxisProjection, LayoutEvent, LayoutParams, assert_no_overlaps,
    compute_layout, default_font, overlapping_x,
)
from .conftest import utc


def _projection(start=None, end=None, width=1000.0):
    return AxisProjection(start or utc(2025, 1, 1, 9, 0, 0),
                          end or utc(2025, 1, 1, 17, 0, 0), width)


def _ev(i, dt, label="event", end=None, placement="right"):
    return LayoutEvent(id=str(i), anchor_dt=dt, label=label, end_dt=end, placement=placement)


# --- the core invariant -----------------------------------------------------

def test_spread_out_events_no_overlap():
    events = [_ev(i, utc(2025, 1, 1, 9 + i)) for i in range(8)]
    result = compute_layout(events, _projection())
    assert_no_overlaps(result)


def test_ten_events_identical_timestamp_get_ten_levels():
    instant = utc(2025, 1, 1, 12, 0, 0)
    events = [_ev(i, instant, label=f"simultaneous event {i}") for i in range(10)]
    result = compute_layout(events, _projection())
    assert result.n_levels == 10
    assert {p.level for p in result.placed} == set(range(10))
    assert_no_overlaps(result)


def test_same_second_cluster_no_overlap():
    base = utc(2025, 1, 1, 12, 0, 0)
    events = [_ev(i, base + timedelta(milliseconds=i), label=f"burst {i}") for i in range(15)]
    result = compute_layout(events, _projection())
    assert_no_overlaps(result)


def test_mixed_line_heights_no_vertical_bleed():
    instant = utc(2025, 1, 1, 12, 0, 0)
    events = [
        _ev(0, instant, label="short"),
        _ev(1, instant, label="this is a much longer label that will wrap onto "
                              "several lines making a tall box " * 2),
        _ev(2, instant, label="medium length label here"),
    ]
    result = compute_layout(events, _projection())
    assert_no_overlaps(result)
    # the tall multi-line box must actually be taller than the short one
    heights = {p.id: p.box_top_px - p.box_bottom_px for p in result.placed}
    assert heights["1"] > heights["0"]


def test_levels_are_minimal_for_two_clusters():
    # two well-separated clusters of 3 -> at most 3 levels, not 6
    left = [_ev(i, utc(2025, 1, 1, 9, 0, 0), label=f"L{i}") for i in range(3)]
    right = [_ev(10 + i, utc(2025, 1, 1, 16, 0, 0), label=f"R{i}") for i in range(3)]
    result = compute_layout(left + right, _projection())
    assert result.n_levels == 3
    assert_no_overlaps(result)


# --- determinism ------------------------------------------------------------

def test_deterministic_snapshot():
    instant = utc(2025, 1, 1, 12, 0, 0)
    events = [_ev(i, instant, label=f"evt {i}") for i in range(6)]
    a = compute_layout(events, _projection())
    b = compute_layout(events, _projection())
    assert [(p.id, p.level, round(p.box_left_px, 3)) for p in a.placed] == \
           [(p.id, p.level, round(p.box_left_px, 3)) for p in b.placed]


# --- spans / bars -----------------------------------------------------------

def test_overlapping_spans_get_distinct_lanes():
    events = [
        _ev(0, utc(2025, 1, 1, 10), label="span A", end=utc(2025, 1, 1, 14)),
        _ev(1, utc(2025, 1, 1, 11), label="span B", end=utc(2025, 1, 1, 15)),
    ]
    result = compute_layout(events, _projection())
    assert result.n_bar_lanes == 2
    assert {b.lane for b in result.bars} == {0, 1}


def test_non_overlapping_spans_share_a_lane():
    events = [
        _ev(0, utc(2025, 1, 1, 10), label="span A", end=utc(2025, 1, 1, 11)),
        _ev(1, utc(2025, 1, 1, 12), label="span B", end=utc(2025, 1, 1, 13)),
    ]
    result = compute_layout(events, _projection())
    assert result.n_bar_lanes == 1


def test_span_label_and_point_labels_coexist():
    events = [
        _ev(0, utc(2025, 1, 1, 12), label="point one"),
        _ev(1, utc(2025, 1, 1, 12), label="span here", end=utc(2025, 1, 1, 14)),
        _ev(2, utc(2025, 1, 1, 12), label="point two"),
    ]
    result = compute_layout(events, _projection())
    assert len(result.placed) == 3   # every label placed
    assert len(result.bars) == 1
    assert_no_overlaps(result)


# --- cap + split ------------------------------------------------------------

def test_exceeds_cap_triggers_split_suggestions():
    instant = utc(2025, 1, 1, 12, 0, 0)
    events = [_ev(i, instant, label=f"dense burst event number {i}") for i in range(40)]
    params = LayoutParams(max_fig_height_px=200.0)  # deliberately tiny cap
    result = compute_layout(events, _projection(), params=params)
    assert result.exceeds_cap
    assert result.split_suggestions
    assert any("cap" in w for w in result.warnings)


def test_within_cap_no_split():
    events = [_ev(i, utc(2025, 1, 1, 9 + i)) for i in range(5)]
    result = compute_layout(events, _projection())
    assert not result.exceeds_cap
    assert result.split_suggestions == []


# --- edge cases -------------------------------------------------------------

def test_degenerate_window_warns_and_stacks():
    instant = utc(2025, 1, 1, 12, 0, 0)
    events = [_ev(i, instant, label=f"e{i}") for i in range(4)]
    result = compute_layout(events, _projection(start=instant, end=instant))
    assert any("zero-width" in w for w in result.warnings)
    assert result.n_levels == 4
    assert_no_overlaps(result)


def test_very_long_label_wraps_tall_not_dropped():
    # An absurdly long token wraps into a tall box rather than being clipped.
    result = compute_layout([_ev(0, utc(2025, 1, 1, 12), label="x" * 4000)],
                            _projection(width=300.0))
    assert len(result.placed) == 1
    placed = result.placed[0]
    assert placed.n_lines > 20  # forced to wrap onto many lines
    assert placed.box_right_px - placed.box_left_px <= 300.0  # never wider than canvas


def test_wide_glyph_label_exceeding_canvas_warns_not_clips():
    # Wide glyphs (W) exceed the char-count-based canvas cap, tripping the warning.
    result = compute_layout([_ev(0, utc(2025, 1, 1, 12), label="W" * 200)],
                            _projection(width=300.0))
    assert any("wider than the view" in w for w in result.warnings)
    assert len(result.placed) == 1  # still placed, not dropped


def test_left_and_right_placement():
    instant = utc(2025, 1, 1, 12, 0, 0)
    left = compute_layout([_ev(0, instant, label="L", placement="left")], _projection())
    right = compute_layout([_ev(0, instant, label="R", placement="right")], _projection())
    assert left.placed[0].box_right_px <= left.placed[0].anchor_x_px
    assert right.placed[0].box_left_px >= right.placed[0].anchor_x_px


def test_injected_measurer_is_used():
    instant = utc(2025, 1, 1, 12, 0, 0)
    events = [_ev(i, instant, label="abc") for i in range(2)]
    # a measurer claiming everything is 500px wide forces wide boxes
    wide = compute_layout(events, _projection(), measurer=lambda text, font: 500.0)
    # same anchor + wide boxes overlap in x, so they must stack onto two levels
    assert overlapping_x(wide.placed[0], wide.placed[1]) is True
    assert wide.n_levels == 2
    assert_no_overlaps(wide)
