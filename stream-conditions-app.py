import pathlib
import pandas as pd
import re

from modal import Image, Period, Stub, Volume, web_endpoint, Dict

stub = Stub("river-conditions")
stub.dict = Dict.new()

conditions_image = (
    Image.debian_slim()
    .apt_install("git")
    .pip_install("pandas", "lxml", "sqlite-utils")
    .pip_install_from_requirements("requirements.txt")
    .pip_install("git+https://github.com/andrie/thames_river_conditions.git")
    # .pip_install("poetry")
    # .run("poetry install git+https://github.com/andrie/thames_river_conditions.git")
    # .pip_install_from_pyproject("https://github.com/andrie/thames_river_conditions.git")
)

volume = Volume.persisted("river-conditions-volume")

VOLUME_DIR = "/cache-vol"
# REPORTS_DIR = pathlib.Path(VOLUME_DIR, "COVID-19")
DB_PATH = pathlib.Path(VOLUME_DIR, "river-conditions.db")


with conditions_image.imports():
    import hcc
    import hcc.ea_rivers
    import hcc.sunrise






@stub.function(
    image   = conditions_image,
    volumes = {VOLUME_DIR: volume},
    schedule = Period(days=1),
    # asgi_app=asgi_app,
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


@stub.function(
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



@stub.function(
    image   = conditions_image,
    volumes = {VOLUME_DIR: volume}
)
@web_endpoint(label="thames-sunrise")
def sunrise_times():
    # import hcc.sunrise as hcc
    events = hcc.sunrise_times()
    return events.to_dict(orient="records")



@stub.function(
    image   = conditions_image,
    volumes = {VOLUME_DIR: volume}
)
def update_stations_dict():
    get_stations()
    return "Updated stations"



def get_stations(parameter="level", qualifier = "Downstream Stage", river_name="River Thames"):
    if parameter == "flow":
        qualifier = None
    key = f"stations-{river_name}-{parameter}-{qualifier}"
    try:
        stations = stub.dict[key]
    except:
        stations = hcc.ea_rivers.get_stations(river_name=river_name, parameter=parameter, qualifier=qualifier)
        stub.dict[key] = stations
    return stations

def get_station_id(search, parameter="level", qualifier = "Downstream Stage", river_name="River Thames"):
    stations = get_stations(parameter=parameter, qualifier=qualifier, river_name=river_name)
    idx = stations["label"].str.contains(search, na = False)
    name = stations.loc[idx, ["label"]].values[0][0]
    measures = stations.loc[idx, ["measures"]]
    m = [x['@id'] for x in measures.values[0][0] if x['unitName'] == 'mASD']

    url = stations.loc[idx, "@id"].values[0]
    return name, m[0]


def get_metric(search, parameter="level", qualifier="Downstream Stage", river_name="River Thames", since = None, limit = 7*24*4):
    # stations = get_stations(parameter=parameter, qualifier=qualifier, river_name=river_name)
    name, id = get_station_id(search, parameter=parameter, qualifier=qualifier, river_name=river_name)
    print(id)
    print(name)
    if since is None:
        z = hcc.ea_rivers.get_readings_for_measure(id, limit = limit)
    else:
        z = hcc.ea_rivers.get_readings_for_measure(id, since = since)
    return z[['dateTime', 'value']]



@stub.function(
    image   = conditions_image,
    volumes = {VOLUME_DIR: volume}
)
@web_endpoint(label="thames-water-level")
def lock_level(station, parameter="level", qualifier="Downstream Stage"):
    import hcc

    name, id = get_station_id(station, parameter=parameter, qualifier=qualifier)

    key_data = f"data-{name}-{parameter}-{qualifier}"
    key_time = f"time-{name}-{parameter}-{qualifier}"

    print(f"Using key {key_data}")
    # check if dict value exists and is older than 15 minutes
    try:
        last_time = pd.Timestamp(stub.dict[key_time])
        if pd.Timestamp.now() - last_time < pd.Timedelta(minutes=15):
            try:
                v_data = stub.dict[key_data]
                print("Using cached data")
                return v_data
            except KeyError:
                pass
    except KeyError:
        pass

    try:
        print("Fetching new data")
        z = get_metric(name, parameter = parameter, qualifier=qualifier)
        # extract only the datetime and value columns from z
    except Exception as e:
        print(f"Error: {e} ")
        z = [{"Error": f"{station} not found"},{f"Error": f"{e}"}]
        return z

    v_data = z[["dateTime", "value"]]
    stub.dict[key_data] = v_data.to_dict(orient="records")
    stub.dict[key_time] = pd.Timestamp.now().isoformat()
           
    return v_data.to_dict(orient="records")


@stub.local_entrypoint()
def run():
    update_conditions_db.remote()
    update_stations_dict.remote()
    return "Updated conditions"

if __name__ == "__main__":
    print(run())
    # import hcc
    # print(hcc.scrape_conditions())