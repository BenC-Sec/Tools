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

"""Shared pytest fixtures/helpers for the pure-core test suite."""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the package importable when tests are run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from timeline_creator.models import AccountType, Event, Investigation  # noqa: E402


def utc(year, month, day, hour=0, minute=0, second=0):
    """Convenience: build a tz-aware UTC datetime."""
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def make_event(message="evt", endpoint="HOST1", username="alice",
               account_type=AccountType.USER, dt=None, end=None, span_id=None):
    return Event(
        datetime=dt or utc(2025, 1, 1, 12, 0, 0),
        message=message,
        endpoint=endpoint,
        username=username,
        account_type=account_type,
        end=end,
        span_id=span_id,
    )


def sample_investigation():
    inv = Investigation(name="case-1")
    inv.add_event(make_event(message="login", dt=utc(2025, 1, 1, 9, 0, 0)))
    inv.add_event(make_event(message="priv esc", username="root",
                             account_type=AccountType.PRIVILEGED,
                             dt=utc(2025, 1, 1, 9, 5, 0)))
    inv.add_event(make_event(message="exfil window", endpoint="HOST2",
                             dt=utc(2025, 1, 1, 10, 0, 0),
                             end=utc(2025, 1, 1, 11, 0, 0), span_id="s1"))
    return inv
