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

"""Thin ipywidgets UI — a three-panel notebook controller (D15, D16).

All business logic lives in the pure core; this module only wires widgets to it.

  Panel 1 Setup    investigation name (create/load/save) + endpoint and user
                   running lists (type-and-enter, no per-item cell re-run).
  Panel 2 Events   a live events table (single source of truth) + a sticky
                   manual form (host/user/type persist after submit) + a bulk
                   import box (CSV paste + xlsx upload). Every path goes through
                   the one Event validator.
  Panel 3 Display  filters (default ALL selected, whole investigation) + the
                   rendered timeline + a "re-layout for current view" button +
                   SVG/PNG export.

Use ``%matplotlib widget`` (ipympl) in the notebook for an interactive
zoom/pan view; the re-layout button recomputes stacking for the visible window.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

import ipywidgets as widgets
from IPython.display import display

from . import importers, io
from .models import AccountType, Event, Investigation

_ACCOUNT_TYPE_OPTIONS = [(at.value, at) for at in AccountType]


def _enable_enter(text: "widgets.Text", handler) -> None:
    """Wire Enter-to-submit if the ipywidgets version still supports on_submit.

    ``Text.on_submit`` is deprecated in ipywidgets 8 but still functional; the
    explicit Add buttons are the reliable path, so this is best-effort only.
    """
    try:
        text.on_submit(lambda *_: handler(None))
    except Exception:  # noqa: BLE001 - removed in a future ipywidgets
        pass


def _parse_utc(date_str: str, time_str: str) -> datetime:
    """Combine a YYYY-MM-DD date and HH:MM[:SS] time into an aware UTC datetime."""
    date_str, time_str = date_str.strip(), time_str.strip()
    if not date_str:
        raise ValueError("date is required (YYYY-MM-DD)")
    if not time_str:
        time_str = "00:00:00"
    if time_str.count(":") == 1:
        time_str += ":00"
    naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
    return naive.replace(tzinfo=timezone.utc)


class TimelineApp:
    """In-memory controller backing the notebook UI."""

    def __init__(self, directory: str | Path = "."):
        self.directory = Path(directory)
        self.investigation: Investigation | None = None
        self._renderer = None      # lazy: importing render pulls in matplotlib
        self._rendered = None      # last RenderedTimeline

    # -- helpers -------------------------------------------------------------

    def _require_investigation(self) -> Investigation:
        if self.investigation is None:
            raise RuntimeError("No investigation loaded. Create or open one in Setup.")
        return self.investigation

    @staticmethod
    def _status(out: widgets.Output, message: str, *, error: bool = False) -> None:
        with out:
            prefix = "⚠ " if error else "✓ "
            print(prefix + message)

    # =====================================================================
    # Panel 1 — Setup
    # =====================================================================

    def setup_panel(self) -> widgets.Widget:
        status = widgets.Output()

        name = widgets.Text(description="Investigation:", placeholder="case name",
                            style={"description_width": "auto"},
                            layout=widgets.Layout(width="360px"))
        existing = widgets.Dropdown(description="Open:", options=[""] + io.list_investigations(self.directory),
                                    style={"description_width": "auto"})
        create_btn = widgets.Button(description="Create", button_style="success")
        open_btn = widgets.Button(description="Open", button_style="info")
        save_btn = widgets.Button(description="Save", button_style="primary")

        endpoint_in = widgets.Text(placeholder="add endpoint")
        add_endpoint_btn = widgets.Button(description="Add endpoint")
        endpoints_view = widgets.HTML()
        user_in = widgets.Text(placeholder="add username")
        user_type = widgets.Dropdown(options=_ACCOUNT_TYPE_OPTIONS, value=AccountType.USER,
                                     layout=widgets.Layout(width="200px"))
        add_user_btn = widgets.Button(description="Add user")
        users_view = widgets.HTML()

        def refresh_catalogues():
            inv = self.investigation
            endpoints_view.value = "<b>Endpoints:</b> " + (
                ", ".join(html.escape(e) for e in inv.endpoints) if inv and inv.endpoints else "—")
            users_view.value = "<b>Users:</b> " + (
                ", ".join(f"{html.escape(u)} ({a.value})" for u, a in inv.users.items())
                if inv and inv.users else "—")

        def on_create(_):
            with status:
                status.clear_output()
            try:
                self.investigation = Investigation(name=name.value.strip())
                self._status(status, f"created '{self.investigation.name}'.")
                refresh_catalogues()
            except Exception as exc:  # noqa: BLE001 - surface to the analyst
                self._status(status, str(exc), error=True)

        def on_open(_):
            with status:
                status.clear_output()
            try:
                target = existing.value or name.value.strip()
                result = io.load(target, self.directory)
                self.investigation = result.investigation
                name.value = self.investigation.name
                for warning in result.warnings:
                    self._status(status, warning, error=True)
                self._status(status, f"opened '{self.investigation.name}' "
                                     f"({len(self.investigation.events)} events).")
                refresh_catalogues()
            except Exception as exc:  # noqa: BLE001
                self._status(status, str(exc), error=True)

        def on_save(_):
            try:
                inv = self._require_investigation()
                jsonl, meta = io.save(inv, self.directory)
                existing.options = [""] + io.list_investigations(self.directory)
                self._status(status, f"saved {jsonl.name} + {meta.name}.")
            except Exception as exc:  # noqa: BLE001
                self._status(status, str(exc), error=True)

        def on_add_endpoint(_):
            try:
                inv = self._require_investigation()
                if inv.add_endpoint(endpoint_in.value):
                    endpoint_in.value = ""
                    refresh_catalogues()
            except Exception as exc:  # noqa: BLE001
                self._status(status, str(exc), error=True)

        def on_add_user(_):
            try:
                inv = self._require_investigation()
                if inv.add_user(user_in.value, user_type.value):
                    user_in.value = ""
                    refresh_catalogues()
            except Exception as exc:  # noqa: BLE001
                self._status(status, str(exc), error=True)

        create_btn.on_click(on_create)
        open_btn.on_click(on_open)
        save_btn.on_click(on_save)
        add_endpoint_btn.on_click(on_add_endpoint)
        add_user_btn.on_click(on_add_user)
        _enable_enter(endpoint_in, on_add_endpoint)  # best-effort Enter-to-add
        _enable_enter(user_in, on_add_user)
        self._refresh_catalogues = refresh_catalogues

        return widgets.VBox([
            widgets.HBox([name, create_btn, save_btn]),
            widgets.HBox([existing, open_btn]),
            widgets.HTML("<hr style='margin:6px 0'>"),
            widgets.HBox([endpoint_in, add_endpoint_btn]),
            endpoints_view,
            widgets.HBox([user_in, user_type, add_user_btn]),
            users_view,
            status,
        ])

    # =====================================================================
    # Panel 2 — Events
    # =====================================================================

    def events_panel(self) -> widgets.Widget:
        status = widgets.Output()
        table = widgets.HTML()

        endpoint = widgets.Combobox(description="Endpoint:", ensure_option=False,
                                    style={"description_width": "auto"})
        username = widgets.Combobox(description="User:", ensure_option=False,
                                    style={"description_width": "auto"})
        account_type = widgets.Dropdown(description="Type:", options=_ACCOUNT_TYPE_OPTIONS,
                                        value=AccountType.USER,
                                        style={"description_width": "auto"})
        message = widgets.Text(description="Message:", placeholder="what happened",
                               style={"description_width": "auto"},
                               layout=widgets.Layout(width="480px"))
        date_in = widgets.Text(description="Date (UTC):", placeholder="YYYY-MM-DD",
                               style={"description_width": "auto"})
        time_in = widgets.Text(description="Time:", placeholder="HH:MM:SS",
                               style={"description_width": "auto"})
        is_span = widgets.Checkbox(value=False, description="Span (has end)")
        end_date = widgets.Text(description="End date:", placeholder="YYYY-MM-DD",
                                style={"description_width": "auto"})
        end_time = widgets.Text(description="End time:", placeholder="HH:MM:SS",
                                style={"description_width": "auto"})
        add_btn = widgets.Button(description="Add event", button_style="success")

        row_pick = widgets.Dropdown(description="Row:", style={"description_width": "auto"})
        edit_btn = widgets.Button(description="Edit (load into form)")
        delete_btn = widgets.Button(description="Delete", button_style="danger")

        csv_box = widgets.Textarea(placeholder="Paste CSV with header: "
                                   "datetime,message,endpoint,username,account_type[,end,span_id]",
                                   layout=widgets.Layout(width="640px", height="120px"))
        csv_btn = widgets.Button(description="Import CSV", button_style="info")
        xlsx_up = widgets.FileUpload(accept=".xlsx", multiple=False, description="Upload .xlsx")

        def refresh_table():
            inv = self.investigation
            options = []
            if inv is None or not inv.events:
                table.value = "<i>No events yet.</i>"
            else:
                rows = ["<tr><th>#</th><th>datetime (UTC)</th><th>end</th>"
                        "<th>message</th><th>endpoint</th><th>user</th><th>type</th></tr>"]
                for i, e in enumerate(inv.events):
                    rows.append(
                        f"<tr><td>{i}</td><td>{e.datetime.isoformat()}</td>"
                        f"<td>{e.end.isoformat() if e.end else ''}</td>"
                        f"<td>{html.escape(e.message)}</td><td>{html.escape(e.endpoint)}</td>"
                        f"<td>{html.escape(e.username)}</td><td>{e.account_type.value}</td></tr>")
                table.value = ("<table border='1' cellpadding='3' "
                               "style='border-collapse:collapse;font-size:12px'>"
                               + "".join(rows) + "</table>")
                options = [(f"{i}: {e.message[:30]}", i) for i, e in enumerate(inv.events)]
            row_pick.options = options
            # keep the form's host/user comboboxes in sync with the catalogues
            if inv is not None:
                endpoint.options = inv.endpoints
                username.options = list(inv.users.keys())

        def build_event() -> Event:
            start = _parse_utc(date_in.value, time_in.value)
            end = _parse_utc(end_date.value, end_time.value) if is_span.value else None
            return Event(datetime=start, end=end, message=message.value,
                         endpoint=endpoint.value, username=username.value,
                         account_type=account_type.value)

        def on_add(_):
            with status:
                status.clear_output()
            try:
                inv = self._require_investigation()
                inv.add_event(build_event())
                # sticky: keep host/user/type; clear the per-event fields
                message.value = ""
                time_in.value = ""
                refresh_table()
                if getattr(self, "_refresh_catalogues", None):
                    self._refresh_catalogues()
                self._status(status, "event added.")
            except Exception as exc:  # noqa: BLE001
                self._status(status, str(exc), error=True)

        def on_delete(_):
            try:
                inv = self._require_investigation()
                if row_pick.value is not None:
                    removed = inv.events.pop(row_pick.value)
                    refresh_table()
                    self._status(status, f"deleted '{removed.message}'.")
            except Exception as exc:  # noqa: BLE001
                self._status(status, str(exc), error=True)

        def on_edit(_):
            try:
                inv = self._require_investigation()
                if row_pick.value is None:
                    return
                e = inv.events[row_pick.value]
                endpoint.value, username.value = e.endpoint, e.username
                account_type.value = e.account_type
                message.value = e.message
                date_in.value, time_in.value = e.datetime.date().isoformat(), \
                    e.datetime.strftime("%H:%M:%S")
                is_span.value = e.is_span
                if e.end:
                    end_date.value = e.end.date().isoformat()
                    end_time.value = e.end.strftime("%H:%M:%S")
                inv.events.pop(row_pick.value)  # editing == delete + re-add on submit
                refresh_table()
                self._status(status, "loaded into form; resubmit to save the edit.")
            except Exception as exc:  # noqa: BLE001
                self._status(status, str(exc), error=True)

        def _commit_import(result):
            inv = self._require_investigation()
            if not result.ok:
                with status:
                    self._status(status, f"import rejected — {len(result.errors)} bad row(s):",
                                 error=True)
                    for err in result.errors:
                        print(f"   row {err.row}: {err.message}")
                return
            for event in result.events:
                inv.add_event(event)
            refresh_table()
            if getattr(self, "_refresh_catalogues", None):
                self._refresh_catalogues()
            self._status(status, f"imported {len(result.events)} event(s).")

        def on_csv(_):
            with status:
                status.clear_output()
            try:
                _commit_import(importers.parse_csv(csv_box.value))
            except Exception as exc:  # noqa: BLE001
                self._status(status, str(exc), error=True)

        def on_xlsx(change):
            if not xlsx_up.value:
                return
            with status:
                status.clear_output()
            try:
                item = next(iter(xlsx_up.value.values())) if isinstance(xlsx_up.value, dict) \
                    else xlsx_up.value[0]
                content = item["content"] if isinstance(item, dict) else item.content
                _commit_import(importers.parse_xlsx(bytes(content)))
            except Exception as exc:  # noqa: BLE001
                self._status(status, str(exc), error=True)

        add_btn.on_click(on_add)
        delete_btn.on_click(on_delete)
        edit_btn.on_click(on_edit)
        csv_btn.on_click(on_csv)
        xlsx_up.observe(on_xlsx, names="value")
        self._refresh_events_table = refresh_table

        form = widgets.VBox([
            widgets.HBox([endpoint, username, account_type]),
            message,
            widgets.HBox([date_in, time_in]),
            is_span,
            widgets.HBox([end_date, end_time]),
            add_btn,
        ])
        return widgets.VBox([
            widgets.HTML("<b>Events</b>"), table,
            widgets.HBox([row_pick, edit_btn, delete_btn]),
            widgets.HTML("<hr style='margin:6px 0'><b>Add / edit event</b>"), form,
            widgets.HTML("<hr style='margin:6px 0'><b>Bulk import</b>"),
            csv_box, widgets.HBox([csv_btn, xlsx_up]),
            status,
        ])

    # =====================================================================
    # Panel 3 — Display
    # =====================================================================

    def _get_renderer(self):
        if self._renderer is None:
            from .render import TimelineRenderer  # lazy: pulls in matplotlib
            self._renderer = TimelineRenderer()
        return self._renderer

    def display_panel(self) -> widgets.Widget:
        from . import filters
        from . import render as render_mod

        status = widgets.Output()
        plot = widgets.Output()

        endpoints_sel = widgets.SelectMultiple(description="Endpoints:", rows=6,
                                               style={"description_width": "auto"})
        users_sel = widgets.SelectMultiple(description="Users:", rows=6,
                                            style={"description_width": "auto"})
        all_btn = widgets.Button(description="Select all")
        clear_btn = widgets.Button(description="Clear")
        start_in = widgets.Text(description="From (UTC):", placeholder="YYYY-MM-DD HH:MM (optional)",
                                style={"description_width": "auto"})
        end_in = widgets.Text(description="To (UTC):", placeholder="YYYY-MM-DD HH:MM (optional)",
                              style={"description_width": "auto"})
        render_btn = widgets.Button(description="Render timeline", button_style="success")
        relayout_btn = widgets.Button(description="Re-layout for current view")
        svg_name = widgets.Text(value="timeline.svg", description="SVG file:",
                                style={"description_width": "auto"})
        export_svg_btn = widgets.Button(description="Export SVG", button_style="primary")
        png_name = widgets.Text(value="timeline.png", description="PNG file:",
                                style={"description_width": "auto"})
        export_png_btn = widgets.Button(description="Export PNG")

        def populate_filters():
            inv = self.investigation
            if inv is None:
                return
            endpoints_sel.options = inv.endpoints
            endpoints_sel.value = tuple(inv.endpoints)       # default: ALL (D21)
            users_sel.options = list(inv.users.keys())
            users_sel.value = tuple(inv.users.keys())

        def _opt_dt(text: str):
            text = text.strip()
            if not text:
                return None
            parts = text.split()
            return _parse_utc(parts[0], parts[1] if len(parts) > 1 else "00:00:00")

        def _filtered_events():
            inv = self._require_investigation()
            return filters.apply(
                inv.events,
                endpoints=list(endpoints_sel.value) if endpoints_sel.value else None,
                users=list(users_sel.value) if users_sel.value else None,
                start=_opt_dt(start_in.value), end=_opt_dt(end_in.value),
            )

        def _show(rt):
            self._rendered = rt
            with plot:
                plot.clear_output(wait=True)
                display(rt.figure)
            with status:
                for warning in rt.layout.warnings:
                    self._status(status, warning, error=True)
                for suggestion in rt.layout.split_suggestions:
                    print(f"   split suggestion: {suggestion.window_start_dt.isoformat()} → "
                          f"{suggestion.window_end_dt.isoformat()} ({suggestion.peak_levels} levels)")

        def on_render(_):
            with status:
                status.clear_output()
            try:
                events = _filtered_events()
                if not events:
                    self._status(status, "no events match the current filters.", error=True)
                    return
                _show(self._get_renderer().render(events))
            except Exception as exc:  # noqa: BLE001
                self._status(status, str(exc), error=True)

        def on_relayout(_):
            with status:
                status.clear_output()
            try:
                if self._rendered is None:
                    self._status(status, "render first, then zoom and re-layout.", error=True)
                    return
                renderer = self._get_renderer()
                window = renderer.window_from_xlim(self._rendered.axes)
                rt = renderer.render(_filtered_events(), window=window,
                                     into_figure=self._rendered.figure)
                self._rendered = rt
                rt.figure.canvas.draw_idle()
                with status:
                    self._status(status, "re-laid out for the current view.")
            except Exception as exc:  # noqa: BLE001
                self._status(status, str(exc), error=True)

        def on_export_svg(_):
            try:
                if self._rendered is None:
                    raise RuntimeError("render a timeline first.")
                path = render_mod.export_svg(self._rendered, svg_name.value)
                self._status(status, f"wrote {path}.")
            except Exception as exc:  # noqa: BLE001
                self._status(status, str(exc), error=True)

        def on_export_png(_):
            try:
                if self._rendered is None:
                    raise RuntimeError("render a timeline first.")
                path = render_mod.export_png(self._rendered, png_name.value)
                self._status(status, f"wrote {path}.")
            except Exception as exc:  # noqa: BLE001
                self._status(status, str(exc), error=True)

        all_btn.on_click(lambda _: setattr(endpoints_sel, "value", tuple(endpoints_sel.options))
                         or setattr(users_sel, "value", tuple(users_sel.options)))
        clear_btn.on_click(lambda _: setattr(endpoints_sel, "value", ())
                           or setattr(users_sel, "value", ()))
        render_btn.on_click(on_render)
        relayout_btn.on_click(on_relayout)
        export_svg_btn.on_click(on_export_svg)
        export_png_btn.on_click(on_export_png)
        self._populate_filters = populate_filters

        controls = widgets.VBox([
            widgets.HBox([endpoints_sel, users_sel]),
            widgets.HBox([all_btn, clear_btn]),
            widgets.HBox([start_in, end_in]),
            widgets.HBox([render_btn, relayout_btn]),
            widgets.HBox([svg_name, export_svg_btn, png_name, export_png_btn]),
            status,
        ])
        return widgets.VBox([controls, plot])

    # =====================================================================
    # Assembly
    # =====================================================================

    def build(self) -> widgets.Widget:
        """Build the full three-panel UI and refresh dependent views on tab change."""
        setup = self.setup_panel()
        events = self.events_panel()
        display_ = self.display_panel()

        accordion = widgets.Accordion(children=[setup, events, display_])
        accordion.set_title(0, "1 · Setup")
        accordion.set_title(1, "2 · Events")
        accordion.set_title(2, "3 · Display")
        accordion.selected_index = 0

        def on_tab(change):
            # refresh the panel being opened so it reflects the latest state
            if change["new"] == 1 and getattr(self, "_refresh_events_table", None):
                self._refresh_events_table()
            elif change["new"] == 2 and getattr(self, "_populate_filters", None):
                self._populate_filters()

        accordion.observe(on_tab, names="selected_index")
        return accordion


def launch(directory: str | Path = ".") -> TimelineApp:
    """Build, display, and return the app. Call this from a notebook cell."""
    app = TimelineApp(directory)
    display(app.build())
    return app
