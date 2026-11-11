
"""
Presentation facade for the CoralWatch dashboard data loader.

Keeps NASA and NOAA data accessible through separate functions,
while preserving the independent filtering logic of each source.
"""

from dashboard.data import load as load_bundle


def load_nasa(bundle):
    """
    Return the NASA datasets used by the dashboard.

    NASA data includes the flight catalog, benthic composition
    summaries and georeferenced spatial observations.
    """
    return {
        "catalog": bundle["catalog"],
        "benthic": bundle["benthic"],
        "spatial": bundle["spatial"],
    }


def load_noaa(bundle):
    """
    Return the NOAA datasets used by the dashboard.

    Includes recent daily observations, the latest pixel map,
    historical SST data for long-term trend analysis and
    metadata describing the selected source.
    """
    return {
        "noaa": bundle["noaa"],
        "pixels": bundle["pixels"],
        "history": bundle["history"],
        "source": bundle["source"],
        "regional": bundle["regional"],
    }
