"""Scientific methods. Synthetic arrays belong only in tests, never evidence."""
from __future__ import annotations
import numpy as np
import pandas as pd

SEASONS={'ALL':list(range(1,13)),'JF':[1,2],'MAM':[3,4,5],'JJAS':[6,7,8,9],'OND':[10,11,12]}

def canonical_unit(values: pd.Series, variable: str, frequency: str, unit: str) -> tuple[pd.Series,str]:
    """Metadata-driven unit conversion. Never infer units from magnitudes."""
    u=unit.strip().lower().replace(' ','')
    v=pd.to_numeric(values,errors='raise').astype(float)
    if variable in ('aod','aod_terra','aod_merra2'):
        if u not in ('1','unitless','dimensionless'):raise ValueError('AOD must be dimensionless')
        return v,'1'
    if variable!='rainfall':raise ValueError('Unknown variable')
    if frequency=='month':
        if u in ('mm/hr','mm/hour','mmh-1'):
            if not isinstance(v.index,pd.DatetimeIndex):raise ValueError('Conversion requires dated values')
            return v*24*v.index.days_in_month,'mm/month'
        if u in ('mm','mm/month','mmmonth-1'):return v,'mm/month'
    elif frequency=='day':
        if u in ('mm/day','mmd-1','mm'):return v,'mm/day'
    raise ValueError(f'Unsupported or ambiguous units: {unit!r} for {frequency}')

def align_series(series: pd.Series, start: str, end: str, frequency: str) -> pd.Series:
    """Create expected timestamps without inventing observations."""
    s=series.copy()
    s.index=pd.to_datetime(s.index)
    if s.index.tz is not None:s.index=s.index.tz_convert('UTC').tz_localize(None)
    if frequency=='month':s.index=s.index.to_period('M').to_timestamp()
    else:s.index=s.index.normalize()
    if s.index.duplicated().any():raise ValueError('Duplicate timestamps after date normalisation')
    s=s.sort_index()
    expected=pd.date_range(start,end,freq='MS' if frequency=='month' else 'D')
    return s.reindex(expected)

def daily_temporal_coverage(series: pd.Series) -> pd.Series:
    """Fraction of calendar days with valid regional values; not spatial coverage."""
    s=series.copy()
    if s.empty:return pd.Series(dtype=float)
    full=pd.date_range(s.index.min().to_period('M').start_time,s.index.max().to_period('M').end_time.normalize(),freq='D')
    return s.reindex(full).notna().resample('MS').sum()/pd.Series(full.days_in_month,index=full).resample('MS').first()

def monthly_anomalies(series: pd.Series, variable: str, coverage: pd.Series | None=None,
                      min_baseline: int=15, dry_median_limit: float=10) -> pd.DataFrame:
    """In-sample same-calendar-month baseline. Threshold convention fixed in docs."""
    s=series.astype(float)
    cov=coverage.reindex(s.index) if coverage is not None else pd.Series(np.nan,index=s.index)
    rows=[]
    for month in range(1,13):
        idx=s.index[s.index.month==month]
        sample=s.reindex(idx)
        if variable=='rainfall':eligible=sample.where(cov.reindex(idx)>=.9)
        elif variable.startswith('aod'):eligible=sample.where(sample>0)
        else:raise ValueError(variable)
        baseline=eligible.dropna()
        med=float(baseline.median()) if len(baseline) else np.nan
        q10=q90=mu=sd=np.nan
        if len(baseline)>=min_baseline:
            if variable=='rainfall':q10,q90=np.quantile(baseline,[.1,.9],method='linear')
            else:
                logs=np.log(baseline)
                mu=float(logs.mean());sd=float(logs.std(ddof=1))
        for date,value in sample.items():
            category='not_evaluated';score=np.nan;note='';status='insufficient_baseline'
            c=cov.get(date,np.nan)
            if pd.isna(value):status='missing';note='No observation'
            elif variable=='rainfall' and (pd.isna(c) or c<.9):
                status='insufficient_coverage';note='Rainfall flags require measured temporal coverage >=0.90'
            elif variable.startswith('aod') and value<=0:
                status='undefined_log';note='Non-positive AOD cannot enter log baseline'
            elif len(baseline)<min_baseline:note=f'Baseline requires {min_baseline} eligible same-month observations'
            elif variable=='rainfall':
                score=float((baseline<value).sum()+.5*(baseline==value).sum())/len(baseline)
                status='evaluated';category='typical'
                if q10==q90:note='Tied baseline: unusual flags suppressed'
                elif value>=q90:category='unusually_wet'
                elif value<=q10 and med>=dry_median_limit:category='unusually_dry'
                elif value<=q10:note='Dry flag suppressed for normally dry calendar month'
            elif not np.isfinite(sd) or sd<=1e-12*max(1.,abs(mu)):
                status='insufficient_variation';note='Log baseline standard deviation is zero'
            else:
                score=float((np.log(value)-mu)/sd)
                status='evaluated';category='unusually_high_aod' if score>=2 else 'unusually_low_aod' if score<=-2 else 'typical'
                if pd.isna(c):note='Temporal coverage unknown'
                elif c<.3:note='Low temporal coverage; interpret flag cautiously'
            rows.append(dict(date=date,value=value,baseline_median=med,baseline_n=len(baseline),
                threshold_low=q10 if variable=='rainfall' else -2,threshold_high=q90 if variable=='rainfall' else 2,
                score=score,score_type='empirical_midrank' if variable=='rainfall' else 'z_log_sample_sd',
                category=category,evaluation_status=status,valid_fraction=c,note=note))
    return pd.DataFrame(rows).sort_values('date').reset_index(drop=True)

def rainfall_indicators(series: pd.Series, seasons=None, completeness: float=.95) -> pd.DataFrame:
    """P95 wet-day share and CDD for regional means. Missing days break runs."""
    if series.empty:return pd.DataFrame()
    s=series.astype(float).sort_index()
    if s.index.duplicated().any():raise ValueError('Duplicate daily dates')
    full=pd.date_range(s.index.min().year.__str__()+'-01-01',str(s.index.max().year)+'-12-31',freq='D')
    s=s.reindex(full)
    if (s.dropna()<0).any():raise ValueError('Negative rainfall must be resolved before indicators')
    records=[]
    for season in seasons or ['ALL','JJAS','OND']:
        months=SEASONS[season]
        baseline=s[s.index.month.isin(months)]
        wet=baseline[baseline>=1].dropna()
        p95=float(np.quantile(wet,.95,method='linear')) if len(wet) else np.nan
        for year in sorted(set(s.index.year)):
            dates=pd.date_range(f'{year}-01-01',f'{year}-12-31',freq='D')
            dates=dates[dates.month.isin(months)]
            vals=s.reindex(dates)
            fraction=float(vals.notna().mean())
            run=longest=0
            for value in vals:
                if pd.notna(value) and value<1:run+=1;longest=max(longest,run)
                else:run=0
            wetvals=vals[vals>=1];denom=float(wetvals.sum())
            share=float(100*vals[vals>p95].sum()/denom) if denom>0 and np.isfinite(p95) else np.nan
            ok=fraction>=completeness
            note='Missing days interrupt spells; maximum may be underestimated' if vals.isna().any() else ''
            if not ok:note='Below completeness requirement'
            for indicator,value,unit in [('heavy_rain_share',share,'%'),('longest_dry_spell',float(longest),'days')]:
                records.append(dict(year=year,season=season,indicator=indicator,value=value if ok else np.nan,
                    unit=unit,valid_fraction=fraction,n_expected=len(vals),n_valid=int(vals.notna().sum()),
                    wet_day_p95=p95,baseline_wet_days=len(wet),method='regional_mean;linear_P95;strict_above;season_specific_baseline',note=note))
    return pd.DataFrame(records)

def combined_flags(rain: pd.DataFrame, aod: pd.DataFrame) -> pd.DataFrame:
    r=rain.set_index('date');a=aod.set_index('date');rows=[]
    for date in r.index.intersection(a.index):
        rc,ac=r.at[date,'category'],a.at[date,'category']
        mapping={('unusually_dry','unusually_high_aod'):'dry_and_high_aod',('unusually_wet','unusually_high_aod'):'wet_and_high_aod',('unusually_wet','unusually_low_aod'):'wet_and_low_aod',('unusually_dry','unusually_low_aod'):'dry_and_low_aod'}
        if (rc,ac) in mapping:rows.append(dict(date=date,category=mapping[(rc,ac)],interpretation='Co-occurrence only'))
    return pd.DataFrame(rows,columns=['date','category','interpretation'])

