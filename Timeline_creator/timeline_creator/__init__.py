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

"""Timeline Creator — build and visualise DFIR investigation timelines.

Layered package (see timeline_tool_scratchpad.md, decisions D1-D23):

  models      pydantic validation gate (Event, Investigation, AccountType)
  io          on-disk JSONL + meta sidecar (Timesketch-aligned)
  importers   CSV / xlsx bulk import
  filters     endpoint / user / time-window filtering
  colour      account-type -> hue family, username -> shade/marker (symbolic)
  layout      PURE pixel-aware label deconfliction
  render      matplotlib rendering + SVG/PNG export (needs matplotlib)
  app         thin ipywidgets notebook UI (needs ipywidgets)

The core (models, io, importers, filters, colour, layout) is pure Python with
no pandas / matplotlib / ipywidgets dependency, so it is unit-testable in
isolation. Only `render` and `app` pull in the heavy GUI/plotting stack.
"""

from .models import AccountType, Event, Investigation

SCHEMA_VERSION = 1

__all__ = ["AccountType", "Event", "Investigation", "SCHEMA_VERSION"]
