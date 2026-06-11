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

from timeline_creator import filters
from timeline_creator.models import AccountType
from .conftest import make_event, utc


def _events():
    return [
        make_event(message="a", endpoint="HOST1", username="alice",
                   dt=utc(2025, 1, 1, 9)),
        make_event(message="b", endpoint="HOST2", username="bob",
                   dt=utc(2025, 1, 1, 10)),
        make_event(message="span", endpoint="HOST1", username="alice",
                   dt=utc(2025, 1, 1, 8), end=utc(2025, 1, 1, 12), span_id="s1"),
    ]


def test_endpoints_none_keeps_all():
    evs = _events()
    assert filters.by_endpoints(evs, None) == evs


def test_endpoints_filter():
    out = filters.by_endpoints(_events(), ["HOST2"])
    assert [e.message for e in out] == ["b"]


def test_users_filter():
    out = filters.by_users(_events(), ["bob"])
    assert [e.message for e in out] == ["b"]


def test_time_window_none_keeps_all():
    evs = _events()
    assert filters.by_time_window(evs, None, None) == evs


def test_time_window_drops_outside():
    out = filters.by_time_window(_events(), utc(2025, 1, 1, 9, 30), utc(2025, 1, 1, 11))
    # 'a' at 09:00 is outside; 'b' at 10:00 inside; span 08:00-12:00 intersects
    msgs = sorted(e.message for e in out)
    assert msgs == ["b", "span"]


def test_span_clipped_to_window():
    out = filters.by_time_window(_events(), utc(2025, 1, 1, 9), utc(2025, 1, 1, 11))
    span = next(e for e in out if e.message == "span")
    assert span.datetime == utc(2025, 1, 1, 9)   # start clipped up
    assert span.end == utc(2025, 1, 1, 11)        # end clipped down


def test_span_not_clipped_when_clip_false():
    out = filters.by_time_window(_events(), utc(2025, 1, 1, 9), utc(2025, 1, 1, 11), clip=False)
    span = next(e for e in out if e.message == "span")
    assert span.datetime == utc(2025, 1, 1, 8)
    assert span.end == utc(2025, 1, 1, 12)


def test_apply_chains_all():
    out = filters.apply(_events(), endpoints=["HOST1"], users=["alice"],
                        start=utc(2025, 1, 1, 8, 30), end=utc(2025, 1, 1, 13))
    # HOST1 + alice = 'a' and 'span'; 'a' at 09:00 inside window
    assert sorted(e.message for e in out) == ["a", "span"]


def test_point_event_at_window_edge_kept():
    out = filters.by_time_window(_events(), utc(2025, 1, 1, 9), utc(2025, 1, 1, 9))
    assert any(e.message == "a" for e in out)
