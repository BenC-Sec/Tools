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


import pandas as pd
from utils import *


logger = logging.getLogger(__name__)

class DataFrameManager:
    def __init__(self, dataframe=None):
        self.dataframe = dataframe if dataframe is not None else pd.DataFrame()

    def add_row(self, data):
        self.dataframe = pd.concat([self.dataframe, pd.DataFrame([data])], ignore_index=True)

    def filter_rows(self, condition):
        self.dataframe = self.dataframe[condition]

    def filter_by_time_range(self, begin_time, end_time):

        self.dataframe['start'] = pd.to_datetime(self.dataframe['start'])
        self.dataframe['end'] = pd.to_datetime(self.dataframe['end'])

        self.dataframe = self.dataframe[
            ((self.dataframe['start'] >= begin_time) & (self.dataframe['start'] <= end_time)) |
            ((self.dataframe['start'] <= begin_time) & (self.dataframe['end'] >= begin_time))
        ]
        
        self.dataframe.loc[
            (self.dataframe['start'] < begin_time) & (self.dataframe['end'] >= begin_time),
            'start'
        ] = begin_time

        # sort by start time and reset indices
        self.dataframe = self.dataframe.sort_values(by='start', ascending=True)
        self.dataframe = self.dataframe.reset_index(drop=True)
        logger.info(f"Investigation filtered by time:\n{self.get_dataframe()}")

    def filter_by_endpoints(self, endpoints: list):
        # Filter the DataFrame to include only rows with specified endpoints
        self.dataframe = self.dataframe[self.dataframe['endpoint'].isin(endpoints)]

        # Reset the index after filtering by endpoints
        self.dataframe = self.dataframe.reset_index(drop=True)
        logger.info(f"Investigation filtered by time and endpoints:\n{self.get_dataframe()}")

    def filter_by_users(self, users: list):
        # Filter the DataFrame to include only rows with specified users
        self.dataframe = self.dataframe[self.dataframe['username'].isin(users)]

        # Reset the index after filtering by users
        self.dataframe = self.dataframe.reset_index(drop=True)
        logger.info(f"Investigation filtered by time, endpoints and users:\n{self.get_dataframe()}")

    def add_height_column(self):
        # Add a height column with values incrementing by 2 until 20, then reset to 0
        self.dataframe['height'] = [2 + (i * 2) % 20 for i in range(len(self.dataframe))]

    def assign_colors(self):

        account_type_colors = {
            "Privileged account": AccountTypeColours.PRIVILEGED_ACCOUNT.value.copy(), 
            "EDR": AccountTypeColours.EDR.value.copy(),
            "Service account": AccountTypeColours.SERVICE_ACCOUNT.value.copy(),
            "System account": AccountTypeColours.SYSTEM_ACCOUNT.value.copy(),
            "Unknown": AccountTypeColours.UNKNOWN.value.copy()
        }

        distinct_colors = [color.value for color in DistinctColours]
        user_colors = {}
        remaining_colors = distinct_colors.copy()

        # Assign colours based on username and account type
        for _, row in self.dataframe.iterrows():
            username = row['username']
            account_type = row['account_type']

            if username not in user_colors:
                if account_type in account_type_colors and account_type_colors[account_type]:
                    # Assign the next available colour for the account type
                    user_colors[username] = account_type_colors[account_type].pop(0)
                elif remaining_colors:
                    user_colors[username] = remaining_colors.pop(0)
                else:
                    # If no more colours are left, cycle back to the beginning
                    remaining_colors = distinct_colors.copy()
                    user_colors[username] = remaining_colors.pop(0)

        self.dataframe['options'] = self.dataframe['username'].apply(
            lambda username: {'color': user_colors[username]}
        )
        logger.info(f"Final dataframe:\n{self.get_dataframe()}")

    def get_dataframe(self):
        return self.dataframe
    

# Creates dataframe of all events in investigation 
def create_dataframe(investigation)  -> DataFrameManager:
    all_events = load_json_file(investigation)
    events_df = pd.DataFrame(all_events["events"])
    
    # Add additional columns required by timeline_generator
    events_df["height"] = 0
    events_df["options"] = [{} for _ in range(len(events_df))]
    
    # Create DataFrameManager for easier management of the DataFrame
    df_manager = DataFrameManager(events_df)
    
    # Log information about the DataFrame
    logger.info(f"Initial Investigation DataFrame unfiltered:\n{df_manager.get_dataframe()}")
    
    return df_manager  
