#!/usr/bin/env python
"""Generate deterministic MOCK daily rows for large-file/CSV acceptance tests.

This is test input generation, not scientific analysis. Never use these values
as observations or place this fixture in data/processed/. The public mock
registry supplies the regions, period, canonical units and primary sources.
"""
from __future__ import annotations

import argparse
import calendar
import csv
from datetime import date, timedelta
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'scripts/mock_config.json'
OUTPUT = ROOT / 'data/mock/qa_large'
COLUMNS = ['date', 'region_id', 'variable', 'frequency', 'value', 'unit',
           'source_id', 'valid_fraction', 'qc_flag']
ALTERNATE_SOURCE = 'MOCK_AOD_SECONDARY_DAILY'


def _daily_csv(cases: list[dict], first: date, last: date, version: str,
               contract_version: str, *, sparse: bool = False) -> tuple[bytes, int]:
    buffer = io.StringIO(newline='')
    buffer.write('# MOCK QA input only | data_status=mock | no scientific findings\n')
    buffer.write(f'# data_version={version} | contract_version={contract_version}\n')
    buffer.write('# Missing values are empty cells; daily valid_fraction is unknown and empty\n')
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator='\n')
    writer.writeheader()
    count = 0
    for index, case in enumerate(cases):
        current = first
        while current <= last:
            offset = (current - first).days
            # Deliberate, deterministic QA cases. No statistic is inferred.
            missing = (offset % 5 < 2 or 2020 <= current.year <= 2021) if sparse else offset % 17 == 0
            if missing:
                value, flag = '', 'missing'
            else:
                value = 0.0 if offset % 11 == 0 else (offset * 37 + index + 1) / 123457
                flag = 'suspect' if offset % 29 == 0 else 'low_coverage' if offset % 31 == 0 else 'ok'
            writer.writerow(dict(date=current.isoformat(), frequency='day', value=value,
                                 valid_fraction='', qc_flag=flag, **case))
            count += 1
            current += timedelta(days=1)
    return buffer.getvalue().encode('utf-8'), count


def build_fixture(registry: Path = REGISTRY) -> dict[str, bytes]:
    """Return canonical bytes; timestamps and generated values are reproducible."""
    registry_bytes = registry.read_bytes()
    cfg = json.loads(registry_bytes)
    start, end = cfg['baseline']['start'], cfg['baseline']['end']
    first = date.fromisoformat(start + '-01')
    year, month = map(int, end.split('-'))
    last = date(year, month, calendar.monthrange(year, month)[1])
    if first > last:
        raise ValueError('The MOCK fixture period is reversed')
    variables = {v['variable']: v for v in cfg['variables']}
    cases = []
    for region in cfg['regions']:
        for variable in ('rainfall', 'aod'):
            spec = variables[variable]
            cases.append(dict(region_id=region['region_id'], variable=variable,
                              source_id=spec['sources'][1], unit=spec['daily_unit']))
        cases.append(dict(region_id=region['region_id'], variable='aod',
                          source_id=ALTERNATE_SOURCE, unit=variables['aod']['daily_unit']))
    version = cfg['data_version'] + '-normal'
    payload, count = _daily_csv(cases, first, last, version, cfg['contract_version'])
    sparse_cases = [case for case in cases if case['source_id'] != ALTERNATE_SOURCE]
    sparse_payload, sparse_count = _daily_csv(sparse_cases, first, last, version,
                                             cfg['contract_version'], sparse=True)
    manifest = dict(data_status='mock', data_version=version,
                    contract_version=cfg['contract_version'], generated_at=cfg['generated_at'],
                    result=dict(purpose='MOCK QA input, never scientific observations',
                                registry_sha256=hashlib.sha256(registry_bytes).hexdigest(),
                                start=start, end=end, series=cases,
                                days_per_series=(last-first).days+1, rows=count,
                                csv_sha256=hashlib.sha256(payload).hexdigest(),
                                sparse=dict(filename='sparse_daily.csv', rows=sparse_count,
                                            series=sparse_cases,
                                            policy='MOCK: two of every five daily slots missing; complete 2020-2021 outage',
                                            csv_sha256=hashlib.sha256(sparse_payload).hexdigest())))
    return {'daily.csv': payload, 'sparse_daily.csv': sparse_payload, 'manifest.json':
            (json.dumps(manifest, indent=2, ensure_ascii=False)+'\n').encode('utf-8')}


def generate(output: Path = OUTPUT, *, check: bool = False) -> int:
    target = output.resolve()
    # Allow pytest temp dirs, but never other repository paths or processed data.
    if target.is_relative_to(ROOT) and target != OUTPUT:
        raise ValueError('MOCK QA output is restricted to data/mock/qa_large/')
    files = build_fixture()
    if check:
        stale = [name for name, payload in files.items()
                 if not (target / name).is_file() or (target / name).read_bytes() != payload]
        if stale:
            raise ValueError('Stale MOCK QA fixture: ' + ', '.join(stale))
    else:
        target.mkdir(parents=True, exist_ok=True)
        for name, payload in files.items():
            path = target / name
            if path.is_symlink():
                raise ValueError('Refusing a symlinked MOCK QA output')
            path.write_bytes(payload)
    return json.loads(files['manifest.json'])['result']['rows']


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify committed bytes without writing')
    args = parser.parse_args()
    try:
        rows = generate(check=args.check)
    except (ValueError, OSError) as exc:
        parser.exit(1, f'{exc}\n')
    sparse_rows = json.loads((OUTPUT / 'manifest.json').read_text())['result']['sparse']['rows']
    print(f'MOCK QA fixtures {"verified" if args.check else "generated"}: '
          f'{rows} normal and {sparse_rows} sparse rows')


if __name__ == '__main__':
    main()
