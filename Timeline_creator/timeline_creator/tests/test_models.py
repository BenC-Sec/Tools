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

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from timeline_creator.models import AccountType, Event, Investigation
from .conftest import make_event, utc


# --- timezone handling (D12) ------------------------------------------------

def test_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        Event(datetime=datetime(2025, 1, 1, 12, 0, 0), message="x",
              endpoint="H", username="u", account_type=AccountType.USER)


def test_aware_non_utc_normalised_to_utc():
    plus2 = timezone(timedelta(hours=2))
    ev = Event(datetime=datetime(2025, 1, 1, 14, 0, 0, tzinfo=plus2), message="x",
               endpoint="H", username="u", account_type=AccountType.USER)
    assert ev.datetime == utc(2025, 1, 1, 12, 0, 0)
    assert ev.datetime.tzinfo == timezone.utc


def test_naive_end_rejected():
    with pytest.raises(ValidationError):
        Event(datetime=utc(2025, 1, 1, 12), message="x", endpoint="H",
              username="u", account_type=AccountType.USER,
              end=datetime(2025, 1, 1, 13))


# --- span validation (D11) --------------------------------------------------

def test_span_end_before_start_rejected():
    with pytest.raises(ValidationError):
        make_event(dt=utc(2025, 1, 1, 12), end=utc(2025, 1, 1, 11))


def test_span_end_equal_start_allowed():
    ev = make_event(dt=utc(2025, 1, 1, 12), end=utc(2025, 1, 1, 12))
    assert ev.is_span


def test_point_event_is_not_span():
    assert make_event().is_span is False


def test_span_event_is_span():
    assert make_event(end=utc(2025, 1, 1, 13)).is_span is True


# --- required fields --------------------------------------------------------

def test_empty_message_rejected():
    with pytest.raises(ValidationError):
        make_event(message="")


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        Event(datetime=utc(2025, 1, 1), message="x", endpoint="H", username="u",
              account_type=AccountType.USER, bogus=1)


# --- account type coercion --------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Privileged account", AccountType.PRIVILEGED),
    ("privileged account", AccountType.PRIVILEGED),
    ("PRIVILEGED", AccountType.PRIVILEGED),
    ("service", AccountType.SERVICE),
    ("EDR", AccountType.EDR),
])
def test_account_type_loose_parsing(raw, expected):
    assert AccountType(raw) is expected


def test_account_type_unknown_raises():
    with pytest.raises(ValueError):
        AccountType("not a real type")


# --- Investigation helpers (D18) -------------------------------------------

def test_add_endpoint_idempotent():
    inv = Investigation(name="c")
    assert inv.add_endpoint("HOST1") is True
    assert inv.add_endpoint("HOST1") is False
    assert inv.endpoints == ["HOST1"]


def test_add_user_replaces_on_change():
    inv = Investigation(name="c")
    assert inv.add_user("bob", AccountType.USER) is True
    assert inv.add_user("bob", AccountType.USER) is False
    assert inv.add_user("bob", AccountType.PRIVILEGED) is True
    assert inv.users["bob"] is AccountType.PRIVILEGED


def test_add_event_autocatalogs_endpoint_and_user():
    inv = Investigation(name="c")
    inv.add_event(make_event(endpoint="NEWHOST", username="carol",
                             account_type=AccountType.SERVICE))
    assert "NEWHOST" in inv.endpoints
    assert inv.users["carol"] is AccountType.SERVICE
