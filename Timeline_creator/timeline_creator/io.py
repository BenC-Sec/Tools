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

"""On-disk persistence — Timesketch-aligned JSONL + a metadata sidecar.

Layout per investigation (D10, D14):

  <name>.jsonl       one Timesketch-style event record per line
  <name>.meta.json   sidecar: name, endpoints[], users->account_type, schema_version

Spans are point-event models in Timesketch/plaso, so a span is DECOMPOSED on
disk into two linked point records sharing a ``span_id`` — one
``timestamp_desc: "Start"`` and one ``"End"`` (D11). They are reconstituted into
a single :class:`Event` on load. A point event is a single record
(``timestamp_desc: "Event"``).

KEEP-EVERY-LABEL ethos applies to loading too: an orphaned span half (a Start
with no End, or vice versa) is promoted to a point event with a warning rather
than dropped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import AccountType, Event, Investigation, SCHEMA_VERSION

# On-disk timestamp_desc values.
DESC_EVENT = "Event"
DESC_START = "Start"
DESC_END = "End"


@dataclass
class LoadResult:
    """Outcome of :func:`load` — the investigation plus any non-fatal warnings."""

    investigation: Investigation
    warnings: list[str] = field(default_factory=list)


def _jsonl_path(name: str, directory: Path) -> Path:
    return directory / f"{name}.jsonl"


def _meta_path(name: str, directory: Path) -> Path:
    return directory / f"{name}.meta.json"


def _event_to_records(event: Event, span_id: str) -> list[dict]:
    """Serialise one Event to one (point) or two (span) on-disk records."""
    base = {
        "message": event.message,
        "endpoint": event.endpoint,
        "username": event.username,
        "account_type": event.account_type.value,
    }
    if not event.is_span:
        return [{"datetime": event.datetime.isoformat(), "timestamp_desc": DESC_EVENT, **base}]
    return [
        {"datetime": event.datetime.isoformat(), "timestamp_desc": DESC_START,
         "span_id": span_id, **base},
        {"datetime": event.end.isoformat(), "timestamp_desc": DESC_END,
         "span_id": span_id, **base},
    ]


def save(investigation: Investigation, directory: str | Path = ".") -> tuple[Path, Path]:
    """Write ``<name>.jsonl`` + ``<name>.meta.json``. Returns both paths.

    Spans without an explicit ``span_id`` get a deterministic synthesised one
    (``span-<index>``) so the file is stable run-to-run.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    for index, event in enumerate(investigation.events):
        span_id = event.span_id or f"span-{index}"
        for record in _event_to_records(event, span_id):
            lines.append(json.dumps(record))

    jsonl = _jsonl_path(investigation.name, directory)
    jsonl.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    meta = {
        "name": investigation.name,
        "endpoints": investigation.endpoints,
        "users": {user: at.value for user, at in investigation.users.items()},
        "schema_version": investigation.schema_version,
    }
    meta_path = _meta_path(investigation.name, directory)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return jsonl, meta_path


def _point_event_from_record(record: dict, *, end: str | None = None,
                             span_id: str | None = None) -> Event:
    return Event(
        datetime=record["datetime"],
        end=end,
        message=record["message"],
        endpoint=record["endpoint"],
        username=record["username"],
        account_type=AccountType(record["account_type"]),
        span_id=span_id,
    )


def _reconstitute(records: list[dict], warnings: list[str]) -> list[Event]:
    """Rebuild Events from raw records, pairing spans and promoting orphans."""
    # Group span halves by span_id, preserving first-seen order via line index.
    span_groups: dict[str, dict] = {}
    ordered: list[tuple[int, str]] = []  # (line_index, kind) where kind is "point" or span_id
    points: dict[int, dict] = {}

    for index, record in enumerate(records):
        desc = record.get("timestamp_desc", DESC_EVENT)
        span_id = record.get("span_id")
        if desc in (DESC_START, DESC_END) and span_id:
            group = span_groups.setdefault(span_id, {"first_index": index})
            group[desc] = record
            if span_id not in {sid for _, sid in ordered}:
                ordered.append((index, span_id))
        else:
            points[index] = record
            ordered.append((index, "point"))

    events: list[Event] = []
    for index, key in ordered:
        if key == "point":
            events.append(_point_event_from_record(points[index]))
            continue
        group = span_groups[key]
        start = group.get(DESC_START)
        end = group.get(DESC_END)
        if start and end:
            events.append(_point_event_from_record(start, end=end["datetime"], span_id=key))
        elif start:
            warnings.append(
                f"span '{key}' has a Start but no End; promoted to a point event."
            )
            events.append(_point_event_from_record(start, span_id=key))
        elif end:
            warnings.append(
                f"span '{key}' has an End but no Start; promoted to a point event."
            )
            events.append(_point_event_from_record(end, span_id=key))
    return events


def load(name: str, directory: str | Path = ".") -> LoadResult:
    """Load an investigation by name. Returns the model plus any warnings.

    The ``.jsonl`` is the source of truth for events; ``.meta.json`` supplies
    the endpoint/user catalogues. If the sidecar is missing, catalogues are
    derived from the events themselves.
    """
    directory = Path(directory)
    jsonl = _jsonl_path(name, directory)
    if not jsonl.exists():
        raise FileNotFoundError(f"No events file for investigation '{name}' at {jsonl}")

    warnings: list[str] = []
    records = [
        json.loads(line)
        for line in jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    events = _reconstitute(records, warnings)

    meta_path = _meta_path(name, directory)
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        endpoints = meta.get("endpoints", [])
        users = {u: AccountType(a) for u, a in meta.get("users", {}).items()}
        schema_version = meta.get("schema_version", SCHEMA_VERSION)
        inv_name = meta.get("name", name)
    else:
        warnings.append(f"No metadata sidecar for '{name}'; catalogues derived from events.")
        endpoints = []
        users = {}
        schema_version = SCHEMA_VERSION
        inv_name = name

    investigation = Investigation(
        name=inv_name,
        endpoints=list(endpoints),
        users=users,
        events=events,
        schema_version=schema_version,
    )
    # Backfill catalogues from events (covers missing sidecar and auto-added refs).
    for event in events:
        investigation.add_endpoint(event.endpoint)
        investigation.add_user(event.username, event.account_type)

    return LoadResult(investigation=investigation, warnings=warnings)


def list_investigations(directory: str | Path = ".") -> list[str]:
    """Return the sorted names of investigations (files ending in ``.jsonl``)."""
    directory = Path(directory)
    if not directory.exists():
        return []
    return sorted(p.name[: -len(".jsonl")] for p in directory.glob("*.jsonl"))
