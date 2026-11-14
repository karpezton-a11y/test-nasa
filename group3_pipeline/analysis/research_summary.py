"""Descriptive findings from actual pipeline outputs; no trend significance claims."""
import argparse,json,pathlib
import numpy as np
import pandas as pd

def number(x):
    return float(x) if pd.notna(x) and np.isfinite(x) else None

def summarize(folder):
    folder=pathlib.Path(folder)
    monthly=pd.read_csv(folder/'timeseries_monthly.csv',parse_dates=['date'])
    daily=pd.read_csv(folder/'timeseries_daily.csv',parse_dates=['date'])
    anomalies=pd.read_csv(folder/'anomalies_monthly.csv',parse_dates=['date'])
    indicators=pd.read_csv(folder/'rainfall_indicators_annual.csv')
    checks=pd.read_csv(folder/'rainfall_monthly_daily_check.csv',parse_dates=['date'])
    primary=['IMERG_V07_FINAL_MONTHLY','MODIS_AQUA_C61_MONTHLY']
    primary_monthly=monthly[monthly.source_id.isin(primary)]
    summary={'period':'2003-01-01 through 2024-12-31','data_status':'real',
             'review_status':'awaiting_independent_review',
             'claim_boundary':'Descriptive regional-box observations and defined anomaly flags. No statistical trend, causal attribution or surface PM2.5 finding.',
             'regions':{},'cross_product_comparisons':[],'charts':{}}
    annual_rain={};annual_aod={};clim_rain={};clim_aod={};cdd={};heavy={};window_rows=[]
    for region in ['IGP','TN']:
        rain=primary_monthly[(primary_monthly.region_id==region)&(primary_monthly.variable=='rainfall')].set_index('date').value
        aod=primary_monthly[(primary_monthly.region_id==region)&(primary_monthly.variable=='aod')].set_index('date').value
        annual=rain.groupby(rain.index.year).sum(min_count=12)
        annual_a=aod.groupby(aod.index.year).mean()
        climatology=rain.groupby(rain.index.month).mean()
        aod_climatology=aod.groupby(aod.index.month).mean()
        rain_daily=daily[(daily.region_id==region)&(daily.variable=='rainfall')]
        aod_daily=daily[(daily.region_id==region)&(daily.variable=='aod')]
        seasonal_shares={s:number(100*climatology[months].sum()/climatology.sum()) for s,months in [('JJAS',[6,7,8,9]),('OND',[10,11,12])]}
        an=anomalies[(anomalies.region_id==region)&anomalies.source_id.isin(primary)]
        flags=an[an.category.isin(['unusually_wet','unusually_dry','unusually_high_aod','unusually_low_aod','high_aod','low_aod'])]
        # Export all actual non-typical evaluated flags; category names remain implementation-defined.
        flags=an[an.evaluation_status.eq('evaluated')&~an.category.isin(['typical','none','not_evaluated'])]
        flags=flags.copy();flags['date']=flags.date.dt.strftime('%Y-%m-%d')
        ind=indicators[(indicators.region_id==region)&indicators.season.eq('ALL')]
        dry=ind[ind.indicator.eq('longest_dry_spell')].set_index('year').value
        share=ind[ind.indicator.eq('heavy_rain_share')].set_index('year').value
        check=checks[checks.region_id==region].copy()
        relative=(check.daily_sum-check.monthly_product)/check.monthly_product*100
        apr=aod[(aod.index.month==4)&(aod.index.year>=2016)&(aod.index.year<=2019)]
        apr2020=aod.get(pd.Timestamp('2020-04-01'),np.nan)
        d={
          'monthly_rain_n':int(rain.notna().sum()),'monthly_aod_n':int(aod.notna().sum()),
          'daily_rain_n':int(rain_daily.value.notna().sum()),'daily_aod_n':int(aod_daily.value.notna().sum()),
          'daily_aod_missing_pct':number(100*aod_daily.value.isna().mean()),
          'daily_aod_nonpositive_count':int((aod_daily.value<=0).sum()),
          'mean_annual_rain_monthly_product_mm':number(annual.mean()),
          'driest_annual_rain':{'year':int(annual.idxmin()),'mm':number(annual.min())},
          'wettest_annual_rain':{'year':int(annual.idxmax()),'mm':number(annual.max())},
          'rain_climatology_peak_month':int(climatology.idxmax()),
          'seasonal_rain_share_pct':seasonal_shares,
          'mean_monthly_aod':number(aod.mean()),
          'anomaly_category_counts':{v:{str(k):int(n) for k,n in g.category.value_counts().items()} for v,g in an.groupby('variable')},
          'anomaly_flags':json.loads(flags.to_json(orient='records')),
          'annual_regional_cdd':{'min_days':number(dry.min()),'max_days':number(dry.max()),'max_year':int(dry.idxmax())},
          'annual_regional_heavy_share':{'min_pct':number(share.min()),'max_pct':number(share.max()),'max_year':int(share.idxmax())},
          'daily_vs_monthly_rain':{'complete_months':int(check.daily_complete.sum()),'mean_difference_mm':number(check.difference.mean()),
              'mean_absolute_difference_mm':number(check.difference.abs().mean()),'max_absolute_difference_mm':number(check.difference.abs().max()),
              'aggregate_difference_pct':number(100*(check.daily_sum.sum()-check.monthly_product.sum())/check.monthly_product.sum()),
              'median_month_relative_difference_pct':number(relative.median()),'status':'differences documented; products retained separately; peer review required'},
          'april_2020_case':{'aqua_april_2020':number(apr2020),'aqua_april_2016_2019_mean':number(apr.mean()),
              'difference_pct':number(100*(apr2020-apr.mean())/apr.mean()),
              'note':'Calendar April in the project box. Different platform/period/mask from the published NASA Terra March 31–April 5 case. No causal attribution.'},
        }
        daily_a=aod_daily.set_index('date').value
        window_means=[]
        for year in range(2016,2021):
            window=daily_a.loc[f'{year}-03-31':f'{year}-04-05']
            if len(window)!=6:raise ValueError('Expected six indexed dates in context window')
            window_means.append(float(window.mean()))
            window_rows.append({'region_id':region,'year':year,'mean_aqua_aod':float(window.mean()),'valid_days':int(window.notna().sum()),'expected_days':6})
        d['march31_april5_case']={'aqua_2020':number(window_means[4]),'mean_of_four_baseline_year_means':number(np.mean(window_means[:4])),
            'difference_pct':number(100*(window_means[4]/np.mean(window_means[:4])-1)),
            'method':'Mean of valid regional daily Aqua AOD per six-day year window; equal-weight mean of 2016–2019 yearly window means. Different platform and footprint from published Terra map.'}
        summary['regions'][region]=d
        annual_rain[region]=[number(v) for v in annual.values]
        annual_aod[region]=[number(v) for v in annual_a.values]
        clim_rain[region]=[number(v) for v in climatology.values]
        clim_aod[region]=[number(v) for v in aod_climatology.values]
        cdd[region]=[number(v) for v in dry.values];heavy[region]=[number(v) for v in share.values]
        for other in ['MODIS_TERRA_C61_MONTHLY','MERRA2_MONTHLY_TOTEXTTAU']:
            b=monthly[(monthly.region_id==region)&monthly.source_id.eq(other)].set_index('date').value
            pair=pd.concat([aod.rename('aqua'),b.rename('comparison')],axis=1).dropna()
            if pair.empty:continue
            summary['cross_product_comparisons'].append({'region_id':region,'comparison_source':other,'paired_months':len(pair),
                'aqua_mean':number(pair.aqua.mean()),'comparison_mean':number(pair.comparison.mean()),
                'mean_comparison_minus_aqua':number((pair.comparison-pair.aqua).mean()),
                'pearson_r_descriptive':number(pair.aqua.corr(pair.comparison)),
                'rmse':number(np.sqrt(np.mean((pair.comparison-pair.aqua)**2))),
                'note':'Descriptive agreement only; no independence or trend significance claimed. Different resolution, masks and sampling.'})
    summary['charts']={
        'annual_rain':{'categories':list(range(2003,2025)),'series':annual_rain,'unit':'mm/year; monthly-product sum'},
        'annual_aod':{'categories':list(range(2003,2025)),'series':annual_aod,'unit':'dimensionless; unweighted mean of 12 monthly regional means'},
        'rain_climatology':{'categories':['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],'series':clim_rain,'unit':'mm/month; 2003–2024 calendar-month means'},
        'aod_climatology':{'categories':['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],'series':clim_aod,'unit':'dimensionless; 2003–2024 calendar-month means'},
        'annual_cdd':{'categories':list(range(2003,2025)),'series':cdd,'unit':'days; regional daily mean below 1 mm/day'},
        'annual_heavy_share':{'categories':list(range(2003,2025)),'series':heavy,'unit':'percent of wet-day rainfall above baseline wet-day P95'},
    }
    pd.DataFrame(window_rows).to_csv(folder/'aod_2020_six_day_context.csv',index=False)
    (folder/'research_findings.json').write_text(json.dumps(summary,indent=2,allow_nan=False),encoding='utf-8')
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--results',default='results')
    args=parser.parse_args();s=summarize(args.results)
    print(json.dumps({r:{k:v for k,v in d.items() if k not in ['anomaly_flags']} for r,d in s['regions'].items()},indent=2))
