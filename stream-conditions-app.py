import pathlib
import pandas as pd
import re

from modal import Image, Period, App, Mount, Volume, web_endpoint, Dict, Secret

app = App("river-conditions")
app_dict = Dict.from_name("hcc", create_if_missing=True)

conditions_image = (
    Image.debian_slim()
    .apt_install("git")
    .pip_install("pandas", "lxml", "sqlite-utils")
    .pip_install_from_requirements("requirements.txt")#, force_build=True)
    .pip_install("git+https://github.com/andrie/thames_river_conditions.git") #, force_build=True)
    # .pip_install("poetry")
    # .run("poetry install git+https://github.com/andrie/thames_river_conditions.git")
    # .pip_install_from_pyproject("https://github.com/andrie/thames_river_conditions.git")
)

# volume = Volume.persisted("river-conditions-volume")
volume = Volume.from_name("river-conditions-volume")

VOLUME_DIR = "/cache-vol"
# REPORTS_DIR = pathlib.Path(VOLUME_DIR, "COVID-19")
DB_PATH = pathlib.Path(VOLUME_DIR, "river-conditions.db")



# @app.function(
#     mounts = [Mount.from_local_python_packages("hcc_modal")]
# )
with conditions_image.imports():
    import hcc
    import hcc.ea_rivers
    import hcc.sunrise
    import hcc.metoffice
    # from hcc_modal import get_metric, get_station_id, get_stations






@app.function(
    image   = conditions_image,
    volumes = {VOLUME_DIR: volume},
    schedule = Period(days=1),
)
def update_conditions_db():
    import sqlite_utils

    new = hcc.scrape_conditions()

    # Rename the 'Current conditions' column to 'condition'
    new.rename(columns={'Current conditions': 'condition'}, inplace=True)
    new.rename(columns={'From': 'from'}, inplace=True)
    new.rename(columns={'To': 'to'}, inplace=True)
    new.drop('Local', axis=1, inplace=True)


    print("Inserting new data into DB...")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite_utils.Database(DB_PATH)

    # Create the "conditions" table with the correct columns if it doesn't exist
    if "conditions" not in db.table_names():
        db["conditions"].create({
            "date": "text",
            "from": "text",
            "to": "text",
            "condition": "text"
        }, pk=("date", "from", "to"))

    table = db["conditions"]

    # insert new into db
    table.insert_all(new.to_dict(orient="records"), replace=True)
    table.create_index(["date", "from", "to"], unique=True, if_not_exists=True)

    print("Syncing DB with volume...")
    db.close()
    volume.commit()

    return None


@app.function(
    image   = conditions_image,
    volumes = {VOLUME_DIR: volume}
)
@web_endpoint(label="thames-conditions")
def api():
    import sqlite_utils
    db = sqlite_utils.Database(DB_PATH)
    table = db["conditions"]
    rows =  table.rows_where("date = (SELECT MAX(date) FROM conditions)")
    df = pd.DataFrame(rows)
    return df.to_dict(orient="records")



@app.function(
    image   = conditions_image,
    volumes = {VOLUME_DIR: volume}
)
@web_endpoint(label="thames-sunrise")
def sunrise_times():
    # import hcc.sunrise as hcc
    events = hcc.sunrise_times()
    return events.to_dict(orient="records")



@app.function(
    image   = conditions_image,
    volumes = {VOLUME_DIR: volume}
)
def update_stations_dict():
    get_stations()
    return "Updated stations"





@app.function(
    image   = conditions_image,
    mounts  = [Mount.from_local_python_packages("hcc_modal", "hcc_modal")],
    volumes = {VOLUME_DIR: volume},
)
@web_endpoint(label="flow")
def flow(station = "Walton"):
    import hcc_modal
    # get_metric = hcc.get_metric
    print("getting name")
    name, id = hcc_modal.get_station_id(station, parameter="flow")
    print(f"name: {name}")
    key_data = f"flow-data-{name}"
    key_time = f"flow-time-{name}"
    if is_valid_cache(key_time, timeout=15):
        try:
            v_data = get_cached_data(key_data)
            return v_data
        except KeyError:
            pass
    try:
        # print("trying to get data")
        v_data = hcc_modal.get_metric(name, parameter = "flow")
    except Exception as e:
        return({"Error": f"{e}"})
    set_cached_data(key_data, key_time, v_data.to_dict(orient="records"))
    return v_data.to_dict(orient="records")



@app.function(
    image   = conditions_image,
    volumes = {VOLUME_DIR: volume},
    secrets = [Secret.from_name("MET-OFFICE")]
)
@web_endpoint(label="weather")
def weather(type = "hourly"):
    import os
    try:
        api_key = os.environ["MET_OFFICE_API_KEY"]
    except KeyError as e:
        return({"Error": f"{e}"})
    key_data = f"weather-data-{type}"
    key_time = f"weather-time-{type}"
    if is_valid_cache(key_time, timeout=60):
        try:
            v_data = get_cached_data(key_data)
            return v_data
        except KeyError:
            pass
    try:
        v_data = hcc.metoffice.get_weather(51.41, -0.36, type = type, api_key = api_key)
    except Exception as e:
        return({"Error": f"{e}"})
    set_cached_data(key_data, key_time, v_data.to_json(orient="columns"))
    return v_data.to_json(orient="columns")


def is_valid_cache(key_time, timeout = 15):
    try:
        last_time = pd.Timestamp(app_dict[key_time])
    except:
        return False
    
    return pd.Timestamp.now() - last_time < pd.Timedelta(minutes=timeout)

def get_cached_data(key_data):
    try:
        v_data = app_dict[key_data]
        print("Using cached data")
        return v_data
    except KeyError:
        raise KeyError("No cached data")
    
def set_cached_data(key_data, key_time, v_data):
    app_dict[key_data] = v_data
    app_dict[key_time] = pd.Timestamp.now()
    return None



@app.function(
    image   = conditions_image,
    volumes = {VOLUME_DIR: volume},
    mounts=[Mount.from_local_python_packages("hcc_modal")],
)
@web_endpoint(label="thames-water-level")
def lock_level(station="Molesey", parameter="level", qualifier="Downstream Stage"):

    import hcc
    import hcc_modal
    # from hcc_modal import get_metric, get_station_id

    name, id = hcc_modal.get_station_id(station, parameter=parameter, qualifier=qualifier)

    key_data = f"data-{name}-{parameter}-{qualifier}"
    key_time = f"time-{name}-{parameter}-{qualifier}"

    print(f"Using key {key_data}")
    # check if dict value exists and is older than 15 minutes
    try:
        last_time = pd.Timestamp(app_dict[key_time])
        if pd.Timestamp.now() - last_time < pd.Timedelta(minutes=15):
            try:
                v_data = app_dict[key_data]
                print("Using cached data")
                return v_data
            except KeyError:
                pass
    except KeyError:
        pass

    try:
        print("Fetching new data")
        z = hcc_modal.get_metric(name, parameter = parameter, qualifier=qualifier)
        # extract only the datetime and value columns from z
    except Exception as e:
        print(f"Error: {e} ")
        z = [{"Error": f"{station} not found"},{f"Error": f"{e}"}]
        return z

    v_data = z[["dateTime", "value"]]
    app_dict[key_data] = v_data.to_dict(orient="records")
    app_dict[key_time] = pd.Timestamp.now().isoformat()
           
    return v_data.to_dict(orient="records")


@app.local_entrypoint()
def run():
    update_conditions_db.remote()
    update_stations_dict.remote()
    return "Updated conditions"

if __name__ == "__main__":
    print(run())
    # import hcc
    # print(hcc.scrape_conditions())