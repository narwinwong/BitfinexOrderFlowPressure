"""Figures from saved E31 development results; no market-source reads."""
from pathlib import Path
import csv
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'evidence/e31'


def main():
    summary=json.loads((OUT/'summary.json').read_text())
    with (OUT/'daily.csv').open() as f:
        rows=list(csv.DictReader(f))
    dates=np.asarray([r['date'] for r in rows],dtype='datetime64[D]')
    fig,ax=plt.subplots(figsize=(9,4.8),layout='constrained')
    for key,label,color in [('d30_f20','Primary: 30s delay, 20bp fee/leg','#b43c39'),
                            ('d30_f0','Same timing, zero fee','#3366aa'),
                            ('d30_f20_baseline','Average-inventory baseline','#777777')]:
        ax.plot(dates,np.cumsum([float(r[key]) for r in rows]),label=label,color=color)
    ax.axhline(0,color='black',lw=.6)
    ax.set(title='E31: realized development PnL',ylabel='Cumulative USD at trade exits',xlabel='2015 UTC date')
    ax.legend(fontsize=8);ax.grid(alpha=.15)
    fig.text(.01,-.035,'Conditional quote fills, 0.01 BTC per trade. No verified size or native fee accounting; confirmation remains sealed.',fontsize=8)
    fig.savefig(ROOT/'figures/e31_equity.png',dpi=160,bbox_inches='tight');plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,4.6),layout='constrained')
    for delay,color in [(10,'#dd8844'),(30,'#3366aa'),(60,'#559977')]:
        cells=[next(c for c in summary['cells'] if c['name']==f'd{delay}_f{fee}') for fee in [0,10,20,30]]
        ax.plot([0,10,20,30],[c['net_pnl_usd'] for c in cells],marker='o',label=f'{delay}s delay',color=color)
    ax.axhline(0,color='black',lw=.6)
    ax.set(title='All registered fee and delay cases lost money',xlabel='Assumed fee per leg (basis points)',ylabel='Six-month net PnL (USD)')
    ax.legend();ax.grid(alpha=.15)
    fig.text(.01,-.035,'Spread paid even at zero fee. Additional 5bp slippage and two noisy-signal cases were also negative.',fontsize=8)
    fig.savefig(ROOT/'figures/e31_cost_latency.png',dpi=160,bbox_inches='tight');plt.close(fig)


if __name__=='__main__':main()
