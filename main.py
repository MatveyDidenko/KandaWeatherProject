from dweather_client.http_queries import get_metadata, get_heads
from dweather_client.aliases_and_units import \
    lookup_station_alias, STATION_UNITS_LOOKUP as SUL, METRIC_TO_IMPERIAL as M2I, IMPERIAL_TO_METRIC as I2M, UNIT_ALIASES
from dweather_client.struct_utils import tupleify, convert_nans_to_none
import datetime, pytz, csv, inspect
from astropy import units as u
import numpy as np
import pandas as pd
from timezonefinder import TimezoneFinder
from dweather_client import gridded_datasets
from dweather_client.storms_datasets import IbtracsDataset, AtcfDataset, SimulatedStormsDataset
from dweather_client.ipfs_queries import StationDataset, YieldDatasets, AemoPowerDataset, AemoGasDataset, AesoPowerDataset
from dweather_client.ipfs_errors import *
import ipfshttpclient

# Gets all gridded dataset classes from the datasets module
GRIDDED_DATASETS = {
    obj.dataset: obj for obj in vars(gridded_datasets).values()
    if inspect.isclass(obj) and type(obj.dataset) == str
}

def get_gridcell_history(
        lat,
        lon,
        dataset,
        also_return_snapped_coordinates=False,
        also_return_metadata=False,
        use_imperial_units=True,
        convert_to_local_time=True,
        ipfs_timeout=None):
    """
    Get the historical timeseries data for a gridded dataset in a dictionary
    This is a dictionary of dates/datetimes: climate values for a given dataset and
    lat, lon.
    also_return_metadata is set to False by default, but if set to True,
    returns the metadata next to the dict within a tuple.
    use_imperial_units is set to True by default, but if set to False,
    will get the appropriate metric unit from aliases_and_units
    """
    try:
        metadata = get_metadata(get_heads()[dataset])
    except KeyError:
        raise DatasetError("No such dataset in dClimate")

    # set up units
    str_u = metadata['unit of measurement']
    with u.imperial.enable():
        dweather_unit = UNIT_ALIASES[str_u] if str_u in UNIT_ALIASES else u.Unit(str_u)
    converter = None
    # if imperial is desired and dweather_unit is metric
    if use_imperial_units and (dweather_unit in M2I):
        converter = M2I[dweather_unit]
    # if metric is desired and dweather_unit is imperial
    elif (not use_imperial_units) and (dweather_unit in I2M):
        converter = I2M[dweather_unit]

    # get dataset-specific "no observation" value
    missing_value = metadata["missing value"]

    try:
        dataset_obj = GRIDDED_DATASETS[dataset](ipfs_timeout=ipfs_timeout)
    except KeyError:
        raise DatasetError("No such dataset in dClimate")

    try:
        (lat, lon), resp_series = dataset_obj.get_data(lat, lon)

    except (ipfshttpclient.exceptions.ErrorResponse, ipfshttpclient.exceptions.TimeoutError, KeyError, FileNotFoundError) as e:
        raise CoordinateNotFoundError("Invalid coordinate for dataset")

    # try a timezone-based transformation on the times in case we're using an hourly set.
    if convert_to_local_time:
        try:
            tf = TimezoneFinder()
            local_tz = pytz.timezone(tf.timezone_at(lng=lon, lat=lat))
            resp_series = resp_series.tz_localize("UTC").tz_convert(local_tz)
        except (AttributeError, TypeError):  # datetime.date (daily sets) doesn't work with this, only datetime.datetime (hourly sets)
            pass

    if type(missing_value) == str:
        resp_series = resp_series.replace(missing_value, np.NaN).astype(float)
    else:
        resp_series.loc[resp_series.astype(float) == missing_value] = np.NaN
        resp_series = resp_series.astype(float)

    resp_series = resp_series * dweather_unit
    if converter is not None:
        resp_series = pd.Series(converter(resp_series.values), resp_series.index)
    result = {k: convert_nans_to_none(v) for k, v in resp_series.to_dict().items()}

    if also_return_metadata:
        result = tupleify(result) + ({"metadata": metadata},)
    if also_return_snapped_coordinates:
        result = tupleify(result) + ({"snapped to": (lat, lon)},)
    return result


print(get_gridcell_history(42, -72, "prismc-tmax-daily"))
