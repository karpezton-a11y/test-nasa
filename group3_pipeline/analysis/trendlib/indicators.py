from ..methods import rainfall_indicators

def compute_rainfall_indicators(daily_series,seasons=None,region_id=None,source_id=None):
    table=rainfall_indicators(daily_series,seasons=seasons)
    table['region_id']=region_id;table['source_id']=source_id
    return table
