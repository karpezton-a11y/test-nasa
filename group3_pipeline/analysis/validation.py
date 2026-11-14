"""Data validation summaries, not a claim of independent statistical validation."""
import numpy as np
import pandas as pd

def series_summary(df):
    summaries=[]
    for keys,g in df.groupby(['region_id','variable','frequency','source_id']):
        valid=g['value'].dropna()
        summaries.append(dict(zip(['region_id','variable','frequency','source_id'],keys))|dict(n_expected=len(g),n_valid=len(valid),
            missing_pct=100*(1-len(valid)/len(g)),suspect_count=int(g.qc_flag.eq('suspect').sum()),
            mean=float(valid.mean()) if len(valid) else None,min=float(valid.min()) if len(valid) else None,
            max=float(valid.max()) if len(valid) else None,coverage_known=int(g.valid_fraction.notna().sum())))
    return summaries

def rainfall_monthly_daily_check(df):
    rows=[]
    for region in df.region_id.unique():
        g=df[(df.region_id==region)&(df.variable=='rainfall')]
        daily=g[g.frequency=='day'].set_index('date').value
        monthly=g[g.frequency=='month'].set_index('date').value
        if daily.empty or monthly.empty:continue
        summed=daily.resample('MS').sum(min_count=1)
        valid=daily.notna().resample('MS').sum()
        expected=pd.Series(daily.index.days_in_month,index=daily.index).resample('MS').first()
        for date in monthly.index.intersection(summed.index):
            complete=valid.at[date]==expected.at[date]
            d=float(summed.at[date]-monthly.at[date]) if complete and pd.notna(monthly.at[date]) else np.nan
            rows.append(dict(region_id=region,date=date,monthly_product=monthly.at[date],daily_sum=summed.at[date],
                daily_complete=bool(complete),difference=d,status='review_difference' if np.isfinite(d) else 'not_comparable'))
    return pd.DataFrame(rows)

