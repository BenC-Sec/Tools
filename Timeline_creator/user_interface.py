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

import ipywidgets as widgets
import os
import json
from IPython.display import display
from datetime import datetime
from dataframe_creation import *
from utils import *
from plot_creation import *


logger = setup_logger("event_log.log")

# Creates dropdown widget and submit button
# User inputs investigation name
# Creates json file with that name if it doesn't exist already.
def create_investigation_json() -> None:

    investigation_name_input = widgets.Text(
        description="Investigation Name:",
        placeholder="Enter investigation name",
        layout=widgets.Layout(width="400px"),
        style={"description_width": "auto"},
    )

    submit_button = widgets.Button(
        description="Submit",
        button_style="success",
    )

    def create_json_file(investigation_name) -> None:
        json_file_name: str = f"{investigation_name}.json"

        try:
            if not os.path.exists(json_file_name):
                # Define the initial structure of the JSON file
                json_data = {
                    "header": {
                        "endpoints": [],
                        "users": {},
                    },
                    "events": [],
                }

                with open(json_file_name, "w") as json_file:
                    json.dump(json_data, json_file, indent=4)
                logger.info(f"Investigation file created:\n{json_file_name}")
                print(f"JSON file '{json_file_name}' created successfully.")
            else:
                logger.warning(
                    f"File '{json_file_name}' already exists. Please use another name."
                )
                print(f"File '{json_file_name}' already exists use another name")

        except Exception as e:
            logger.error(f"An error occurred while creating the JSON file: {str(e)}")
            print(f"Error: {str(e)}")

    def on_submit_button_clicked(b) -> None:
        investigation_name = investigation_name_input.value.strip()
        if investigation_name:
            create_json_file(investigation_name)
        else:
            print("Please enter a valid investigation name.")

    submit_button.on_click(on_submit_button_clicked)
    display(investigation_name_input, submit_button)


# Creates dropdown widgets and submit button
# User inputs endpoint names
# Adds endpoint names to JSON file
def add_endpoint_to_investigation() -> None:

    def submit_endpoint(change) -> None:
        if investigation_dropdown.value:
            file_name: str = investigation_dropdown.value
            endpoint: str = endpoint_input.value

            data = load_json_file(file_name)

            if endpoint and endpoint not in data["header"]["endpoints"]:
                data["header"]["endpoints"].append(endpoint)
                save_json_file(file_name, data)
                print(f"Endpoint '{endpoint}' added to '{file_name}'.")
            else:
                print("Endpoint is either empty or already exists.")

    investigation_dropdown = widgets.Dropdown(
        options=list_json_files(),
        description="Investigation:",
        disabled=False,
        style={"description_width": "auto"}
    )

    endpoint_input = widgets.Text(description="Endpoint:", placeholder="Enter endpoint")
    submit_button = widgets.Button(
        description="Submit",
        button_style="success",
    )

    submit_button.on_click(submit_endpoint)
    display(investigation_dropdown, endpoint_input, submit_button)


# Creates dropdown widgets and submit button
# User inputs usernames and account types
# Adds usernames and account types to JSON file
def add_user_to_investigation() -> None:

    def submit_user(change) -> None:
        if investigation_dropdown.value:
            file_name = investigation_dropdown.value
            username = username_input.value
            account_type = account_type_dropdown.value

            data = load_json_file(file_name)

            if username and account_type:
                data["header"]["users"][username] = account_type
                save_json_file(file_name, data)
                print(
                    f"User '{username}' with account type '{account_type}' added to '{file_name}'."
                )
            else:
                print("Username or account type cannot be empty.")

    investigation_dropdown = widgets.Dropdown(
        options=list_json_files(),
        description="Investigation:",
        disabled=False,
        style={"description_width": "auto"}
    )

    # EDR although not technically an account type is an option for the user during investigations
    username_input = widgets.Text(description="Username:", placeholder="Enter username")
    account_type_dropdown = widgets.Dropdown(
        options=[
            "Guest account",
            "User account",
            "Privileged account",
            "Service account",
            "System account",
            "EDR",
            "Unknown",
        ],
        description="Account Type:",
        disabled=False,
        style={"description_width": "auto"}
    )

    submit_button = widgets.Button(
        description="Submit",
        button_style="success",
    )

    submit_button.on_click(submit_user)
    display(
        investigation_dropdown, username_input, account_type_dropdown, submit_button
    )


# Creates dropdown widgets and submit button
# User selects previously added endpoints and usernames
# User adds a description and start time with optional end time
# Adds event to the JSON file
def add_event_to_investigation() -> None:
    """User selects json file via dropdown, user and account type from dropdown, enters a description,
    start time and optional end time via a checkbox. The event is written to the json
    """

    # called in the method so that any new files are detected
    json_files = list_json_files()

    investigation_dropdown = widgets.Dropdown(
        options=json_files,
        description="Investigation:",
        disabled=False,
        value=(json_files[0] if json_files else None),
        style={"description_width": "auto"}
    )

    endpoint_dropdown = widgets.Dropdown(
        description="Endpoint:",
        disabled=False,
    )

    user_dropdown = widgets.Dropdown(
        description="User:",
        disabled=False,
    )

    description_input = widgets.Text(
        description="Description:", placeholder="Enter event description"
    )

    start_date_picker = widgets.DatePicker(
        description="Start Date:",
        disabled=False,
    )

    start_time_picker = widgets.TimePicker(
        description="Start Time:",
        disabled=False,
    )

    end_date_picker = widgets.DatePicker(
        description="End Date:",
        disabled=False,
    )

    end_time_picker = widgets.TimePicker(
        description="End Time:",
        disabled=False,
    )

    end_time_checkbox = widgets.Checkbox(
        value=False,
        description="Add End Time",
        disabled=False,
    )

    submit_button = widgets.Button(description="Submit", button_style="success")

    display(
        investigation_dropdown,
        endpoint_dropdown,
        user_dropdown,
        description_input,
        widgets.HBox([start_date_picker, start_time_picker]),
        end_time_checkbox,
        widgets.HBox([end_date_picker, end_time_picker]),
        submit_button,
    )

    def update_dropdowns(change=None) -> None:
        if investigation_dropdown.value:
            investigation = load_json_file(investigation_dropdown.value)

            endpoint_dropdown.options = []
            user_dropdown.options = []

            endpoint_dropdown.options = get_endpoints(investigation)
            user_dropdown.options = [
                (user.strip())  # Display and store the full string
                for user in get_users(investigation)
            ]

    # Checks all fields have been completed and valid
    # Creates an event in the json file
    def submit_event(change) -> None:
        if all(
            [
                investigation_dropdown.value,
                endpoint_dropdown.value,
                user_dropdown.value,
                description_input.value,
                start_date_picker.value,
                start_time_picker.value,
            ]
        ):
            file_name = investigation_dropdown.value
            endpoint = endpoint_dropdown.value
            selected_value = user_dropdown.value
            username, account_type = selected_value.split(" (")  # type: ignore
            account_type = account_type.rstrip(")")
            description = description_input.value
            start_date = start_date_picker.value
            start_time = start_time_picker.value
            end_time = end_time_picker.value if end_time_checkbox.value else ""

            if start_date is None or start_time is None:
                logger.warning("Start date and/or time is missing.")
                print("Please select both start date and time.")
                return
            else:
                start_datetime = datetime.combine(start_date, start_time)
                logger.info(f"Start datetime created: {start_datetime}")

            if end_time_checkbox.value:
                end_date = end_date_picker.value
                end_time = end_time_picker.value
                if end_date is None or end_time is None:
                    logger.warning("End date and/or time is missing.")
                    print("Please select both end date and time.")
                    return
                end_datetime = datetime.combine(end_date, end_time)
            else:
                end_datetime = ""

            print(f"Start: {start_datetime}, End: {end_datetime}")

            data = load_json_file(file_name)

            event = {
                "username": username,  # Use the extracted username
                "account_type": account_type,
                "endpoint": endpoint,
                "start": start_datetime.isoformat(),
                "end": (end_datetime.isoformat() if end_time else ""),  # type: ignore
                "description": description,
            }

            data["events"].append(event)
            save_json_file(file_name, data)
            logger.info(f"Event added to '{file_name}'.")
            print(f"Event added to '{file_name}'.")
        else:
            print("Please fill in all required fields.")

    if json_files:
        update_dropdowns()

    investigation_dropdown.observe(update_dropdowns, names="value")

    submit_button.on_click(submit_event)


def filter_and_display() -> None:

    json_files = list_json_files()

    investigation_dropdown = widgets.Dropdown(
        options=json_files,
        description="Investigation:",
        disabled=False,
        value=(json_files[0] if json_files else None),
        style={"description_width": "auto"}
    )

    endpoints_listbox = widgets.SelectMultiple(
        description="Endpoints:",
        disabled=False,
    )

    selected_endpoints_box = widgets.SelectMultiple(
        description="Selected endpoints:",
        disabled=False,
        style={"description_width": "auto"}
    )

    users_listbox = widgets.SelectMultiple(
        description="Users:",
        disabled=False,
    )

    selected_users_box = widgets.SelectMultiple(
        description="Selected Users:",
        disabled=False,
        style={"description_width": "auto"}
    )

    start_date_picker = widgets.DatePicker(
        description="Start Date:",
        disabled=False,
    )

    start_time_picker = widgets.TimePicker(
        description="Start Time:",
        disabled=False,
    )

    end_date_picker = widgets.DatePicker(
        description="End Date:",
        disabled=False,
    )

    end_time_picker = widgets.TimePicker(
        description="End Time:",
        disabled=False,
    )

    submit_button = widgets.Button(description="Submit", button_style="success")

    endpoint_move_button = widgets.Button(description="Move >>")
    endpoint_remove_button = widgets.Button(description="<< Move")

    user_move_button = widgets.Button(description="Move >>")
    user_remove_button = widgets.Button(description="<< Move")

    display(
        investigation_dropdown,
        endpoints_listbox,
        endpoint_move_button,
        endpoint_remove_button,
        selected_endpoints_box,
        users_listbox,
        user_move_button,
        user_remove_button,
        selected_users_box,
        widgets.HBox([start_date_picker, start_time_picker]),
        widgets.HBox([end_date_picker, end_time_picker]),
        submit_button,
    )

    def update_dropdowns(change=None) -> None:
        if investigation_dropdown.value:
            investigation = load_json_file(investigation_dropdown.value)

            endpoints_listbox.options = []
            users_listbox.options = []
            selected_endpoints_box.options = []
            selected_users_box.options = []

            endpoints_listbox.options = get_endpoints(investigation)
            users_listbox.options = [
                (user.strip()) for user in get_users(investigation)
            ]

    # Action on moving endpoint, move to selected endpoints box, remove from existing endpoints list
    def on_move_button_click_endpoints(b):
        """Transfer an endpoint from the endpoint list to the list of selected endpoints."""
        selected_endpoints = list(endpoints_listbox.value)

        for endpoint in selected_endpoints:
            if endpoint not in selected_endpoints_box.options:
                selected_endpoints_box.options = tuple(
                    list(selected_endpoints_box.options) + [endpoint]
                )
        existing_endpoints = [endpoint for endpoint in endpoints_listbox.options]
        endpoints_listbox.options = ()
        endpoints_listbox.options = tuple(
            [u for u in existing_endpoints if u not in selected_endpoints_box.options]
        )

    # Action on removing endpoint, move to endpoints box, remove from selected endpoints list
    def on_remove_button_click_endpoints(b) -> None:
        """Transfer a user from the selected users back to the list of users."""
        selected_endpoints = list(selected_endpoints_box.value)

        # Filter out endpoints that are already in the endpoint_listbox
        new_endpoints = [
            endpoint
            for endpoint in selected_endpoints
            if endpoint not in endpoints_listbox.options
        ]

        if new_endpoints:
            endpoints_listbox.options = list(endpoints_listbox.options) + new_endpoints

            selected_endpoints_box.options = [
                endpoint
                for endpoint in selected_endpoints_box.options
                if endpoint not in new_endpoints
            ]

    # Action on moving user, move to selected user box, remove from existing user list
    def on_move_button_click_users(b) -> None:
        """Transfer a user from the user list to the list of selected users."""
        selected_users = list(users_listbox.value)

        for user in selected_users:
            if user not in selected_users_box.options:
                selected_users_box.options = tuple(
                    list(selected_users_box.options) + [user]
                )

        existing_users = [user for user in users_listbox.options]
        users_listbox.options = ()
        users_listbox.options = tuple(
            [u for u in existing_users if u not in selected_users_box.options]
        )

    # Action on removing user, move to user box, remove from selected user list
    def on_remove_button_click_users(b) -> None:
        """Transfer a user from the selected users back to the list of users."""
        selected_users = list(selected_users_box.value)

        # Filter out users that are already in the users_listbox
        new_users = [
            user for user in selected_users if user not in users_listbox.options
        ]

        if new_users:
            users_listbox.options = list(users_listbox.options) + new_users

            selected_users_box.options = [
                user for user in selected_users_box.options if user not in new_users
            ]

    # When user clicks submit button check all fields have been completed and are valid, then create a dataframe, apply readability functions before using IBM timeline generator to display timeline
    def on_submit_button_clicked(b):
        """Calls methods to create a dataframe of the selected investigation then filter it to the selected endpoints and users and display graph"""
        if all(
            [
                investigation_dropdown.value,
                selected_endpoints_box.options,
                selected_users_box.options,
                start_date_picker.value,
                start_time_picker.value,
                end_date_picker.value,
                end_time_picker.value,
                are_dates_correct(
                    start_date_picker.value,
                    start_time_picker.value,
                    end_date_picker.value,
                    end_time_picker.value,
                ),
            ]
        ):

            file_name = investigation_dropdown.value
            # remove JSON from filename for image labelling
            base_file_name = os.path.splitext(str(file_name))[0]
            selected_endpoints = selected_endpoints_box.options
            selected_users = [
                user_entry.split(" (")[0] for user_entry in selected_users_box.options
            ]
            logger.info(f"Selected users:\n{selected_users}")
            start_datetime = datetime.combine(
                start_date_picker.value, start_time_picker.value
            )
            end_datetime = datetime.combine(
                end_date_picker.value, end_time_picker.value
            )

            # Using a dataframe manager apply each of the user selected filters
            investigation_dataframe: DataFrameManager = create_dataframe(file_name)
            investigation_dataframe.filter_by_time_range(start_datetime, end_datetime)
            investigation_dataframe.filter_by_endpoints(selected_endpoints)
            investigation_dataframe.filter_by_users(selected_users)

            # Add height for readability on graph
            investigation_dataframe.add_height_column()
            investigation_dataframe.assign_colors()

            plot_manager = PlotManager()
            plot_manager.create_plot(
                data=investigation_dataframe.get_dataframe(),
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                base_filename=base_file_name,
            )

        else:
            print("Please fill in all required fields ensuring times are correct.")
            logger.warning("User clicked timeline display with incomplete inputs.")

    # Trigger the update immediately to load data on initial display
    update_dropdowns(None)

    # If user changes investigation dropdown then re-populate
    investigation_dropdown.observe(update_dropdowns, names="value")

    # Action on user moving endpoints
    endpoint_move_button.on_click(on_move_button_click_endpoints)
    endpoint_remove_button.on_click(on_remove_button_click_endpoints)

    # Action on user moving users
    user_move_button.on_click(on_move_button_click_users)
    user_remove_button.on_click(on_remove_button_click_users)

    # Action on user clicking submit
    submit_button.on_click(on_submit_button_clicked)
