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

import importlib.util
from datetime import timezone

import pytest

from timeline_creator import importers
from timeline_creator.importers import ImportError_, parse_csv
from timeline_creator.models import AccountType

HEADER = "datetime,message,endpoint,username,account_type"


def test_valid_csv_commits():
    csv = HEADER + "\n" + "2025-01-01T09:00:00+00:00,login,HOST1,alice,User account\n"
    result = parse_csv(csv)
    assert result.ok
    assert len(result.events) == 1
    assert result.events[0].message == "login"
    assert result.discovered_endpoints == ["HOST1"]
    assert result.discovered_users == {"alice": AccountType.USER}


def test_naive_datetime_assumed_utc():
    csv = HEADER + "\n" + "2025-01-01 09:00:00,login,HOST1,alice,User account\n"
    result = parse_csv(csv)
    assert result.ok
    assert result.events[0].datetime.tzinfo == timezone.utc
    assert result.events[0].datetime.hour == 9


def test_naive_rejected_when_assume_utc_false():
    csv = HEADER + "\n" + "2025-01-01 09:00:00,login,HOST1,alice,User account\n"
    result = parse_csv(csv, assume_utc=False)
    assert not result.ok
    assert "naive" in result.errors[0].message


def test_all_or_nothing_one_bad_row_blocks_batch():
    csv = (HEADER + "\n"
           + "2025-01-01T09:00:00+00:00,good,HOST1,alice,User account\n"
           + "not-a-date,bad,HOST1,bob,User account\n")
    result = parse_csv(csv)
    assert not result.ok
    assert result.events == []  # nothing committed
    assert result.errors[0].row == 2


def test_aggregates_multiple_row_errors():
    csv = (HEADER + "\n"
           + "not-a-date,a,HOST1,alice,User account\n"
           + "2025-01-01T09:00:00+00:00,b,HOST1,bob,Bogus type\n")
    result = parse_csv(csv)
    assert len(result.errors) == 2
    assert {e.row for e in result.errors} == {1, 2}


def test_missing_required_column_is_batch_error():
    csv = "datetime,message,endpoint,username\n2025-01-01T09:00:00+00:00,a,H,u\n"
    with pytest.raises(ImportError_):
        parse_csv(csv)


def test_missing_required_value_is_row_error():
    csv = HEADER + "\n" + "2025-01-01T09:00:00+00:00,,HOST1,alice,User account\n"
    result = parse_csv(csv)
    assert not result.ok
    assert "message" in result.errors[0].message


def test_span_via_end_column():
    csv = (HEADER + ",end\n"
           + "2025-01-01T09:00:00+00:00,window,HOST1,alice,User account,2025-01-01T10:00:00+00:00\n")
    result = parse_csv(csv)
    assert result.ok
    assert result.events[0].is_span


def test_end_before_start_row_error():
    csv = (HEADER + ",end\n"
           + "2025-01-01T10:00:00+00:00,window,HOST1,alice,User account,2025-01-01T09:00:00+00:00\n")
    result = parse_csv(csv)
    assert not result.ok


def test_header_aliases_and_casing():
    csv = "Date,Description,Host,User,account_type\n2025-01-01T09:00:00+00:00,login,HOST1,alice,user\n"
    result = parse_csv(csv)
    assert result.ok
    assert result.events[0].message == "login"


def test_blank_lines_skipped():
    csv = HEADER + "\n\n2025-01-01T09:00:00+00:00,login,HOST1,alice,User account\n\n"
    result = parse_csv(csv)
    assert result.ok
    assert len(result.events) == 1


@pytest.mark.skipif(importlib.util.find_spec("openpyxl") is None,
                    reason="openpyxl not installed in this dev env")
def test_xlsx_round_trips_basic():
    import io as _io
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["datetime", "message", "endpoint", "username", "account_type"])
    ws.append(["2025-01-01T09:00:00+00:00", "login", "HOST1", "alice", "User account"])
    buf = _io.BytesIO()
    wb.save(buf)
    result = importers.parse_xlsx(buf.getvalue())
    assert result.ok
    assert result.events[0].message == "login"
