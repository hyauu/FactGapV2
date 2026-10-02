"""Standalone scientific figure: distinct axes/scales, observed block means, no fabricated intervals."""
from pathlib import Path
import json,os
R=Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR']=str(R/'cache/matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
s=json.loads((R/'analysis/summary.json').read_text(encoding='utf-8'))
keys=['bm25','bge_small','e5_small','minilm_ce'];conditions=['WRONG_ALIGNED','NEUTRAL','GOLD_ALIGNED']
titles=['BM25 (fixed 24-document index)','BGE-small (unscaled cosine)','E5-small (unscaled cosine)','MiniLM cross-encoder (raw logit)']
fig,axes=plt.subplots(2,2,figsize=(10,7),layout='constrained')
for k,title,ax in zip(keys,titles,axes.flat):
 for b in range(12):
  bid=f'eval_block_{b:02d}';vals=[next(x['margin'] for x in s['block_results'] if x['model_key']==k and x['block_id']==bid and x['condition']==c) for c in conditions]
  ax.plot([0,1,2],vals,color='#adb8c3',linewidth=.85,alpha=.75)
 vals=[next(x['primary_template_equal_margin'] for x in s['condition_results'] if x['model_key']==k and x['condition']==c) for c in conditions]
 ax.plot([0,1,2],vals,color='#155c9a',marker='o',linewidth=2.3,label='Four-template equal mean')
 ax.axhline(0,color='#334155',linestyle='--',linewidth=.8)
 ax.set(title=title,ylabel='Gold score minus wrong score',xticks=[0,1,2],xticklabels=['Wrong aligned','Neutral','Gold aligned'])
 ax.grid(axis='y',alpha=.18);ax.spines[['top','right']].set_visible(False)
axes[0,0].legend(loc='best',fontsize=8)
fig.suptitle('ALIGN3: the same interval and candidates, three operand alignments\nThin lines: 12 block means (two wordings each). Separate model scales; no confidence intervals.',fontsize=11)
for ext in ['png','svg']:fig.savefig(R/f'analysis/ALIGN3_MARGIN.{ext}',dpi=180)
plt.close(fig)
