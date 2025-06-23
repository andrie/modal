import pathlib
import pandas as pd
import re

from modal import Image, Period, App, Mount, Volume, fastapi_endpoint, Dict, Secret

app = App("hcc-modal")
app_dict = Dict.from_name("hcc-modal-dict", create_if_missing=True)

minimal_image = (
    Image.debian_slim()
    .pip_install('pandas', 'requests')
)

conditions_image = (
    Image.debian_slim()
    .apt_install("git")
    .pip_install("pandas", "requests", "openai", "pydantic")
    .pip_install("git+https://github.com/andrie/thames_river_conditions.git") #, force_build=True)
    .pip_install("git+https://github.com/cpsievert/chatlas") #, force_build=True)
    .pip_install_from_requirements("requirements.txt") #, force_build=True)
    .add_local_file('./system_prompt.md', '/system_prompt.md')
)



@app.function(
    image   = minimal_image,
)
@fastapi_endpoint(label="conditions")
def conditions(metric = "flow", station = "walton"):
    metric = metric.lower()
    station = station.lower()

    if metric == 'hcc_terse':
        return app_dict["hcc_terse"]

    if metric == 'hcc_summary':
        return app_dict["hcc_summary"]

    if metric == 'hcc_all':
        return app_dict["hcc_all"]
    
    if metric == 'ai_guidance':
        return app_dict['ai_guidance']


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

    # save weather forecast
    try:
        api_key = os.environ["MET_OFFICE_API_KEY"]
    except KeyError as e:
        app_dict['weather'] = {"Error": "Invalid API key"}
        # return({"Error": f"{e}"})

    try:
        # type = 'hourly'
        type = 'three-hourly'
        w_data = hcc.metoffice.get_weather(51.41, -0.36, type = type, api_key = api_key)

        v_data = w_data.to_json(orient='columns')
    except KeyError as e:
        v_data = 'Error in fetching weather report'
    app_dict['weather'] = v_data

    update_hcc_dict()
    # Generate chatbot summary

    # try:
    #     guidance = get_gpt_summary()
    # except Exception as e:
    #     import datetime
    #     now = datetime.datetime.now()
    #     guidance = f'Unable to generate AI guidance summary at {now}: {e}'
    #     app_dict['ai_guidance'] = guidance

    guidance = get_gpt_summary.remote()
    app_dict['ai_guidance'] = guidance
    # print('Dictionary udpated with AI guidance')
    # print(guidance)

    return True

def get_water_temperature():
    url = "https://dl1.findlays.net/show/temp/thames1"
    try:
        import requests
        from bs4 import BeautifulSoup
        page = requests.get(url)
        soup = BeautifulSoup(page.content, 'html.parser')
    except Exception as e:
        print(f"Error fetching water temperature data: {e}")
        return 'NA'

    lines = soup.body.text.split('\n')  # split by line break
    for line in lines: 
        if "River temperature now:" in line: # if this text is found in the line
            return line.replace("C", "").split(': ')[1] # extract and return the value
    print('Error fetching water temperature: no water temperature found')

    return 'NA'




def get_hcc_conditions(conditions):
    '''
    Get current conditions of river temperature, conditions and weather at Hampton Canoe Club.

    Parameters:

    foo: not used

    '''
    # url = "https://andrie--conditions.modal.run?metric=hcc_terse"
    # try:
    #     import requests
    #     response = requests.get(url)
    #     conditions = response.json()
    try:
        # conditions = app_dict['hcc_terse']
        weatherString = conditions['weather']

        from io import StringIO
        import pandas as pd
        weather = pd.read_json(StringIO(weatherString)).head(8)
        weather['temperature'] = (weather['minScreenAirTemp'] + weather['maxScreenAirTemp']) / 2
        weather['windSpeed10m'] *= 3.6
        weather['windGustSpeed10m'] *= 3.6
        weather[['time', 'description', 'temperature', 'windSpeed10m', 'windGustSpeed10m', 
                    'probOfRain', 'probOfHeavyRain', 'probOfSnow', 'probOfHail', 'totalPrecipAmount']]
        conditions['weather'] = weather.to_json()
    except Exception as e:
        print('Error in calling to modal')
        return f'Error: {e}'
    return conditions


@app.function(
    image = conditions_image,
    secrets = [Secret.from_name("MET-OFFICE")]
)
def get_gpt_summary():
    from chatlas import ChatOpenAI
    import os
    import json

    print("get_gpt_summary triggered")

    try:
        api_key = os.environ["OPENAI_API_KEY"]
    except KeyError as e:
        print(f'Error in OpenAI key: {e}')

    try:
        with open('/system_prompt.md', 'r') as f:
            system_prompt = f.read()
            conditions = app_dict['hcc_terse']
            conditions = get_hcc_conditions(conditions)
            system_prompt += '\n\n' + json.dumps(conditions)
    except Exception as e:
        print(f'Error in creating system prompt: {e}')

    chat = ChatOpenAI(
        model="gpt-4o-mini",
        system_prompt = system_prompt,
        api_key = api_key
    )

    # chat.register_tool(get_hcc_conditions, model=NoFields)

    # try:
    resp = chat.chat("What are the conditions at Hampton Canoe Club?", echo='none')
    guidance = resp.content
    print(guidance)
    # except Exception as e:
    #     guidance = f'Unable to get response from chatbot, with error code {e}'
    
    return guidance


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
    sunrise = hcc.sunrise_times().to_dict(orient='records')
    app_dict['sunrise'] = sunrise


    # cache lock board conditions
    new = hcc.scrape_conditions()
    new.rename(columns={'Current conditions': 'condition'}, inplace=True)
    new.rename(columns={'From': 'from'}, inplace=True)
    new.rename(columns={'To': 'to'}, inplace=True)
    boards = new[42:45].to_dict(orient='records')
    app_dict['lockboard'] = boards

    # cache water temperature
    water_temperature = get_water_temperature()
    app_dict['water_temperature'] = water_temperature

    update_hcc_dict()

    return True

def update_hcc_dict():
    import datetime
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    terse = {
        'updated':       timestamp,
        'water_temp':    app_dict['water_temperature'],
        'sunrise':       app_dict['sunrise'],
        'flow_latest':   app_dict['flow_walton'][-1]['value'],
        'boards':        app_dict['lockboard'],
        'weather':       app_dict['weather'],
    }
    app_dict['hcc_terse'] = terse

    summary = {
        'updated_at':    timestamp,
        'water_temp':    app_dict['water_temperature'],
        'sunrise':       app_dict['sunrise'],
        'flow_walton':   app_dict['flow_walton'],
        'level_sunbury': app_dict['level_sunbury'],
        'boards':        app_dict['lockboard'],
        'weather':       app_dict['weather'],
    }
    app_dict['hcc_summary'] = summary

    summary.update({
        'flow_kingston': app_dict['flow_kingston'],
        'level_molesey': app_dict['level_molesey'],
    })
    app_dict['hcc_all'] = summary
    return True



@app.local_entrypoint()
def run():
    guidance = get_gpt_summary.remote()
    cache_flow.remote()
    cache_weather.remote()
    return(guidance)
    # return "Updated flow and weather"

if __name__ == "__main__":
    print(run())