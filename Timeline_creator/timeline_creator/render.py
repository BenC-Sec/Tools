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

"""Matplotlib rendering — consumes a :class:`LayoutResult` and draws it (D8).

This is the only place matplotlib is used. It translates the pure layout's
pixel geometry into a figure:

  * point events  -> a marker at the timeline baseline + a stacked label
  * spans         -> a lane-packed bar below the baseline + a label off the start
  * colour/marker -> concrete styles mapped from the symbolic colour tokens
  * legend        -> grouped by account-type family

The DPI<->pixel bridge lives here: the axes pixel width drives the layout
projection, and the layout's required pixel height drives the figure height, so
1 y-unit == 1 pixel and the layout's non-overlap guarantee survives into the
rendered output. Export re-runs the layout with a matplotlib-backed text
measurer so the vector SVG is collision-free against true font metrics.

Primary export is SVG (vector, crisp in reports); PNG is a convenience
fallback. An interactive ipympl view supports zoom/pan with a "re-layout for
current view" button (button-press, not reactive).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from . import colour as colour_mod
from . import filters
from .colour import SHADES_PER_FAMILY, ColourToken
from .layout import (AxisProjection, LayoutParams, LayoutResult, compute_layout,
                     default_font, layout_events_from)
from .models import AccountType, Event

# Concrete colour ramps per family (light -> dark), SHADES_PER_FAMILY entries each.
FAMILY_RAMPS: dict[str, list[str]] = {
    "reds":    ["#fcae91", "#fb6a4a", "#de2d26", "#a50f15"],
    "blues":   ["#9ecae1", "#4292c6", "#2171b5", "#084594"],
    "greys":   ["#bdbdbd", "#969696", "#636363", "#252525"],
    "oranges": ["#fdbe85", "#fd8d3c", "#e6550d", "#a63603"],
    "greens":  ["#a1d99b", "#41ab5d", "#238b45", "#005a32"],
    "purples": ["#bcbddc", "#807dba", "#6a51a3", "#4a1486"],
    "neutral": ["#bdbdbd", "#737373", "#525252", "#252525"],
}


def colour_for(token: ColourToken) -> str:
    """Concrete matplotlib colour string for a symbolic token."""
    ramp = FAMILY_RAMPS.get(token.family, FAMILY_RAMPS["neutral"])
    return ramp[token.shade_index % SHADES_PER_FAMILY]


@dataclass
class RenderStyle:
    font_size: float = 8.0
    dpi: int = 150
    fig_width_in: float = 14.0
    left_frac: float = 0.13      # axes left margin (room for the legend)
    right_frac: float = 0.02
    bottom_frac: float = 0.10    # room for date ticks + span lanes
    top_frac: float = 0.04
    bar_area_px: float = 26.0    # vertical pixels reserved below baseline for bars
    lane_height_px: float = 7.0


def _axes_pixel_width(style: RenderStyle) -> float:
    frac = 1.0 - style.left_frac - style.right_frac
    return frac * style.fig_width_in * style.dpi


def _make_measurer(style: RenderStyle):
    """A matplotlib-backed text measurer (px width of one line at the font).

    Uses a scratch Agg figure at the target dpi; width depends only on dpi and
    font, not on the final figure size, so this is safe to build up front.
    """
    scratch = plt.figure(dpi=style.dpi)
    canvas = scratch.canvas
    renderer = canvas.get_renderer()

    def measurer(text: str, font) -> float:
        artist = scratch.text(0, 0, text or " ", fontsize=style.font_size)
        width = artist.get_window_extent(renderer=renderer).width
        artist.remove()
        return width

    measurer._scratch = scratch  # keep a reference alive
    return measurer


@dataclass
class RenderedTimeline:
    figure: matplotlib.figure.Figure
    axes: matplotlib.axes.Axes
    layout: LayoutResult
    window: tuple[datetime, datetime]


class TimelineRenderer:
    """Render filtered events into a matplotlib figure using the pure layout."""

    def __init__(self, style: RenderStyle | None = None,
                 layout_params: LayoutParams | None = None,
                 display_tz: tzinfo = timezone.utc):
        self.style = style or RenderStyle()
        self.layout_params = layout_params or LayoutParams()
        self.display_tz = display_tz
        self.font = default_font(self.style.font_size)

    # -- projection helpers --------------------------------------------------

    def _window(self, events: list[Event],
                window: tuple[datetime, datetime] | None) -> tuple[datetime, datetime]:
        if window is not None:
            return window
        starts = [e.datetime for e in events]
        ends = [e.end for e in events if e.end is not None]
        lo = min(starts)
        hi = max(ends + starts)
        if lo == hi:  # single instant -> pad so the axis isn't zero-width
            from datetime import timedelta
            lo, hi = lo - timedelta(minutes=1), hi + timedelta(minutes=1)
        else:  # 4% breathing room each side
            pad = (hi - lo) * 0.04
            lo, hi = lo - pad, hi + pad
        return lo, hi

    def _layout(self, events: list[Event], window: tuple[datetime, datetime],
                measurer) -> tuple[LayoutResult, AxisProjection]:
        projection = AxisProjection(window[0], window[1], _axes_pixel_width(self.style))
        layout_events = layout_events_from(events)
        result = compute_layout(layout_events, projection, self.font,
                                self.layout_params, measurer=measurer)
        return result, projection

    # -- drawing -------------------------------------------------------------

    def render(self, events: list[Event],
               window: tuple[datetime, datetime] | None = None,
               *, accurate: bool = True,
               into_figure: "matplotlib.figure.Figure | None" = None) -> RenderedTimeline:
        """Build a figure for the given events.

        ``accurate=True`` measures text with matplotlib (collision-free against
        true metrics); ``False`` uses the pure estimator (faster, looser).
        ``into_figure`` redraws into an existing figure (used by the interactive
        "re-layout for current view" button so the ipympl canvas is reused).
        """
        if not events:
            raise ValueError("no events to render")

        win = self._window(events, window)
        # Lay out only what's visible in the window (spans clipped to the edge),
        # so a zoomed "re-layout for current view" doesn't draw off-canvas labels.
        events = filters.by_time_window(events, win[0], win[1])
        if not events:
            raise ValueError("no events fall within the requested window")
        measurer = _make_measurer(self.style) if accurate else None
        result, projection = self._layout(events, win, measurer)

        style = self.style
        bar_area = style.bar_area_px if result.bars else 0.0
        axes_height_px = result.required_height_px + bar_area
        height_frac = 1.0 - style.bottom_frac - style.top_frac
        fig_height_in = max(2.5, axes_height_px / (height_frac * style.dpi))

        if into_figure is not None:
            fig = into_figure
            fig.clear()
            fig.set_size_inches(style.fig_width_in, fig_height_in)
        else:
            fig = plt.figure(figsize=(style.fig_width_in, fig_height_in), dpi=style.dpi)
        ax = fig.add_axes([style.left_frac, style.bottom_frac,
                           1 - style.left_frac - style.right_frac, height_frac])

        x_lo = mdates.date2num(win[0])
        x_hi = mdates.date2num(win[1])
        ax.set_xlim(x_lo, x_hi)
        ax.set_ylim(-bar_area, result.required_height_px)

        def px_to_x(px: float) -> float:
            return x_lo + (px / projection.pixel_width) * (x_hi - x_lo)

        assignment = colour_mod.assign(events)
        event_by_id = {str(i): e for i, e in enumerate(events)}

        def token_for(event: Event) -> ColourToken:
            return assignment[(event.account_type, event.username)]

        # span bars (lane-packed below the baseline)
        for bar in result.bars:
            event = event_by_id[bar.id]
            y = -(bar.lane + 1) * style.lane_height_px
            ax.hlines(y, px_to_x(bar.start_x_px), px_to_x(bar.end_x_px),
                      color=colour_for(token_for(event)), linewidth=4,
                      capstyle="round", alpha=0.9)

        # point markers at the baseline
        for placed in result.placed:
            event = event_by_id[placed.id]
            token = token_for(event)
            if not event.is_span:
                ax.plot(mdates.date2num(event.datetime), 0, token.marker_token,
                        color=colour_for(token), markersize=4, zorder=5)

        # leader lines + stacked labels
        for placed in result.placed:
            event = event_by_id[placed.id]
            colour = colour_for(token_for(event))
            anchor_x = mdates.date2num(event.datetime)
            ax.plot([anchor_x, anchor_x], [0, placed.box_bottom_px],
                    color=colour, linewidth=0.4, alpha=0.6, zorder=1)
            ax.text(px_to_x(placed.box_left_px), placed.box_bottom_px,
                    placed.wrapped_text, fontsize=style.font_size,
                    ha="left", va="bottom", color="black", zorder=6,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                              edgecolor=colour, linewidth=0.6, alpha=0.85))

        self._style_axes(ax, win)
        self._legend(ax, assignment)
        return RenderedTimeline(figure=fig, axes=ax, layout=result, window=win)

    @staticmethod
    def window_from_xlim(ax) -> tuple[datetime, datetime]:
        """Current visible time window from an axes' xlim (for re-layout)."""
        lo, hi = ax.get_xlim()
        return mdates.num2date(lo), mdates.num2date(hi)

    def _style_axes(self, ax, window: tuple[datetime, datetime]) -> None:
        for spine in ("top", "right", "left"):
            ax.spines[spine].set_visible(False)
        ax.spines["bottom"].set_position(("data", 0))
        ax.get_yaxis().set_ticks([])
        locator = mdates.AutoDateLocator(tz=self.display_tz)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator, tz=self.display_tz))
        ax.tick_params(axis="x", labelsize=self.style.font_size)

    def _legend(self, ax, assignment) -> None:
        handles: list[Line2D] = []
        for group in colour_mod.legend_groups(assignment):
            # a non-drawing header entry per family, then its users
            handles.append(Line2D([], [], linestyle="none", marker="",
                                  label=f"— {group.account_type.value} —"))
            for entry in group.entries:
                handles.append(Line2D(
                    [], [], linestyle="none", marker=entry.token.marker_token,
                    markerfacecolor=colour_for(entry.token),
                    markeredgecolor=colour_for(entry.token), markersize=6,
                    label=f"  {entry.username}"))
        if handles:
            ax.legend(handles=handles, loc="center left", bbox_to_anchor=(-0.16, 0.5),
                      fontsize=self.style.font_size - 1, frameon=False,
                      handletextpad=0.4, labelspacing=0.3)


# --- exports ----------------------------------------------------------------

def export_svg(rendered: RenderedTimeline, path: str) -> str:
    rendered.figure.savefig(path, format="svg", bbox_inches="tight")
    return path


def export_png(rendered: RenderedTimeline, path: str) -> str:
    rendered.figure.savefig(path, format="png", bbox_inches="tight", dpi=rendered.figure.dpi)
    return path
