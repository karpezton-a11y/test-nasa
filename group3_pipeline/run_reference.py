"""Generate reference results using Aadarsh's explicitly supplied adapter."""
import argparse,hashlib,importlib.util,json,pathlib
import pandas as pd

def main():
    p=argparse.ArgumentParser();p.add_argument('--series',required=True);p.add_argument('--adapter',required=True)
    p.add_argument('--output',default='results/trend_results_reference.json');a=p.parse_args()
    spec=importlib.util.spec_from_file_location('aadarsh_adapter',a.adapter);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    if not hasattr(mod,'analyze_series'):raise ValueError('Adapter must define analyze_series(series, metadata)')
    data=pd.read_csv(a.series,parse_dates=['date']);results=[]
    for keys,g in data.groupby(['region_id','variable','source_id','unit']):
        series=g.set_index('date').value.sort_index()
        metadata=dict(zip(['region_id','variable','source_id','unit'],keys))
        for season in ['ALL','JF','MAM','JJAS','OND']:
            result=mod.analyze_series(series,metadata|{'season':season,'n_expected':len(series)})
            for field in ['sen_slope','slope_ci','p_value','n_valid','method']:
                if field not in result:raise ValueError('Adapter result lacks '+field)
            results.append(metadata|{'season':season,'result':result})
    output={'input_sha256':hashlib.sha256(pathlib.Path(a.series).read_bytes()).hexdigest(),
            'adapter_sha256':hashlib.sha256(pathlib.Path(a.adapter).read_bytes()).hexdigest(),
            'validation_status':'awaiting_Aadarsh_independent_check','results':results}
    target=pathlib.Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(output,indent=2,allow_nan=False))
    print(target)
if __name__=='__main__':main()
