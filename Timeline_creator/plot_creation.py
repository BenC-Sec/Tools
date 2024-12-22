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

# Author BenC https://github.com/BenC-Sec/Tools 

import os
from datetime import timedelta
from utils import *
from timeline_generator import *


logger = logging.getLogger(__name__)

class PlotManager:
    plot_counter = 0  
    last_filename_base = None 

    def __init__(self):
        self.ax = None

    def create_plot(self, data, start_datetime, end_datetime, base_filename):
        # Reset the counter if the filename base changes
        if base_filename != PlotManager.last_filename_base:
            PlotManager.plot_counter = 0
            PlotManager.last_filename_base = base_filename

        # Generate unique filename
        while True:
            PlotManager.plot_counter += 1
            proposed_filename = f"{base_filename}-{PlotManager.plot_counter}.png"
            if not os.path.exists(proposed_filename):
                break

        if (end_datetime - start_datetime) > timedelta(hours=36):
            dateformat = '%A, %d %B'
            interval = 24
        else:
            dateformat="%b %d %H:%M"
            interval = 1


        self.ax = get_timeline(
            data=data,
            start=start_datetime,
            end=end_datetime,
            interval=interval,
            dateformat=dateformat,
            filename=proposed_filename
        )
        print("Plot: ", proposed_filename)
        logger.info(f"Generating plot with unique file name: {proposed_filename}")