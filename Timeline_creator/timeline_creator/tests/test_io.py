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

import json

from timeline_creator import io
from timeline_creator.models import AccountType, Event, Investigation
from .conftest import make_event, sample_investigation, utc


def test_round_trip_equal(tmp_path):
    inv = sample_investigation()
    io.save(inv, tmp_path)
    result = io.load(inv.name, tmp_path)
    assert result.warnings == []
    assert result.investigation.model_dump() == inv.model_dump()


def test_span_decomposed_into_two_records(tmp_path):
    inv = Investigation(name="c")
    inv.add_event(make_event(message="span", dt=utc(2025, 1, 1, 1),
                             end=utc(2025, 1, 1, 2), span_id="s1"))
    io.save(inv, tmp_path)
    lines = [json.loads(l) for l in (tmp_path / "c.jsonl").read_text().splitlines()]
    assert len(lines) == 2
    assert [r["timestamp_desc"] for r in lines] == ["Start", "End"]
    assert all(r["span_id"] == "s1" for r in lines)


def test_point_event_single_record(tmp_path):
    inv = Investigation(name="c")
    inv.add_event(make_event(message="point"))
    io.save(inv, tmp_path)
    lines = [json.loads(l) for l in (tmp_path / "c.jsonl").read_text().splitlines()]
    assert len(lines) == 1
    assert lines[0]["timestamp_desc"] == "Event"
    assert "span_id" not in lines[0]


def test_synthesised_span_id_when_missing(tmp_path):
    inv = Investigation(name="c")
    inv.add_event(make_event(end=utc(2025, 1, 1, 13)))  # no span_id
    io.save(inv, tmp_path)
    lines = [json.loads(l) for l in (tmp_path / "c.jsonl").read_text().splitlines()]
    assert lines[0]["span_id"] == "span-0"


def test_orphan_start_promoted_to_point(tmp_path):
    (tmp_path / "c.jsonl").write_text(json.dumps({
        "datetime": "2025-01-01T01:00:00+00:00", "timestamp_desc": "Start",
        "span_id": "s1", "message": "half span", "endpoint": "H",
        "username": "u", "account_type": "User account",
    }) + "\n")
    result = io.load("c", tmp_path)
    assert len(result.investigation.events) == 1
    assert result.investigation.events[0].is_span is False
    assert any("Start but no End" in w for w in result.warnings)


def test_meta_sidecar_contents(tmp_path):
    inv = sample_investigation()
    io.save(inv, tmp_path)
    meta = json.loads((tmp_path / f"{inv.name}.meta.json").read_text())
    assert meta["name"] == inv.name
    assert "HOST1" in meta["endpoints"]
    assert meta["users"]["root"] == "Privileged account"
    assert meta["schema_version"] == 1


def test_load_without_sidecar_derives_catalogues(tmp_path):
    inv = sample_investigation()
    io.save(inv, tmp_path)
    (tmp_path / f"{inv.name}.meta.json").unlink()
    result = io.load(inv.name, tmp_path)
    assert "HOST1" in result.investigation.endpoints
    assert "root" in result.investigation.users
    assert any("No metadata sidecar" in w for w in result.warnings)


def test_list_investigations(tmp_path):
    io.save(Investigation(name="bravo"), tmp_path)
    io.save(Investigation(name="alpha"), tmp_path)
    assert io.list_investigations(tmp_path) == ["alpha", "bravo"]


def test_event_order_preserved_with_mixed_points_and_spans(tmp_path):
    inv = Investigation(name="c")
    inv.add_event(make_event(message="first", dt=utc(2025, 1, 1, 1)))
    inv.add_event(make_event(message="span", dt=utc(2025, 1, 1, 2),
                             end=utc(2025, 1, 1, 3), span_id="s1"))
    inv.add_event(make_event(message="third", dt=utc(2025, 1, 1, 4)))
    io.save(inv, tmp_path)
    result = io.load("c", tmp_path)
    assert [e.message for e in result.investigation.events] == ["first", "span", "third"]
