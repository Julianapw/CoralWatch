import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from dashboard import data
from dashboard.ui import PAGES

PAGE_FILES = ['pages/1_Overview.py', 'pages/2_Reef_Composition.py', 'pages/3_Environmental_Monitoring.py', 'pages/4_Early_Warning.py']

ROOT = Path(__file__).resolve().parents[1]
PAGE_PATHS = [str(ROOT / path) for path in PAGE_FILES]


def app_test():
    # Keep the test entrypoint outside pages/: AppTest resets Streamlit's legacy
    # pages-directory detection on every rerun. Run the real entrypoint unchanged.
    script = f"import runpy; runpy.run_path({str(ROOT / 'app.py')!r}, run_name='__main__')"
    return AppTest.from_string(script, default_timeout=30).run()


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        data._read.clear()

    def tearDown(self):
        self.temp.cleanup()

    def csv(self, name, rows):
        pd.DataFrame(rows).to_csv(self.folder / name, index=False)

    def nasa(self):
        self.csv('flight_catalog.csv', [dict(flight_line='F1', source_file='f.nc', region='Reef', observation_date='2016-09-01', latitude_min=-15, latitude_max=-14, longitude_min=145, longitude_max=146)])
        self.csv('benthic_variable_summary.csv', [dict(flight_line='F1', source_file='f.nc', variable=v, mean=m, units='unitless', valid_count=10) for v, m in [('coral', .4), ('algae', .3), ('sand', .3)]])
        (self.folder / 'dashboard_config.json').write_text(json.dumps({'probability_note': 'per-pixel probabilities from 0 to 1'}))
        self.csv('spatial_observations.csv', [dict(source_file='f.nc', variable='coral', value=.4, units='unitless', latitude=-14.5, longitude=145.5)])

    def regional(self):
        self.csv('noaa_daily_summary.csv', [dict(region=r, date=d, SST_mean=28, HOTSPOT_mean=.2, DHW_mean=2, DHW_max=3, BAA_max=b) for r, d, b in [('F1', '2026-11-01', 4), ('F1', '2026-11-02', 1), ('F2', '2026-11-01', 2)]])
        self.csv('noaa_spatial_summary.csv', [dict(region='F1', BAA_max=4, DHW_max=99, latitude_min=-15, latitude_max=-14, longitude_min=145, longitude_max=146)])

    def test_regional_priority_and_latest_dates(self):
        self.regional()
        self.csv('noaa_thermal_timeseries.csv', [dict(date='2026-11-03', baa_7d_max=4)])
        bundle = data.load(self.folder)
        self.assertEqual(bundle['source'], 'noaa_daily_summary.csv')
        latest = data.latest_by_region(bundle['noaa']).set_index('region')
        self.assertEqual(latest.loc['F1', 'baa'], 1)
        self.assertEqual(latest.loc['F2', 'date'], pd.Timestamp('2026-11-01'))
        self.assertEqual(latest.loc['F1', 'dhw_max'], 3)
        self.assertEqual(len(bundle['noaa']), 3)

    def test_original_and_invalid_dates(self):
        self.csv('noaa_thermal_timeseries.csv', [dict(date='bad', sst_c_mean=28, baa_7d_max=2), dict(date='2026-01-01', sst_c_mean=-9999, dhw_celsius_weeks_max=5, baa_7d_max=7)])
        b = data.load(self.folder)
        self.assertFalse(b['regional'])
        self.assertEqual(len(b['noaa']), 1)
        self.assertTrue(pd.isna(b['noaa'].sst_mean.iloc[0]))
        self.assertEqual(b['noaa'].baa.iloc[0], 7)
        self.assertTrue(any('datas inválidas' in x for x in b['messages']))

    def test_empty_missing_and_cache_change(self):
        (self.folder / 'noaa_daily_summary.csv').write_text('')
        self.assertTrue(data.load(self.folder)['noaa'].empty)
        self.csv('noaa_daily_summary.csv', [dict(region='F1', date='2026-01-01', BAA_max=None)])
        self.assertEqual(len(data.load(self.folder)['noaa']), 1)
        self.csv('benthic_variable_summary.csv', [dict(unrelated=1)])
        self.assertTrue(data.load(self.folder)['benthic'].empty)

    def test_historical_not_current(self):
        self.csv('integrated_regional_summary.csv', [dict(flight_line='F1', nasa_region='Reef', nasa_observation_date='2016-01-01', coral_mean=.4, BAA_max=4, DHW_max=99)])
        b = data.load(self.folder)
        self.assertTrue(b['noaa'].empty)
        self.assertTrue(b['pixels'].empty)
        self.assertFalse(b['catalog'].empty)

    def test_units_and_composition(self):
        self.nasa()
        b = data.load(self.folder)
        self.assertAlmostEqual(b['benthic'].measure.iloc[0], 40)
        self.assertFalse(data.composition_valid(b['benthic'], b['catalog']))
        (self.folder / 'dashboard_config.json').write_text('{}')
        b = data.load(self.folder)
        self.assertAlmostEqual(b['benthic'].measure.iloc[0], .4)
        cat = b['catalog'].copy()
        cat['probability_sum_min'], cat['probability_sum_max'], cat['valid_benthic_pixels'] = 1., 1., 10
        d = b['benthic'].copy()
        d['measure'] = [40, 30, 30]
        d['unit_label'] = '% de probabilidade média'
        self.assertTrue(data.composition_valid(d, cat))
        d.loc[0, 'valid_count'] = 9
        self.assertFalse(data.composition_valid(d, cat))

    def test_coordinates_and_unknown_baa(self):
        self.csv('noaa_latest_map.csv', [dict(date='2026-11-01', latitude=-14, longitude=145, baa_7d_max=7), dict(date='2026-11-01', latitude=-9999, longitude=145, baa_7d_max=4), dict(date='2026-10-01', latitude=-14, longitude=145, baa_7d_max=4)])
        b = data.load(self.folder)
        self.assertEqual(len(b['pixels']), 1)
        self.assertEqual(b['pixels'].baa.iloc[0], 7)

    def test_metadata_missing_values_and_bad_json(self):
        self.nasa()
        self.csv('variable_inventory.csv', [dict(variable='coral', source_file='f.nc', valid_min=0, valid_max=1)])
        self.csv('spatial_observations.csv', [dict(source_file='f.nc', variable='coral', value=v, latitude=-14, longitude=145) for v in (.4, -9999, 2)])
        (self.folder / 'noaa_config.json').write_text('{broken')
        self.csv('noaa_daily_summary.csv', [dict(region='F1', date='2026-11-01', BAA_max=None)])
        b = data.load(self.folder)
        self.assertEqual(b['spatial'].value.notna().sum(), 1)
        self.assertTrue(pd.isna(data.latest_by_region(b['noaa']).baa.iloc[0]))
        self.assertTrue(any('noaa_config.json' in m for m in b['messages']))

    def test_pixel_only_pages(self):
        self.csv('noaa_latest_map.csv', [dict(date='2026-11-01', latitude=-14, longitude=145, baa_7d_max=3, sst_c=28)])
        self.assert_pages()

    def assert_pages(self):
        with patch.object(data, 'DATA_DIR', self.folder):
            at = app_test()
            for page in PAGE_PATHS:
                at.switch_page(page).run()
                self.assertEqual(len(at.exception), 0, [x.message for x in at.exception])
            return at

    def test_pages_no_sources(self):
        self.assert_pages()

    def test_pages_nasa_only(self):
        self.nasa()
        self.assert_pages()

    def test_pages_noaa_only(self):
        self.regional()
        self.assert_pages()

    def test_pages_both_and_empty_filters(self):
        self.nasa()
        self.regional()
        with patch.object(data, 'DATA_DIR', self.folder):
            at = app_test()
            before = at.metric[3].value
            at.sidebar.multiselect(key='nasa_flight_line').set_value([]).run()
            self.assertEqual(at.metric[3].value, before, 'Filtros NASA não podem alterar BAA NOAA')
            at.sidebar.multiselect(key='noaa_region').set_value([]).run()
            for page in PAGE_PATHS:
                at.switch_page(page).run()
                self.assertEqual(len(at.exception), 0, [x.message for x in at.exception])
        self.assert_pages()

    def test_original_pages_and_pixel_alerts(self):
        self.csv('noaa_thermal_timeseries.csv', [dict(date='2026-11-01', sst_c_mean=28, sst_anomaly_c_mean=.5, dhw_celsius_weeks_mean=3, hotspot_c_mean=.2, baa_7d_max=4)])
        self.csv('noaa_latest_map.csv', [dict(date='2026-11-01', latitude=-14, longitude=145, baa_7d_max=v, sst_c=28, hotspot_c=.2, dhw_celsius_weeks=3) for v in (0, 4, 7, None)])
        self.assert_pages()


if __name__ == '__main__':
    unittest.main()
