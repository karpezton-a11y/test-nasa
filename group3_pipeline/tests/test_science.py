"""Synthetic test inputs verify methods. They are never research observations."""
import json,pathlib,tempfile,unittest
import numpy as np
import pandas as pd
from analysis.methods import canonical_unit,align_series,daily_temporal_coverage,monthly_anomalies,rainfall_indicators,combined_flags
from analysis.io import read_export
from run_pipeline import main

class ScientificChecks(unittest.TestCase):
    def test_monthly_conversion_leap_year(self):
        s=pd.Series([1.,1.],index=pd.to_datetime(['2020-02-01','2021-02-01']))
        out,u=canonical_unit(s,'rainfall','month','mm/hr')
        self.assertEqual(out.tolist(),[696.,672.]);self.assertEqual(u,'mm/month')
    def test_no_double_conversion(self):
        s=pd.Series([100.],index=pd.to_datetime(['2020-01-01']))
        self.assertEqual(canonical_unit(s,'rainfall','month','mm/month')[0].iloc[0],100.)
    def test_daily_units_unchanged(self):
        s=pd.Series([10.]);self.assertEqual(canonical_unit(s,'rainfall','day','mm/day')[0].iloc[0],10.)
    def test_unknown_units_rejected(self):
        with self.assertRaises(ValueError):canonical_unit(pd.Series([1]),'rainfall','month','unknown')
    def test_gap_remains_missing(self):
        s=pd.Series([0.,2.],index=pd.to_datetime(['2020-01-01','2020-03-01']))
        r=align_series(s,'2020-01-01','2020-03-01','month')
        self.assertTrue(pd.isna(r.iloc[1]));self.assertEqual(r.iloc[0],0)
    def test_duplicate_rejected(self):
        s=pd.Series([1,2],index=pd.to_datetime(['2020-01-01','2020-01-20']))
        with self.assertRaises(ValueError):align_series(s,'2020-01-01','2020-02-01','month')
    def test_coverage_counts_calendar_days(self):
        s=pd.Series(1.,index=pd.date_range('2020-02-01','2020-02-29'));s.iloc[:9]=np.nan
        self.assertAlmostEqual(daily_temporal_coverage(s).iloc[0],20/29)
    def test_missing_coverage_blocks_rain_flags(self):
        s=pd.Series(np.arange(264.),index=pd.date_range('2003-01-01',periods=264,freq='MS'))
        a=monthly_anomalies(s,'rainfall')
        self.assertTrue(a.category.eq('not_evaluated').all())
    def test_normally_dry_baseline(self):
        dates=pd.date_range('2003-01-01',periods=264,freq='MS')
        s=pd.Series(5.,index=dates);s.loc['2024-01-01']=0
        a=monthly_anomalies(s,'rainfall',pd.Series(1.,index=dates))
        self.assertNotIn('unusually_dry',set(a.category))
    def test_aod_zero_variation_safe(self):
        s=pd.Series(.4,index=pd.date_range('2003-01-01',periods=264,freq='MS'))
        a=monthly_anomalies(s,'aod');self.assertTrue(a.score.isna().all())
        self.assertTrue(a.evaluation_status.eq('insufficient_variation').all())
    def test_aod_log_edge(self):
        s=pd.Series(.4,index=pd.date_range('2003-01-01',periods=264,freq='MS'));s.iloc[0]=0;s.iloc[1]=-1
        a=monthly_anomalies(s,'aod');self.assertEqual(a.evaluation_status.eq('undefined_log').sum(),2)
    def test_extreme_aod_flag(self):
        dates=pd.date_range('2003-01-01',periods=264,freq='MS')
        s=pd.Series(np.exp(np.tile(np.linspace(-1.1,-.9,22),12).reshape(12,22).T.ravel()),index=dates)
        s.iloc[-1]=5.
        a=monthly_anomalies(s,'aod');self.assertEqual(a.iloc[-1].category,'unusually_high_aod')
    def test_dry_spell_missing_break(self):
        s=pd.Series(10.,index=pd.date_range('2020-01-01','2020-12-31'));s.iloc[:10]=0;s.iloc[4]=np.nan
        ind=rainfall_indicators(s,seasons=['ALL'])
        self.assertEqual(ind[ind.indicator=='longest_dry_spell'].value.iloc[0],5.)
    def test_incomplete_year_null(self):
        s=pd.Series(2.,index=pd.date_range('2020-01-01','2020-12-31'));s.iloc[:30]=np.nan
        self.assertTrue(rainfall_indicators(s,seasons=['ALL']).value.isna().all())
    def test_no_wet_day_denominator(self):
        s=pd.Series(0.,index=pd.date_range('2020-01-01','2020-12-31'))
        ind=rainfall_indicators(s,seasons=['ALL'])
        self.assertTrue(pd.isna(ind[ind.indicator=='heavy_rain_share'].value.iloc[0]))
        self.assertEqual(ind[ind.indicator=='longest_dry_spell'].value.iloc[0],366.)
    def test_season_boundaries(self):
        s=pd.Series(0.,index=pd.date_range('2020-01-01','2020-12-31'))
        ind=rainfall_indicators(s,seasons=['JJAS','OND'])
        self.assertEqual(ind[(ind.season=='JJAS')&(ind.indicator=='longest_dry_spell')].value.iloc[0],122.)
        self.assertEqual(ind[(ind.season=='OND')&(ind.indicator=='longest_dry_spell')].value.iloc[0],92.)
    def test_percent_share_known(self):
        s=pd.Series(1.,index=pd.date_range('2021-01-01','2021-12-31'));s.iloc[0]=100
        ind=rainfall_indicators(s,seasons=['ALL'])
        self.assertAlmostEqual(ind[ind.indicator=='heavy_rain_share'].value.iloc[0],100*100/464)
    def test_combined_flags(self):
        r=pd.DataFrame([{'date':pd.Timestamp('2020-01-01'),'category':'unusually_dry'}])
        a=pd.DataFrame([{'date':pd.Timestamp('2020-01-01'),'category':'unusually_high_aod'}])
        self.assertEqual(combined_flags(r,a).category.iloc[0],'dry_and_high_aod')
    def test_csv_metadata_and_fill(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=pathlib.Path(tmp)/'input.csv';p.write_text('Example test header\nDate,Rain\n2020-01-01,0\n2020-02-01,-9999\n')
            e=dict(path='input.csv',region_id='IGP',variable='rainfall',frequency='month',source_id='TEST_ONLY',unit='mm/month',date_column='Date',value_column='Rain',source_url='test-only',bbox=[76,24,88,30],source_variable='precipitation',product='test-only',version='test-only',accessed_at='test-only',fill_values=[-9999])
            d,prov=read_export(e,tmp,'2020-01-01','2020-02-01')
            self.assertEqual(d.value.iloc[0],0);self.assertTrue(pd.isna(d.value.iloc[1]));self.assertEqual(prov['fill_values_removed'],1)
    def test_empty_inputs_never_fake_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=pathlib.Path(tmp)/'inputs.json';p.write_text(json.dumps({'inputs':[]}))
            code=main(['--manifest',str(p),'--output',tmp+'/out'])
            self.assertEqual(code,2);self.assertFalse((pathlib.Path(tmp)/'out/timeseries_monthly.csv').exists())
    def test_full_test_only_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            dates=pd.date_range('2003-01-01',periods=264,freq='MS')
            pd.DataFrame({'Date':dates,'AOD':np.linspace(.2,.6,264)}).to_csv(pathlib.Path(tmp)/'input.csv',index=False)
            e=dict(path='input.csv',region_id='IGP',variable='aod',frequency='month',source_id='TEST_ONLY',unit='1',date_column='Date',value_column='AOD',source_url='test-only',bbox=[76,24,88,30],source_variable='test-only',product='test-only',version='test-only',accessed_at='test-only')
            cfg={'start':'2003-01-01','end':'2024-12-31','data_version':'test-only','inputs':[e],'primary_source_ids':['TEST_ONLY']}
            p=pathlib.Path(tmp)/'inputs.json';p.write_text(json.dumps(cfg))
            self.assertEqual(main(['--manifest',str(p),'--output',tmp+'/out']),0)
            self.assertEqual(len(pd.read_csv(pathlib.Path(tmp)/'out/timeseries_monthly.csv')),264)
    def test_nonoverlapping_chunks_join_without_filling_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            (root/'a.csv').write_text('Date,Rain\n2020-01-01,10\n2020-02-01,20\n')
            (root/'b.csv').write_text('Date,Rain\n2020-04-01,40\n')
            common=dict(region_id='IGP',variable='rainfall',frequency='month',source_id='TEST_ONLY',unit='mm/month',date_column='Date',value_column='Rain',source_url='test-only',bbox=[76,24,88,30],source_variable='precipitation',product='test-only',version='test-only',accessed_at='test-only')
            cfg={'start':'2020-01-01','end':'2020-04-30','data_version':'test-only','inputs':[common|{'path':'a.csv'},common|{'path':'b.csv'}]}
            p=root/'inputs.json';p.write_text(json.dumps(cfg))
            self.assertEqual(main(['--manifest',str(p),'--output',str(root/'out')]),0)
            result=pd.read_csv(root/'out/timeseries_monthly.csv')
            self.assertEqual(result.value.iloc[0],10);self.assertTrue(pd.isna(result.value.iloc[2]));self.assertEqual(result.value.iloc[3],40)

if __name__=='__main__':unittest.main()
