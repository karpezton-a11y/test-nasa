"""Explicit metadata adapter for Giovanni CSV exports. Raw files stay intact."""
import csv,hashlib,io,re
from pathlib import Path
import numpy as np
import pandas as pd
from .methods import canonical_unit,align_series

def sha256(path):
    digest=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

def read_export(entry,root,start,end):
    required=['path','region_id','variable','frequency','source_id','unit','date_column','value_column','source_url','bbox','source_variable','product','version','accessed_at']
    missing=[x for x in required if x not in entry or entry[x] in ('',None)]
    if missing:raise ValueError('Manifest metadata missing: '+', '.join(missing))
    path=(Path(root)/entry['path']).resolve()
    if not path.is_file():raise FileNotFoundError(path)
    text=path.read_text(encoding='utf-8-sig')
    lines=text.splitlines()
    header=None
    for i,line in enumerate(lines):
        fields=next(csv.reader([line]))
        if entry['date_column'] in fields and entry['value_column'] in fields:header=i;break
    if header is None:raise ValueError('Exact date/value columns absent; inspect header and edit manifest')
    raw=pd.read_csv(io.StringIO('\n'.join(lines[header:])),dtype=str)
    dates=pd.to_datetime(raw[entry['date_column']],errors='raise')
    if entry['frequency']=='day' and (dates.dt.hour.ne(0)|dates.dt.minute.ne(0)|dates.dt.second.ne(0)).any():
        raise ValueError('Subdaily input cannot be silently treated as a daily series')
    value_text=raw[entry['value_column']].replace({'':np.nan,'NA':np.nan,'NaN':np.nan,'nan':np.nan})
    numbers=pd.to_numeric(value_text,errors='raise').astype(float)
    numbers.index=dates
    fill_count=0
    for code in entry.get('fill_values',[]):
        mask=numbers.eq(float(code));fill_count+=int(mask.sum());numbers=numbers.mask(mask)
    # For raw encoded data only: scale and offset must be supplied explicitly.
    numbers=numbers*float(entry.get('scale_factor',1))+float(entry.get('add_offset',0))
    numbers,unit=canonical_unit(numbers,entry['variable'],entry['frequency'],entry['unit'])
    source_index=pd.DatetimeIndex(numbers.index)
    if source_index.tz is not None:source_index=source_index.tz_convert('UTC').tz_localize(None)
    source_index=source_index.to_period('M').to_timestamp() if entry['frequency']=='month' else source_index.normalize()
    s=align_series(numbers,start,end,entry['frequency'])
    suspect=s.notna() & (~np.isfinite(s))
    if entry['variable']=='rainfall':suspect |= s<0
    if 'valid_min' in entry:suspect |= s<float(entry['valid_min'])
    if 'valid_max' in entry:suspect |= s>float(entry['valid_max'])
    original_suspect=s[suspect].to_dict();s=s.mask(suspect)
    flags=pd.Series('ok',index=s.index)
    flags.loc[s.isna()]='missing';flags.loc[suspect]='suspect'
    df=pd.DataFrame({'date':s.index,'region_id':entry['region_id'],'variable':entry['variable'],
        'frequency':entry['frequency'],'value':s.to_numpy(),'unit':unit,'source_id':entry['source_id'],
        'valid_fraction':np.nan,'qc_flag':flags.to_numpy()})
    if entry.get('coverage_column'):
        if entry['coverage_column'] not in raw:raise ValueError('Coverage column missing')
        c=pd.Series(pd.to_numeric(raw[entry['coverage_column']],errors='raise').to_numpy(),index=dates)
        if ((c.dropna()<0)|(c.dropna()>1)).any():raise ValueError('Coverage must be fraction 0..1')
        c=align_series(c,start,end,entry['frequency'])
        df['valid_fraction']=c.to_numpy()
    provenance={k:entry[k] for k in required}
    provenance.update(raw_sha256=sha256(path),raw_rows=len(raw),output_rows=len(df),fill_values_removed=fill_count,
        source_dates=[d.strftime('%Y-%m-%d') for d in source_index],
        suspect_count=len(original_suspect),suspect_observations={str(k):float(v) for k,v in original_suspect.items()},
        canonical_unit=unit,method=entry.get('method','Giovanni area-averaged time series; recorded export'),
        coverage_definition=entry.get('coverage_definition','unknown'),data_status='real',metadata_header='\n'.join(lines[:header]))
    return df,provenance

