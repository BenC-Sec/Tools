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

"""Pydantic data model — the single validation gate for every input path.

Every event, whether typed in manually, pasted from CSV, loaded from xlsx, or
read back off disk, is validated through :class:`Event`. That kills the
divergent ad-hoc checks that made the old code fragile (D23).

Time handling (D12): timestamps are stored timezone-AWARE and normalised to
UTC. Naive datetimes are rejected outright — the caller must attach a timezone
(the UI enters in UTC by default). This fixes the old
``datetime.combine(...).isoformat()`` naive-local bug.

Spans (start + end) are first-class here (D11): an :class:`Event` with ``end``
set is a span and renders as a bar. On-disk decomposition into linked point
records lives in :mod:`timeline_creator.io`, not here.
"""

from __future__ import annotations

from datetime import datetime as _DateTime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 1


class AccountType(str, Enum):
    """Account types an analyst attributes events to.

    Values are the human display strings (kept stable for the UI dropdown and
    the on-disk format). EDR is not strictly an account type but is a useful
    attribution bucket during investigations.
    """

    GUEST = "Guest account"
    USER = "User account"
    PRIVILEGED = "Privileged account"
    SERVICE = "Service account"
    SYSTEM = "System account"
    EDR = "EDR"
    UNKNOWN = "Unknown"

    @classmethod
    def _missing_(cls, value: object) -> "AccountType | None":
        """Accept loose input (case-insensitive, short forms) from imports.

        Lets ``AccountType("privileged")`` / ``"PRIVILEGED ACCOUNT"`` resolve so
        pasted spreadsheets do not fail on trivial casing differences.
        """
        if not isinstance(value, str):
            return None
        needle = value.strip().casefold()
        for member in cls:
            if member.value.casefold() == needle:
                return member
        # short form: match on the first word ("privileged", "service", ...)
        for member in cls:
            if member.value.split()[0].casefold() == needle:
                return member
        return None


def _ensure_aware_utc(value: _DateTime) -> _DateTime:
    """Reject naive datetimes; normalise aware ones to UTC (D12)."""
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(
            "datetime must be timezone-aware (no naive datetimes). "
            "Attach an explicit timezone/offset before creating an Event."
        )
    return value.astimezone(timezone.utc)


class Event(BaseModel):
    """A single timeline event.

    A point event has ``end is None``. A span has ``end`` set and ``end`` must
    be >= ``datetime``. ``span_id`` links the two on-disk records of a span and
    round-trips; it is normally None for point events.

    Field names follow Timesketch (D9): ``datetime`` (the timestamp),
    ``message`` (the human-readable label, formerly ``description``).
    """

    model_config = ConfigDict(extra="forbid")

    datetime: _DateTime = Field(description="Event time (start time for spans).")
    message: str = Field(min_length=1, description="Human-readable label.")
    endpoint: str = Field(min_length=1)
    username: str = Field(min_length=1)
    account_type: AccountType
    end: _DateTime | None = Field(default=None, description="Span end time.")
    span_id: str | None = Field(default=None, description="Links a span's two on-disk records.")

    @field_validator("datetime", "end")
    @classmethod
    def _aware_utc(cls, value: _DateTime | None) -> _DateTime | None:
        if value is None:
            return None
        return _ensure_aware_utc(value)

    @model_validator(mode="after")
    def _check_span(self) -> "Event":
        if self.end is not None and self.end < self.datetime:
            raise ValueError(
                f"span end ({self.end.isoformat()}) is before start "
                f"({self.datetime.isoformat()})"
            )
        return self

    @property
    def is_span(self) -> bool:
        return self.end is not None


class Investigation(BaseModel):
    """A named collection of events plus the endpoints/users seen in it.

    ``endpoints`` and ``users`` are the catalogues the UI offers for quick
    entry; events may reference values auto-added on import (D18).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    endpoints: list[str] = Field(default_factory=list)
    users: dict[str, AccountType] = Field(default_factory=dict)
    events: list[Event] = Field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    def add_endpoint(self, endpoint: str) -> bool:
        """Add an endpoint if new. Returns True if it was added."""
        endpoint = endpoint.strip()
        if endpoint and endpoint not in self.endpoints:
            self.endpoints.append(endpoint)
            return True
        return False

    def add_user(self, username: str, account_type: AccountType) -> bool:
        """Add/replace a user->account_type mapping. Returns True if changed."""
        username = username.strip()
        if not username:
            return False
        account_type = AccountType(account_type)
        if self.users.get(username) == account_type:
            return False
        self.users[username] = account_type
        return True

    def add_event(self, event: Event) -> None:
        """Append an event, auto-cataloguing its endpoint and user (D18)."""
        self.add_endpoint(event.endpoint)
        self.add_user(event.username, event.account_type)
        self.events.append(event)
