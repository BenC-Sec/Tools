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

"""Pure filtering over a list of events (D20, D21).

Defaults are deliberately inclusive: the whole investigation, with every
endpoint and user selected. Passing ``None`` for a selection means "all" — the
analyst narrows down from everything rather than building a selection up from
nothing (the opposite of the old none-selected default).

A time window is optional. Spans that straddle the window edge are clipped to
the window so their bars don't render outside it (the tz-aware successor to the
old ``filter_by_time_range`` clip behaviour).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from .models import Event


def by_endpoints(events: Sequence[Event], endpoints: Iterable[str] | None) -> list[Event]:
    """Keep events on the given endpoints. ``None`` keeps all (D21)."""
    if endpoints is None:
        return list(events)
    allowed = set(endpoints)
    return [e for e in events if e.endpoint in allowed]


def by_users(events: Sequence[Event], usernames: Iterable[str] | None) -> list[Event]:
    """Keep events for the given usernames. ``None`` keeps all (D21)."""
    if usernames is None:
        return list(events)
    allowed = set(usernames)
    return [e for e in events if e.username in allowed]


def _intersects(event: Event, start: datetime | None, end: datetime | None) -> bool:
    event_end = event.end if event.is_span else event.datetime
    if start is not None and event_end < start:
        return False
    if end is not None and event.datetime > end:
        return False
    return True


def _clip(event: Event, start: datetime | None, end: datetime | None) -> Event:
    if not event.is_span:
        return event
    new_start = max(event.datetime, start) if start is not None else event.datetime
    new_end = min(event.end, end) if end is not None else event.end
    if new_start == event.datetime and new_end == event.end:
        return event
    return event.model_copy(update={"datetime": new_start, "end": new_end})


def by_time_window(events: Sequence[Event], start: datetime | None = None,
                   end: datetime | None = None, *, clip: bool = True) -> list[Event]:
    """Keep events intersecting ``[start, end]``. ``None`` bounds are open (D20).

    Spans crossing a bound are clipped to the window when ``clip`` is True.
    """
    kept = [e for e in events if _intersects(e, start, end)]
    if clip:
        kept = [_clip(e, start, end) for e in kept]
    return kept


def apply(events: Sequence[Event], *, endpoints: Iterable[str] | None = None,
          users: Iterable[str] | None = None, start: datetime | None = None,
          end: datetime | None = None, clip: bool = True) -> list[Event]:
    """Apply endpoint, user, and time-window filters in one call."""
    result = by_endpoints(events, endpoints)
    result = by_users(result, users)
    result = by_time_window(result, start, end, clip=clip)
    return result
