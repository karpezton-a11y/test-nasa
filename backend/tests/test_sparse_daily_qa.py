"""Missing-data acceptance cases complement the existing high-coverage fixture."""
from datetime import date
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError
from app.main import create_app
from app.reports.charts import gap_arrays
from app.schemas import Envelope, TimeSeries
from scripts.generate_load_fixture import ALTERNATE_SOURCE, OUTPUT, generate
from test_large_daily_csv import LargeDailyMockStore, SELECTIONS, WINDOWS


@pytest.fixture(scope='module')
def sparse_store():
    return LargeDailyMockStore('sparse_daily.csv')


@pytest.fixture
def sparse_client(sparse_store, make_settings):
    with TestClient(create_app(make_settings(), store=sparse_store)) as client:
        yield client


def test_sparse_fixture_has_four_validated_full_records(sparse_store):
    manifest = json.loads((OUTPUT / 'manifest.json').read_text())
    assert manifest['data_status'] == 'mock'
    assert manifest['result']['sparse']['rows'] == 32144
    assert len(sparse_store.daily) == 4
    for series in sparse_store.daily.values():
        assert len(series.points) == 8036
        assert 0.4 < sum(p.value is None for p in series.points) / len(series.points) < 0.5
        assert any(p.value == 0.0 and p.qc_flag == 'ok' for p in series.points)
        assert all(p.qc_flag == 'missing' for p in series.points if p.value is None)
        assert all(p.valid_fraction is None for p in series.points)


@pytest.mark.parametrize('window', WINDOWS)
@pytest.mark.parametrize('region,variable', SELECTIONS)
def test_raw_api_retains_sparse_values_and_all_slots(sparse_client, sparse_store, region, variable, window):
    response = sparse_client.get('/api/v1/timeseries', params=dict(
        region_id=region, variable=variable, frequency='day', start=window[0], end=window[1]))
    assert response.status_code == 200
    envelope = Envelope[TimeSeries].model_validate(response.json())
    assert envelope.data_status == 'mock'
    expected = [p for p in sparse_store.series(region, variable, 'day').points
                if window[0] <= p.date.strftime('%Y-%m') <= window[1]]
    assert envelope.result.points == expected
    assert any(p.value is None for p in envelope.result.points)
    assert any(p.value == 0.0 for p in envelope.result.points)


@pytest.mark.parametrize('window', WINDOWS)
@pytest.mark.parametrize('region,variable', SELECTIONS)
def test_sparse_csv_is_a_json_quality_error_not_a_partial_download(sparse_client, region, variable, window):
    response = sparse_client.get('/api/v1/export/csv', params=dict(
        region_id=region, variable=variable, frequency='day', what='series', start=window[0], end=window[1]))
    assert response.status_code == 422
    assert response.headers['content-type'].startswith('application/json')
    assert 'Content-Disposition' not in response.headers
    error = response.json()['error']
    assert error['code'] == 'INSUFFICIENT_DATA'
    assert error['details']['valid_pct'] < 70
    assert error['details']['n_valid'] < error['details']['n_expected']


@pytest.mark.parametrize('region,variable', SELECTIONS)
def test_complete_outage_is_returned_as_nulls_and_chart_gaps(sparse_client, region, variable):
    response = sparse_client.get('/api/v1/timeseries', params=dict(
        region_id=region, variable=variable, frequency='day', start='2020-01', end='2021-12'))
    assert response.status_code == 200
    series = Envelope[TimeSeries].model_validate(response.json()).result
    assert len(series.points) == 731
    assert series.points[0].date == date(2020, 1, 1)
    assert series.points[-1].date == date(2021, 12, 31)
    assert all(p.value is None and p.qc_flag == 'missing' for p in series.points)
    dates, values = gap_arrays(series)
    assert len(dates) == 731 and np.isnan(values).all()


def test_outage_csv_reports_zero_valid_observations(sparse_client):
    response = sparse_client.get('/api/v1/export/csv', params=dict(
        region_id='IGP', variable='aod', frequency='day', start='2020-01', end='2021-12'))
    error = response.json()['error']
    assert response.status_code == 422 and error['code'] == 'INSUFFICIENT_DATA'
    assert error['details']['n_valid'] == 0 and error['details']['n_expected'] == 731


def test_unavailable_alternate_source_never_falls_back(sparse_client):
    response = sparse_client.get('/api/v1/timeseries', params=dict(region_id='IGP', variable='aod',
        frequency='day', start='2024-01', end='2024-12', source_id=ALTERNATE_SOURCE))
    assert response.status_code == 404
    assert response.json()['error']['code'] == 'DATA_NOT_AVAILABLE'


def test_full_record_still_obeys_daily_request_limit(sparse_client):
    response = sparse_client.get('/api/v1/timeseries', params=dict(
        region_id='IGP', variable='aod', frequency='day'))
    assert response.status_code == 400 and response.json()['error']['code'] == 'INVALID_PERIOD'


def test_sparse_qa_store_cannot_start_in_production(sparse_store, make_settings):
    with pytest.raises(ConfigError):
        with TestClient(create_app(make_settings(APP_ENV='prod', DATA_MODE='real'), store=sparse_store)):
            pass


def test_tampered_sparse_fixture_is_detected_and_regeneration_keeps_notes(tmp_path):
    generate(tmp_path)
    notes = tmp_path / 'notes.txt'
    notes.write_text('MOCK: manually written QA notes')
    (tmp_path / 'sparse_daily.csv').write_text('corrupt fixture')
    with pytest.raises(ValueError, match='Stale MOCK QA fixture: sparse_daily.csv'):
        generate(tmp_path, check=True)
    generate(tmp_path)
    generate(tmp_path, check=True)
    assert notes.read_text() == 'MOCK: manually written QA notes'
