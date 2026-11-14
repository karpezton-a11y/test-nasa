"""Run from the package directory: python run_pipeline.py --manifest inputs.json."""
from __future__ import annotations
import argparse,json,pathlib,sys
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from analysis.io import read_export
from analysis.methods import daily_temporal_coverage,monthly_anomalies,rainfall_indicators,combined_flags
from analysis.validation import series_summary,rainfall_monthly_daily_check

def clean_json(o):
    if isinstance(o,dict):return {str(k):clean_json(v) for k,v in o.items()}
    if isinstance(o,list):return [clean_json(x) for x in o]
    if isinstance(o,(np.integer,)):return int(o)
    if isinstance(o,(np.floating,float)):return float(o) if np.isfinite(o) else None
    if isinstance(o,(pd.Timestamp,datetime)):return o.isoformat()
    return o

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest',default='inputs.json');ap.add_argument('--output',default='results')
    ap.add_argument('--figures',action='store_true')
    args=ap.parse_args(argv)
    root=pathlib.Path(args.manifest).resolve().parent
    config=json.loads(pathlib.Path(args.manifest).read_text(encoding='utf8'))
    out=pathlib.Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    if not config.get('inputs'):
        status={'status':'awaiting_observations','data_status':'unavailable','reason':'No input files supplied. No environmental results calculated.',
                'required_primary_series':['IGP rainfall month','TN rainfall month','IGP Aqua AOD month','TN Aqua AOD month']}
        (out/'run_status.json').write_text(json.dumps(status,indent=2))
        print(status['reason']);return 2
    frames=[];prov=[]
    for entry in config['inputs']:
        df,p=read_export(entry,root,config['start'],config['end'])
        # Retain observed source rows before joining chunks. Full-calendar gaps are indexed once after merging.
        frames.append(df[df.date.isin(pd.to_datetime(p['source_dates']))].copy());prov.append(p)
    data=pd.concat(frames,ignore_index=True)
    # Multiple sources for a variable are permitted, overlapping rows in a source are not.
    if data.duplicated(['date','region_id','variable','frequency','source_id']).any():
        raise ValueError('Duplicate contract rows across files; resolve chunk overlaps before continuing')
    versions={p['version'] for p in prov if p['variable']=='rainfall'}
    if len(versions)>1:raise ValueError('Mixed rainfall versions rejected')
    aligned=[]
    for keys,g in data.groupby(['region_id','variable','frequency','source_id','unit']):
        expected=pd.date_range(config['start'],config['end'],freq='MS' if keys[2]=='month' else 'D')
        r=g.set_index('date').reindex(expected).rename_axis('date').reset_index()
        for column,value in zip(['region_id','variable','frequency','source_id','unit'],keys):r[column]=value
        r['qc_flag']=r['qc_flag'].fillna('missing')
        aligned.append(r)
    data=pd.concat(aligned,ignore_index=True)[['date','region_id','variable','frequency','value','unit','source_id','valid_fraction','qc_flag']]
    series_keys=['region_id','variable','source_id']
    coverages={}
    for keys,g in data[data.frequency=='day'].groupby(series_keys):
        coverages[keys]=daily_temporal_coverage(g.set_index('date').value)
    # Daily/monthly IDs differ; match via declared pair rather than variable name alone.
    source_pairs=config.get('daily_monthly_source_pairs',{})
    for (region,variable,daily_source),cov in coverages.items():
        monthly_source=source_pairs.get(daily_source)
        if monthly_source:
            mask=(data.region_id==region)&(data.variable==variable)&(data.frequency=='month')&(data.source_id==monthly_source)
            data.loc[mask,'valid_fraction']=data.loc[mask,'date'].map(cov)
    low=(data.valid_fraction<config.get('low_coverage_threshold',.3)) & data.value.notna() & data.qc_flag.eq('ok')
    data.loc[low,'qc_flag']='low_coverage'
    data=data.sort_values(['region_id','variable','frequency','source_id','date'])
    # Canonical nine-column contract. Additional metadata stays in sidecars until G1 agrees.
    for freq in ['month','day']:
        subset=data[data.frequency==freq]
        if len(subset):subset.to_csv(out/('timeseries_monthly.csv' if freq=='month' else 'timeseries_daily.csv'),index=False,date_format='%Y-%m-%d',na_rep='')
    all_anom=[];by_region={}
    for (region,variable,source),g in data[data.frequency=='month'].groupby(series_keys):
        an=monthly_anomalies(g.set_index('date').value,variable,g.set_index('date').valid_fraction,
                            min_baseline=config.get('min_anomaly_baseline',15))
        an['region_id']=region;an['variable']=variable;an['source_id']=source;all_anom.append(an)
        if source in config.get('primary_source_ids',[]):by_region[(region,variable)]=an
    if all_anom:
        anomalies=pd.concat(all_anom,ignore_index=True)
        anomalies.to_csv(out/'anomalies_monthly.csv',index=False,date_format='%Y-%m-%d',na_rep='')
        (out/'anomalies_monthly.json').write_text(json.dumps(clean_json(anomalies.to_dict('records')),indent=2),encoding='utf8')
    combined=[]
    for region in data.region_id.unique():
        if (region,'rainfall') in by_region and (region,'aod') in by_region:
            c=combined_flags(by_region[(region,'rainfall')],by_region[(region,'aod')]);c['region_id']=region;combined.append(c)
    if combined:pd.concat(combined,ignore_index=True).to_csv(out/'combined_anomalies.csv',index=False,date_format='%Y-%m-%d')
    indicators=[]
    for (region,variable,source),g in data[(data.frequency=='day')&(data.variable=='rainfall')].groupby(series_keys):
        ind=rainfall_indicators(g.set_index('date').value,seasons=config.get('indicator_seasons',['ALL','JJAS','OND']))
        ind['region_id']=region;ind['source_id']=source;indicators.append(ind)
    if indicators:pd.concat(indicators,ignore_index=True).to_csv(out/'rainfall_indicators_annual.csv',index=False,na_rep='')
    check=rainfall_monthly_daily_check(data)
    if len(check):check.to_csv(out/'rainfall_monthly_daily_check.csv',index=False,date_format='%Y-%m-%d',na_rep='')
    summaries=series_summary(data)
    (out/'data_quality_summary.json').write_text(json.dumps(clean_json(summaries),indent=2))
    (out/'provenance.json').write_text(json.dumps(clean_json(prov),indent=2),encoding='utf8')
    metadata={'data_version':config['data_version'],'contract_version':config.get('contract_version','proposed_1.0'),
        'data_status':'real','generated_at':datetime.now(timezone.utc).isoformat(),
        'spatial_method':'Documented per source in provenance.json',
        'monthly_valid_fraction':'Valid regional daily values / calendar days, when daily source pair exists',
        'daily_valid_fraction':'Spatial valid-cell fraction only when supplied, otherwise unknown',
        'review_status':'awaiting_independent_review_by_Aadarsh','anomaly_min_baseline':config.get('min_anomaly_baseline',15),
        'method_decisions':'docs/methods.md','statistical_results':'Aadarsh adapter required for trend/evidence results'}
    (out/'metadata.json').write_text(json.dumps(metadata,indent=2))
    report=['# Validation report Part A','',f'Run: {metadata["generated_at"]}',
        '','Automated data checks executed. Independent scientific review remains pending.','',
        '| Region | Variable | Source | Frequency | Valid / expected | Missing % | Coverage known |',
        '|---|---|---|---|---|---|---|']
    for r in summaries:report.append(f'| {r["region_id"]} | {r["variable"]} | {r["source_id"]} | {r["frequency"]} | {r["n_valid"]}/{r["n_expected"]} | {r["missing_pct"]:.2f} | {r["coverage_known"]} |')
    report+=['','## Checks executed','- Exact date/value columns required by manifest.','- Duplicate source timestamps rejected.',
        '- Units converted only through explicit rules.','- Missing timestamps indexed without filling values.',
        '- Source metadata and SHA256 retained.','- Suspect observations excluded with counts and original values retained in provenance.',
        '','## Review still needed','- Confirm selected field, version, scale/offset and actual geographic mask.',
        '- Review seasonal climatology and daily/monthly differences; no arbitrary discrepancy tolerance is imposed.',
        '- Review low-coverage AOD flags and anomaly eligibility.',
        '- Confirm P95, missing-day and minimum-baseline conventions with Aadarsh.',
        '- Verify resulting files against Group 1 contract before integration.']
    (out/'validation_report_part_A.md').write_text('\n'.join(report),encoding='utf8')
    if args.figures:
        from analysis.figures import build_figures
        build_figures(data,out/'figures',pd.concat(indicators,ignore_index=True) if indicators else None,
                      pd.concat(all_anom,ignore_index=True) if all_anom else None)
    (out/'run_status.json').write_text(json.dumps({'status':'computed_pending_peer_review','data_status':'real',
        'input_files':len(prov),'rows':len(data),'independent_review_complete':False,'trend_results_generated':False},indent=2))
    print(f'Processed {len(prov)} real exports. Outputs: {out}. Aadarsh review still required.')
    return 0

if __name__=='__main__':sys.exit(main())

