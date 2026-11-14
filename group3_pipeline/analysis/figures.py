"""Publication-style figures generated only from supplied observations."""
import pathlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

COLORS={'IGP':'#147d92','TN':'#c45a2f'}
def build_figures(data,out,indicators=None,anomalies=None):
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    monthly=data[data.frequency=='month']
    for (variable,source),g in monthly.groupby(['variable','source_id']):
        fig,ax=plt.subplots(figsize=(11,4.8),layout='constrained')
        for region,r in g.groupby('region_id'):
            ax.plot(r.date,r.value,label=region,color=COLORS.get(region),lw=1.3)
        ax.set(title=f'{variable.upper()} monthly regional observations',ylabel=g.unit.iloc[0],xlabel='UTC month')
        ax.legend();ax.grid(alpha=.18);fig.savefig(out/f'{source}_timeseries.png',dpi=180);plt.close(fig)
        fig,ax=plt.subplots(figsize=(9,4.8),layout='constrained')
        for region,r in g.groupby('region_id'):
            c=r.groupby(r.date.dt.month).value.mean()
            ax.plot(c.index,c.values,'o-',label=region,color=COLORS.get(region))
        ax.set(title=f'{variable.upper()} calendar-month climatology',ylabel=g.unit.iloc[0],xlabel='Calendar month',xticks=range(1,13))
        ax.legend();ax.grid(alpha=.18);fig.savefig(out/f'{source}_climatology.png',dpi=180);plt.close(fig)
        fig,axes=plt.subplots(max(1,g.region_id.nunique()),1,figsize=(11,3.8),squeeze=False,layout='constrained')
        for ax,(region,r) in zip(axes.ravel(),g.groupby('region_id')):
            ax.bar(r.date,r.valid_fraction,width=25,color=COLORS.get(region));ax.set(ylim=(0,1),ylabel=region)
            ax.axhline(.3,c='#aa3030',ls='--',lw=1);ax.set_title('Temporal coverage; blank means unknown' if r.valid_fraction.notna().sum()==0 else 'Valid regional days / calendar days')
        fig.savefig(out/f'{source}_coverage.png',dpi=180);plt.close(fig)
    if indicators is not None:
        for (indicator,season),g in indicators.groupby(['indicator','season']):
            fig,ax=plt.subplots(figsize=(10,4.5),layout='constrained')
            for region,r in g.groupby('region_id'):ax.plot(r.year,r.value,'o-',label=region,color=COLORS.get(region))
            ax.set(title=f'{indicator.replace("_"," ").title()} ({season})',ylabel=g.unit.iloc[0],xlabel='Year');ax.legend();ax.grid(alpha=.18)
            fig.savefig(out/f'{indicator}_{season}.png',dpi=180);plt.close(fig)
    if anomalies is not None:
        for (region,variable,source),g in anomalies.groupby(['region_id','variable','source_id']):
            fig,ax=plt.subplots(figsize=(10,4.6),layout='constrained')
            ax.plot(g.date,g.value,color='#5c7182',lw=1)
            flags=g[g.category.str.startswith('unusually')]
            ax.scatter(flags.date,flags.value,color='#c45a2f',s=30,label='Flagged observation',zorder=3)
            ax.set(title=f'{region} {variable}: same-month anomaly flags',xlabel='Date');ax.legend();ax.grid(alpha=.18)
            fig.savefig(out/f'{region}_{source}_anomalies.png',dpi=180);plt.close(fig)

