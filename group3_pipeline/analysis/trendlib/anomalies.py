"""Backend-friendly adapter for Sritharan's anomaly function."""
import numpy as np
from ..methods import monthly_anomalies

def _safe(value):
    if isinstance(value,dict):return {k:_safe(v) for k,v in value.items()}
    if isinstance(value,list):return [_safe(v) for v in value]
    if isinstance(value,(float,np.floating)):return float(value) if np.isfinite(value) else None
    if isinstance(value,np.integer):return int(value)
    if hasattr(value,'isoformat'):return value.strftime('%Y-%m-%d')
    return value

def compute_anomalies(series,variable,coverage=None,region_id=None,source_id=None,min_baseline=15):
    result=monthly_anomalies(series,variable,coverage,min_baseline=min_baseline)
    flags=result[result.category.str.startswith('unusually')].copy()
    flags['score_type']='percentile' if variable=='rainfall' else 'z_log'
    return _safe({'region_id':region_id,'variable':variable,'source_id':source_id,
        'baseline':{'start':'2003-01','end':'2024-12','method':'same_calendar_month',
            'statistic':'empirical_percentile' if variable=='rainfall' else 'z_log','detrended':False},
        'thresholds':{'high':.9 if variable=='rainfall' else 2,'low':.1 if variable=='rainfall' else -2},
        'anomalies':flags.to_dict('records'),'evaluation_summary':result.evaluation_status.value_counts().to_dict(),
        'combined_flags':[],'method_note':'See docs/methods.md for eligibility, quantile ties and baseline rules.'})
