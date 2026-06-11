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

"""Symbolic colour/marker assignment — pure, no matplotlib (D19).

The visual encoding inverts the old broken logic:

  primary channel   account type  -> a HUE FAMILY (privileged=reds, EDR=blues,
                                     service=greys, system=oranges, guest=greens,
                                     user=purples, unknown=neutral)
  secondary channel username      -> a SHADE within that family, and when a
                                     family's shades are exhausted, a MARKER
                                     shape (the fallback ladder).

Assignment is keyed on the ``(account_type, username)`` PAIR, which fixes the
old bugs: guest/user accounts had no colour pool and fell through to generic
colours; username-only keying made the same name under different account types
ambiguous.

This module emits *symbolic* tokens only (family name + shade index + marker
token). :mod:`timeline_creator.render` maps those tokens to concrete matplotlib
colours/markers, keeping this layer pure and unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

from .models import AccountType, Event

# account type -> hue family name. render owns the actual colour ramps.
FAMILY_BY_ACCOUNT_TYPE: dict[AccountType, str] = {
    AccountType.PRIVILEGED: "reds",
    AccountType.EDR: "blues",
    AccountType.SERVICE: "greys",
    AccountType.SYSTEM: "oranges",
    AccountType.GUEST: "greens",
    AccountType.USER: "purples",
    AccountType.UNKNOWN: "neutral",
}

# Number of distinguishable shades render provides per family ramp.
SHADES_PER_FAMILY = 4

# Marker tokens used once a family's shades are exhausted (render maps to mpl).
MARKERS: tuple[str, ...] = ("o", "s", "^", "D", "v", "P", "X", "*")


@dataclass(frozen=True)
class ColourToken:
    """A symbolic style for one ``(account_type, username)`` pair."""

    family: str
    shade_index: int     # 0 .. SHADES_PER_FAMILY - 1
    marker_token: str


@dataclass(frozen=True)
class LegendEntry:
    username: str
    token: ColourToken


@dataclass(frozen=True)
class LegendGroup:
    account_type: AccountType
    family: str
    entries: list[LegendEntry]


def _distinct_pairs(events: Sequence[Event]) -> list[tuple[AccountType, str]]:
    """Distinct (account_type, username) pairs, in a deterministic order."""
    seen: set[tuple[AccountType, str]] = set()
    for event in events:
        seen.add((event.account_type, event.username))
    return sorted(seen, key=lambda p: (p[0].value, p[1]))


def assign(events: Sequence[Event]) -> dict[tuple[AccountType, str], ColourToken]:
    """Map each ``(account_type, username)`` pair to a :class:`ColourToken`.

    Within a family, distinct usernames take successive shades; once the shades
    are used up the marker shape advances (hue -> shade -> marker ladder).
    """
    pairs = _distinct_pairs(events)
    family_counter: dict[str, int] = {}
    result: dict[tuple[AccountType, str], ColourToken] = {}
    for account_type, username in pairs:
        family = FAMILY_BY_ACCOUNT_TYPE[account_type]
        k = family_counter.get(family, 0)
        family_counter[family] = k + 1
        shade_index = k % SHADES_PER_FAMILY
        marker_token = MARKERS[(k // SHADES_PER_FAMILY) % len(MARKERS)]
        result[(account_type, username)] = ColourToken(family, shade_index, marker_token)
    return result


def legend_groups(
    assignment: dict[tuple[AccountType, str], ColourToken],
) -> list[LegendGroup]:
    """Group an assignment by account-type family for a structured legend.

    Groups follow account-type enum order; entries within a group are sorted by
    shade then username, so the legend reads predictably.
    """
    by_type: dict[AccountType, list[LegendEntry]] = {}
    for (account_type, username), token in assignment.items():
        by_type.setdefault(account_type, []).append(LegendEntry(username, token))

    groups: list[LegendGroup] = []
    for account_type in AccountType:  # enum definition order
        entries = by_type.get(account_type)
        if not entries:
            continue
        entries.sort(key=lambda e: (e.token.shade_index, e.username))
        groups.append(LegendGroup(account_type, FAMILY_BY_ACCOUNT_TYPE[account_type], entries))
    return groups
