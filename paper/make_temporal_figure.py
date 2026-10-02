"""Redraw the original temporal table as a single-column figure; no model calls."""
from pathlib import Path
import csv
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
with (ROOT/'source_data/original_temporal_compact.csv').open(newline='',encoding='utf-8') as f:
    rows=list(csv.reader(f))[1:]
with plt.rc_context({'pdf.fonttype':42,'ps.fonttype':42}):
    fig,ax=plt.subplots(figsize=(3.48,2.85))
    for row,marker in zip(rows,['o','s','^','D','v']):
        ax.plot(['D0','D1','P0','P1'],list(map(float,row[1:])),marker=marker,
                markersize=3.5,linewidth=1.2,label=row[0])
    ax.set_ylabel('Family-weighted pair accuracy (%)',fontsize=8)
    ax.set_ylim(-4,105);ax.set_yticks([0,20,40,60,80,100]);ax.tick_params(labelsize=8)
    ax.grid(axis='y',alpha=0.22)
    ax.legend(loc='lower center',bbox_to_anchor=(.5,1.03),ncol=2,frameon=False,
              fontsize=7.5,handlelength=1.5,columnspacing=.9)
    fig.tight_layout(pad=.5)
    for ext in ('pdf','png'):
        fig.savefig(ROOT/'figures'/f'original_temporal_compact.{ext}',dpi=220,bbox_inches='tight')
    plt.close(fig)
