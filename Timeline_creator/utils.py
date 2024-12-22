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
import json
import logging
from typing import List
from datetime import datetime
from enum import Enum

class AccountTypeColours(Enum):
    PRIVILEGED_ACCOUNT = ['firebrick', 'darkred', 'indianred']
    EDR = ['midnightblue', 'navy', 'dodgerblue']
    SERVICE_ACCOUNT = ['darkgrey', 'dimgrey', 'lightgrey']
    SYSTEM_ACCOUNT = ['darkorange', 'coral', 'goldenrod']
    UNKNOWN = ['black']

class DistinctColours(Enum):
    FOREST_GREEN = 'forestgreen'
    LIME_GREEN = 'limegreen'
    GOLD = 'gold'
    YELLOW = 'yellow'
    DARK_VIOLET = 'darkviolet'
    MEDIUM_PURPLE = 'mediumpurple'
    ORCHID = 'orchid'
    HOT_PINK = 'hotpink'
    DEEP_PINK = 'deeppink'
    MAGENTA = 'magenta'

def list_json_files() -> List[str]:
    return [file for file in os.listdir(".") if file.endswith(".json")]

def load_json_file(file_name):
    with open(file_name, "r") as file:
        return json.load(file)

def save_json_file(file_name, data) -> None:
    with open(file_name, "w") as file:
        json.dump(data, file, indent=4)

def get_users(investigation) -> List[str]:
    return [
        f"{username} ({account_type})"
        for username, account_type in investigation["header"]["users"].items()
    ]

def get_endpoints(investigation):
    """Retrieve endpoints from the JSON file."""
    return investigation["header"]["endpoints"]

def are_dates_correct(start_date, start_time, end_date, end_time) -> bool:
    # Check for missing dates or times
    if not all([start_date, start_time, end_date, end_time]):
        print("Please select valid start and end dates and times.")
        return False

    start_datetime = datetime.combine(start_date, start_time)
    end_datetime = datetime.combine(end_date, end_time)

    if start_datetime >= end_datetime:
        print("Start time must be before end time.")
        return False

    return True

def setup_logger(log_file: str) -> logging.Logger:

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    return logger