"""Large deterministic MOCK inputs exercise real selection/export code, never science.

The store subclass exists only in tests. Neither DATA_MODE=real nor the regular
mock scenario factory can select the QA-only CSV as NASA observations.
"""
import hashlib
import io
import json
from collections import defaultdict
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError, REPO_ROOT
from app.errors import api_error
from app.main import create_app
from app.schemas import Envelope, SourceInfo, TimeSeries
from app.services.csv_codec import read_export
from app.services.csv_export import SERIES_COLUMNS
from app.services.store import MockStore
from scripts.generate_load_fixture import ALTERNATE_SOURCE, OUTPUT, build_fixture, generate

WINDOWS = [('2003-01', '2012-12'), ('2013-01', '2022-12'), ('2023-01', '2024-12')]
SELECTIONS = [('IGP', 'rainfall'), ('IGP', 'aod'), ('TN', 'rainfall'), ('TN', 'aod')]


class LargeDailyMockStore(MockStore):
    """Test-only adapter: normal metadata/results plus eagerly validated QA daily input."""
    def __init__(self, filename='daily.csv'):
        super().__init__(REPO_ROOT / 'data/mock/normal')
        self.fixture = filename
        raw = (OUTPUT / filename).read_bytes()
        manifest = json.loads((OUTPUT / 'manifest.json').read_text())
        assert manifest['data_status'] == 'mock'
        assert manifest['data_version'] == self.info.data_version
        entry = manifest['result'] if filename == 'daily.csv' else manifest['result']['sparse']
        assert hashlib.sha256(raw).hexdigest() == entry['csv_sha256']
        parsed = read_export(raw)
        assert parsed.metadata['data_status'] == 'mock'
        grouped = defaultdict(list)
        for row in parsed.rows:
            grouped[(row['region_id'], row['variable'], row['source_id'])].append(row)
        self.daily = {}
        for key, rows in grouped.items():
            rid, variable, source_id = key
            self.daily[key] = TimeSeries(region_id=rid, variable=variable, source_id=source_id,
                frequency='day', unit=rows[0]['unit'], points=[
                    {k: row[k] for k in ('date', 'value', 'valid_fraction', 'qc_flag')} for row in rows])
        assert len(parsed.rows) == entry['rows']
        assert len(self.daily) == len(entry['series'])

    def variables(self):
        return [v.model_copy(update={'sources': [*v.sources, ALTERNATE_SOURCE]})
                if v.variable == 'aod' else v.model_copy(deep=True) for v in super().variables()]

    def sources(self):
        return [*(s.model_copy(deep=True) for s in super().sources()), SourceInfo(
            source_id=ALTERNATE_SOURCE, product='MOCK secondary AOD input for QA only',
            short_name='MOCK QA alternate', version='MOCK', doi=None,
            access_method='MOCK generated fixture', access_date=None, variable_name='MOCK aod', citation=None)]

    def asset_statuses(self):
        return {**super().asset_statuses(), f'qa_large/{self.fixture}': 'mock'}

    def series_for_source(self, region_id, variable, frequency, source_id):
        series = self.daily.get((region_id, variable, source_id)) if frequency == 'day' else None
        if series is None:
            raise api_error('DATA_NOT_AVAILABLE', 'MOCK QA series unavailable.', {'dataset': 'timeseries'})
        return series.model_copy(deep=True)

    def series(self, region_id, variable, frequency):
        if frequency != 'day':
            return super().series(region_id, variable, frequency)
        primary = next((s for (r, v, _), s in self.daily.items()
                        if r == region_id and v == variable), None)
        if primary is None:
            raise api_error('DATA_NOT_AVAILABLE', 'MOCK QA series unavailable.', {'dataset': 'timeseries'})
        return primary.model_copy(deep=True)


@pytest.fixture(scope='module')
def large_store():
    return LargeDailyMockStore()


@pytest.fixture
def large_client(large_store, make_settings):
    with TestClient(create_app(make_settings(), store=large_store)) as client:
        yield client


def test_committed_fixture_matches_generator_and_hashes(tmp_path):
    generated = build_fixture()
    assert generate(check=True) == 48216
    for name, payload in generated.items():
        assert (OUTPUT / name).read_bytes() == payload
    generate(tmp_path)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == generated
    assert build_fixture() == generated


def test_fixture_is_six_full_daily_series_with_leap_days_and_qc_states(large_store):
    assert sum(len(s.points) for s in large_store.daily.values()) == 48216
    for series in large_store.daily.values():
        assert len(series.points) == 8036
        assert series.points[0].date == date(2003, 1, 1)
        assert series.points[-1].date == date(2024, 12, 31)
        assert sum(p.date.month == 2 and p.date.day == 29 for p in series.points) == 6
        assert {p.qc_flag for p in series.points} == {'missing', 'ok', 'suspect', 'low_coverage'}
        assert all(p.valid_fraction is None for p in series.points)
        assert any(p.value == 0.0 and p.qc_flag == 'ok' for p in series.points)
        assert all(p.qc_flag == 'missing' for p in series.points if p.value is None)


@pytest.mark.parametrize('window', WINDOWS)
@pytest.mark.parametrize('region,variable', SELECTIONS)
def test_daily_api_window_preserves_every_value(large_client, large_store, region, variable, window):
    start, end = window
    response = large_client.get('/api/v1/timeseries', params=dict(
        region_id=region, variable=variable, frequency='day', start=start, end=end))
    assert response.status_code == 200
    actual = Envelope[TimeSeries].model_validate(response.json())
    assert actual.data_status == 'mock'
    expected = [p for p in large_store.series(region, variable, 'day').points
                if start <= p.date.strftime('%Y-%m') <= end]
    assert actual.result.points == expected


@pytest.mark.parametrize('window', WINDOWS)
@pytest.mark.parametrize('region,variable', SELECTIONS)
def test_daily_csv_matches_api_exactly(large_client, region, variable, window):
    params = dict(region_id=region, variable=variable, frequency='day', start=window[0], end=window[1])
    api = large_client.get('/api/v1/timeseries', params=params).json()['result']
    response = large_client.get('/api/v1/export/csv', params={**params, 'what': 'series'})
    assert response.status_code == 200
    decoded = read_export(response.content)
    assert decoded.columns == SERIES_COLUMNS
    assert decoded.metadata['data_status'] == 'mock'
    assert 'MOCK' in response.text.splitlines()[0]
    assert len(decoded.rows) == len(api['points'])
    for row, point in zip(decoded.rows, api['points']):
        assert {name: row[name] for name in point} == point
        assert all(row[name] == api[name] for name in ('region_id', 'variable', 'source_id', 'frequency', 'unit'))
    frame = pd.read_csv(io.BytesIO(response.content), comment='#')
    assert list(frame.columns) == SERIES_COLUMNS
    assert len(frame) == len(api['points'])
    missing = [point['value'] is None for point in api['points']]
    assert frame['value'].isna().tolist() == missing
    assert frame['valid_fraction'].isna().all()
    assert frame.loc[frame['qc_flag'] == 'missing', 'value'].isna().all()
    assert (frame['value'] == 0).sum() == sum(point['value'] == 0 for point in api['points'])


@pytest.mark.parametrize('region', ['IGP', 'TN'])
def test_alternate_source_selection_is_distinct_and_defensively_copied(large_client, large_store, region):
    response = large_client.get('/api/v1/timeseries', params=dict(region_id=region, variable='aod',
        frequency='day', start='2024-01', end='2024-12', source_id=ALTERNATE_SOURCE))
    assert response.status_code == 200
    result = Envelope[TimeSeries].model_validate(response.json()).result
    assert result.source_id == ALTERNATE_SOURCE
    assert len(result.points) == 366
    primary = large_store.series(region, 'aod', 'day')
    alternate = large_store.series_for_source(region, 'aod', 'day', ALTERNATE_SOURCE)
    assert primary.points[1].value != alternate.points[1].value
    alternate.points.clear()
    assert len(large_store.series_for_source(region, 'aod', 'day', ALTERNATE_SOURCE).points) == 8036


def test_full_daily_record_still_requires_a_ten_year_window(large_client):
    response = large_client.get('/api/v1/timeseries', params=dict(region_id='IGP', variable='aod', frequency='day'))
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'INVALID_PERIOD'


def test_mock_qa_store_is_rejected_in_production(large_store, make_settings):
    with pytest.raises(ConfigError):
        with TestClient(create_app(make_settings(APP_ENV='prod', DATA_MODE='real'), store=large_store)):
            pass


def test_generator_never_writes_in_processed_or_unrelated_repo_paths():
    for output in [REPO_ROOT / 'data/processed', REPO_ROOT / 'docs']:
        with pytest.raises(ValueError, match='restricted'):
            generate(output)
