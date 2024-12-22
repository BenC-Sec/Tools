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

# Original code can be found at https://github.com/IBM/timeline-generator

import logging
import textwrap
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Patch

logger = logging.getLogger(__name__)

def get_timeline(data, start=None, end=None,
                 granularity='hours', interval=24, ylim=None, dateformat='%a %b %d', fig_height=8, fig_width=14, filename=None):

    data['start_datetime'] = pd.to_datetime(data.start, format='mixed')
    data['end_datetime'] = pd.to_datetime(data.end, format='mixed')

    offset_args = {}
    offset_args[granularity] = interval
    if not start:
        start_datetime = min(data.start_datetime) - \
            pd.DateOffset(**offset_args)
    else:
        start_datetime = pd.to_datetime(start)
    if not end:
        end_datetime = max(max(data.start_datetime), max(
            data.end_datetime)) + pd.DateOffset(**offset_args)
    else:
        end_datetime = pd.to_datetime(end)

    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=300)
    ax.set_xlim([start_datetime, end_datetime]) # type: ignore
    if not ylim:
        ax.set_ylim(0,1 + data[
            ((data.start_datetime >= start_datetime) & (data.start_datetime <= end_datetime)) | 
            (pd.notnull(data.end_datetime) & (data.end_datetime >= start_datetime) & (data.end_datetime <= end_datetime))
            ].height.max())
    else:
        ax.set_ylim(0,ylim)

    data['options'] = data.apply(lambda row: set_defaults(row.options), axis=1)
    data_options = pd.DataFrame([x for x in data.options])
    data = data.combine_first(data_options)
    data = data.where(pd.notnull(data), None)

    spans = data[data.end_datetime.notnull()]
    if spans.shape[0] > 0:
        ax.hlines(spans.height, spans.start_datetime, spans.end_datetime,
                  linewidth=spans.linewidth, capstyle='round', alpha=spans.alpha,
                  color=spans.color)
    milestones = data[data.end_datetime.isnull()]
    vlines = milestones[milestones.vline == True]
    plots = milestones[milestones.marker == True]
    for index, row in plots.iterrows():
        ax.plot(row.start_datetime, row.height, row.markerfmt,
                color=row.color, markerfacecolor=row.color)
    ax.vlines(vlines.start_datetime, 0, vlines.height,
              color=vlines.color, linewidth=0.5)
    data.apply(lambda row: annotate(ax, row), axis=1)

    # Added to create a legend
    unique_colors = data[['username', 'color', 'account_type']].drop_duplicates()
    legend_handles = [
        Patch(color=row['color'], label=f"{row['username']} ({row['account_type']})")
        for _, row in unique_colors.iterrows()
    ]
    ax.legend(handles=legend_handles, title='Usernames', loc='center left', bbox_to_anchor=(-0.2, 0.5), fontsize=8)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_position('zero')
    ax.get_yaxis().set_ticks([])
    dtFmt = mdates.DateFormatter(dateformat)
    ax.xaxis.set_major_formatter(dtFmt)
    if granularity == 'minutes':
        ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=interval))
    elif granularity == 'hours':
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=interval))
    elif granularity == 'weeks':
        ax.xaxis.set_major_locator(mdates.WeekLocator(interval=interval))  # type: ignore
    elif granularity == 'months':
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=interval)) 
    else:
        print("invalid granularity")
    ax.tick_params(axis="x", labelsize=8)
    fig.autofmt_xdate()
    if (filename):
        plt.savefig(filename, bbox_inches='tight')
    return ax

def set_defaults(options):
    defaults = {
        'text_wrap': 50,
        'x_offset': 10,
        'y_offset': 5,
        'arrowprops': None,
        'annotation_anchor': 'left',
        'horizontalalignment': 'left',
        'color': 'darkblue',
        'textcolor': 'black',
        'alpha': 1,
        'linewidth': 20,
        'vline': True,
        'marker': True,
        'markerfmt': 'o',
        'placement':'right'
    }
    result = defaults
    for option in options:
        result[option] = options[option]
    return result


def annotate(ax, row):
    description = "\n".join(textwrap.wrap(
        row.description, width=row['text_wrap']))
    
    anchor = row['start_datetime']
    
    if pd.notna(row['end_datetime']):  
        row['horizontalalignment'] = 'left'  # Align text to the left of the start time
        row['x_offset'] = 20  # Move annotation 20 units to the right of the start time
    else:
        if row['placement'] == 'left':
            row['horizontalalignment'] = 'right'
            row['x_offset'] = -10
        else:
            row['horizontalalignment'] = 'left'
            row['x_offset'] = 10

    # Added as was getting float issues
    if pd.isna(row['arrowprops']):
        row['arrowprops'] = None  
    elif isinstance(row['arrowprops'], dict) == False:
        row['arrowprops'] = {}

    ax.annotate(
        description, xy=(anchor, row.height),
        xytext=(row.x_offset, row.y_offset), 
        textcoords="offset points",
        horizontalalignment=row.horizontalalignment,
        verticalalignment="top",
        color=row.textcolor,
        arrowprops=row.arrowprops
    )

