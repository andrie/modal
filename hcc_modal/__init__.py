__version__ = '0.1.0'

import hcc


def get_stations(parameter="level", qualifier = "Downstream Stage", river_name="River Thames"):
    if parameter == "flow":
        qualifier = None
    key = f"stations-{river_name}-{parameter}-{qualifier}"
    try:
        stations = app.dict[key]
    except:
        stations = hcc.ea_rivers.get_stations(river_name=river_name, parameter=parameter, qualifier=qualifier)
        try:
            app.dict[key] = stations
        except:
            pass
    stations = hcc.ea_rivers.get_stations(river_name=river_name, parameter=parameter, qualifier=qualifier)
    return stations


def get_station_id(search, parameter="level", qualifier = "Downstream Stage", river_name="River Thames"):
    stations = get_stations(parameter=parameter, qualifier=qualifier, river_name=river_name)
    labels = stations["label"].values
    low_labels = stations['label'].str.lower().values
    search = search.lower()
    matching_indices = [i for i, label in enumerate(low_labels) if search in label]
    if matching_indices:
        idx = matching_indices[0]  # Use the first matching index
        name = labels[idx]
        if parameter == "level":
            measures = stations.loc[idx, ["measures"]]
            m = [x['@id'] for x in measures.iloc[0] if x['unitName'] == 'mASD']
        else:
            measures = stations.loc[idx, ["measures"]]['measures']
            m = [x['@id'] for x in measures if x['unitName'] == 'm3/s']
        return name, m[0]
    else:
        return None, None  # Return None if no match was found


def get_metric(search, parameter="level", qualifier="Downstream Stage", river_name="River Thames", since = None, limit = 7*24*4):
    name, id = get_station_id(search, parameter=parameter, qualifier=qualifier, river_name=river_name)
    if since is None:
        z = hcc.ea_rivers.get_readings_for_measure(id, limit = limit)
    else:
        z = hcc.ea_rivers.get_readings_for_measure(id, since = since)
    return z[['dateTime', 'value']]