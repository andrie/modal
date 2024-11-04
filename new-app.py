import pathlib
import pandas as pd
import re

from modal import Image, Period, App, Mount, Volume, web_endpoint, Dict, Secret

app = App("hcc-modal")
app_dict = Dict.from_name("hcc-modal-dict", create_if_missing=True)

minimal_image = (
    Image.debian_slim()
    # .apt_install("git")
    .pip_install('pandas', 'requests')
    # .pip_install('requests')
)

conditions_image = (
    Image.debian_slim()
    .apt_install("git")
    .pip_install("pandas", "requests")
    .pip_install("git+https://github.com/andrie/thames_river_conditions.git", force_build=True)
    .pip_install_from_requirements("requirements.txt")#, force_build=True)
)



@app.function(
    image   = minimal_image,
)
@web_endpoint(label="conditions")
def conditions(metric = "flow", station = "walton"):
    metric = metric.lower()
    station = station.lower()

    if metric == 'flow':
        station = station.lower()
        flow = app_dict[f'flow_{station}']
        return flow
    
    if metric == 'level':
        station = station.lower()
        level = app_dict[f'level_{station}']
        return level
    
    if metric == 'sunrise':
        return app_dict['sunrise']
    
    if metric == 'boards':
        return app_dict['lockboard']

    if metric == 'weather':
        return app_dict['weather']
    
    return 'Unknown metric'


@app.function(
    image = conditions_image,
    schedule  = Period(hours=6),
    secrets = [Secret.from_name("MET-OFFICE")]
)
def cache_weather():
    import os
    import hcc.metoffice
    try:
        api_key = os.environ["MET_OFFICE_API_KEY"]
    except KeyError as e:
        app_dict['weather'] = {"Error": "Invalid API key"}
        return({"Error": f"{e}"})

    try:
        type = 'hourly'
        w_data = hcc.metoffice.get_weather(51.41, -0.36, type = type, api_key = api_key)
        v_data = w_data.to_json(orient='columns')
    except KeyError as e:
        v_data = 'Error in fetching weather report'
    app_dict['weather'] = v_data
    return True


@app.function(
    image = conditions_image,
    schedule = Period(hours=1)
)
def cache_flow():
    """
    Fetches and caches flow data for specified stations.

    This function retrieves flow data for a predefined set of stations from the
    Environment Agency's flood monitoring API. The data is fetched for the past
    week (4 readings per hour, 24 hours a day, for 7 days). The data is then
    sorted by date and time, and stored in the app_dict dictionary.

    The function uses the following stations and their corresponding URLs:
    - Kingston: https://environment.data.gov.uk/flood-monitoring/id/measures/3400TH-flow-water-i-15_min-m3_s
    - Walton: https://environment.data.gov.uk/flood-monitoring/id/measures/3100TH-flow--i-15_min-m3_s

    If no data is available for a station, "No flow data" is stored instead.

    Returns:
        bool: Always returns True.
    """
    import ea_rivers

    base_url = 'https://environment.data.gov.uk/flood-monitoring/id/measures'

    flow_url = {
        'kingston': f'{base_url}/3400TH-flow-water-i-15_min-m3_s',
        'walton':   f'{base_url}/3100TH-flow--i-15_min-m3_s'
    }
    
    for station, url in flow_url.items():
        flow = ea_rivers.get_readings_for_measure(url, limit = 4*24*7)
        if flow.empty:
            flow_dict = "No flow data"
        else:
            flow = flow.sort_values(by='dateTime', ascending=True)[['dateTime', 'value']]
            flow_dict = flow.to_dict(orient='records')
        app_dict[f'flow_{station}'] = flow_dict


    level_url = {
        'sunbury': f'{base_url}/3101TH-level-downstage-i-15_min-mASD',
        'molesey': f'{base_url}/3102TH-level-downstage-i-15_min-mASD'
    }
    
    for station, url in level_url.items():
        level = ea_rivers.get_readings_for_measure(url, limit = 4*24*7)
        if level.empty:
            level_dict = "No level data"
        else:
            level = level.sort_values(by='dateTime', ascending=True)[['dateTime', 'value']]
            level_dict = level.to_dict(orient='records')
        app_dict[f'level_{station}'] = level_dict


    # cache sunrise times
    import hcc
    app_dict['sunrise'] = hcc.sunrise_times().to_dict(orient='records')


    # cache lock board conditions
    new = hcc.scrape_conditions()
    new.rename(columns={'Current conditions': 'condition'}, inplace=True)
    new.rename(columns={'From': 'from'}, inplace=True)
    new.rename(columns={'To': 'to'}, inplace=True)
    app_dict['lockboard'] = new[42:45].to_dict(orient='records')

    return True


@app.local_entrypoint()
def run():
    cache_flow.remote()
    cache_weather.remote()
    return "Updated flow and weather"

if __name__ == "__main__":
    print(run())