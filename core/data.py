"""Presentation facade. Reuse the existing cached loader without changing any data logic."""
from dashboard.data import load as load_bundle


def load_nasa(bundle):
    """NASA frames retain their existing adapted schema and units."""
    return {name: bundle[name] for name in ('catalog', 'benthic', 'spatial')}


def load_noaa(bundle):
    """NOAA remains independent from NASA filters and historical period maxima."""
    return {name: bundle[name] for name in ('noaa', 'pixels', 'source', 'regional')}
