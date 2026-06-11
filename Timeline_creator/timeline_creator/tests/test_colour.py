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

from timeline_creator import colour
from timeline_creator.colour import SHADES_PER_FAMILY
from timeline_creator.models import AccountType
from .conftest import make_event


def test_account_type_maps_to_family():
    evs = [make_event(username="alice", account_type=AccountType.PRIVILEGED)]
    tokens = colour.assign(evs)
    assert tokens[(AccountType.PRIVILEGED, "alice")].family == "reds"


def test_guest_and_user_have_distinct_families():
    # The old code had no pool for these; here they get real families.
    evs = [
        make_event(username="g", account_type=AccountType.GUEST),
        make_event(username="u", account_type=AccountType.USER),
    ]
    tokens = colour.assign(evs)
    assert tokens[(AccountType.GUEST, "g")].family == "greens"
    assert tokens[(AccountType.USER, "u")].family == "purples"


def test_keyed_on_pair_not_username():
    # Same username, different account types -> different tokens.
    evs = [
        make_event(username="svc", account_type=AccountType.SERVICE),
        make_event(username="svc", account_type=AccountType.PRIVILEGED),
    ]
    tokens = colour.assign(evs)
    assert (AccountType.SERVICE, "svc") in tokens
    assert (AccountType.PRIVILEGED, "svc") in tokens
    assert tokens[(AccountType.SERVICE, "svc")].family == "greys"
    assert tokens[(AccountType.PRIVILEGED, "svc")].family == "reds"


def test_shades_increment_within_family():
    evs = [make_event(username=f"u{i}", account_type=AccountType.USER) for i in range(3)]
    tokens = colour.assign(evs)
    shades = sorted(tokens[(AccountType.USER, f"u{i}")].shade_index for i in range(3))
    assert shades == [0, 1, 2]


def test_marker_advances_when_shades_exhausted():
    n = SHADES_PER_FAMILY + 1
    evs = [make_event(username=f"u{i}", account_type=AccountType.USER) for i in range(n)]
    tokens = colour.assign(evs)
    markers = {tokens[(AccountType.USER, f"u{i}")].marker_token for i in range(n)}
    # the (SHADES_PER_FAMILY+1)-th user wraps shade and takes a new marker
    assert len(markers) == 2


def test_deterministic():
    evs = [make_event(username=f"u{i}", account_type=AccountType.USER) for i in range(5)]
    assert colour.assign(evs) == colour.assign(evs)


def test_legend_groups_grouped_by_family():
    evs = [
        make_event(username="root", account_type=AccountType.PRIVILEGED),
        make_event(username="alice", account_type=AccountType.USER),
        make_event(username="bob", account_type=AccountType.USER),
    ]
    groups = colour.legend_groups(colour.assign(evs))
    by_type = {g.account_type: g for g in groups}
    assert set(by_type) == {AccountType.PRIVILEGED, AccountType.USER}
    assert [e.username for e in by_type[AccountType.USER].entries] == ["alice", "bob"]
