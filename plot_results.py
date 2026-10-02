"""Render empirical figures from regenerated numerical tables."""
from pathlib import Path
import argparse,csv,json
from fractions import Fraction
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--analysis',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9})
    def save(fig,name):
        for ext in ['svg','png']:fig.savefig(a.out/(name+'.'+ext),dpi=200,bbox_inches='tight')
        plt.close(fig)
    completion={r['method']:r for r in rows(a.analysis/'final/completion_high_h.csv')}
    methods=['A0','A1','A2'];counts=[int(completion[m]['all_six_numeric_optimal_conditions']) for m in methods]
    fig,ax=plt.subplots(figsize=(3.55,2.65));ax.bar(range(3),counts,color=['#9ca4ac','#24649a','#829dad'])
    for i,v in enumerate(counts):ax.text(i,v+1.5,f'{v}/85',ha='center',fontsize=8)
    ax.set_xticks(range(3),['Global MILP\nbaseline','Preprocessed\nglobal MILP','Preprocessed\ncomponent MILP'],fontsize=7)
    ax.set_ylabel('Completed conditions');ax.set_ylim(0,96);ax.spines[['top','right']].set_visible(False);fig.tight_layout();save(fig,'completion')
    gaps=[r for r in rows(a.analysis/'final/all_u_gap_by_h.csv') if r['scope']=='target_100k_matched']
    charges=[float(Fraction(r['h'])) for r in gaps];values=[float(r['AllU_gap_median_percent']) for r in gaps]
    fig,axs=plt.subplots(1,2,figsize=(7.1,2.7))
    for ax,x,y,title in [(axs[0],charges,values,'All measured charges'),(axs[1],charges[:5],values[:5],r'$1\leq h\leq 2$ detail')]:
        ax.plot(x,y,'o--',color='#24649a',lw=1,ms=4);ax.set_title(title);ax.set_xlabel('Definition charge $h$');ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.25)
    axs[0].set_xscale('log',base=2);axs[0].set_xticks([1,2,4,8,16,32],[1,2,4,8,16,32]);axs[0].set_ylabel('Maximal sharing excess cost (%)')
    fig.tight_layout();save(fig,'all_u_gap')
    paired=rows(a.analysis/'comparison/paired_times.csv');sources=['matplotlib','pydantic','aiohttp','jsonschema']
    groups=[[float(r['ratio']) for r in paired if r['comparison']=='A0/A1' and r['eligible']=='True' and r['distribution']==s] for s in sources]
    fig,ax=plt.subplots(figsize=(3.5,2.7));box=ax.boxplot(groups,positions=range(4),widths=.48,whis=(0,100),patch_artist=True,showfliers=False)
    for patch in box['boxes']:patch.set(facecolor='#dbe9f6',edgecolor='#294d6b')
    for i,g in enumerate(groups):ax.scatter(i+np.linspace(-.13,.13,len(g)),sorted(g),s=10,color='#294d6b',alpha=.7,zorder=3)
    ax.axhline(1,color='#777777',ls='--',lw=.8);ax.set_xticks(range(4),[s+'\n(n='+str(len(g))+')' for s,g in zip(sources,groups)],fontsize=7.5)
    ax.set_ylabel('Speedup from preprocessing\nthe global MILP');ax.set_ylim(bottom=0);ax.spines[['top','right']].set_visible(False);fig.tight_layout();save(fig,'source_time_ratios')
    (a.out/'values.json').write_text(json.dumps({'completion':counts,'charges':charges,'gaps':values,'paired_counts':list(map(len,groups))},indent=2),encoding='utf-8')
if __name__=='__main__':main()
