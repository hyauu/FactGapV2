"""Document-level invariants; does not replay experimental scores or call models.
Run after build.sh/build.bat. PyMuPDF is optional for PDF layout checks.
"""
from pathlib import Path
from collections import Counter
import csv, hashlib, json, re

ROOT = Path(__file__).resolve().parent
old = (ROOT/'editorial/BASELINE_9PAGE_MAIN.tex').read_text(encoding='utf-8')
new = (ROOT/'main.tex').read_text(encoding='utf-8')
checks = []

def record(name, ok, detail):
    checks.append({'check':name,'pass':bool(ok),'detail':detail})

def canonical(text):
    return re.sub(r'\s+', '', text)

def body(source, label):
    pos = source.index(r'\label{'+label+'}')
    a = source.index(r'\begin{tabular}',pos)
    b = source.index(r'\end{tabular}',a)+len(r'\end{tabular}')
    return canonical(source[a:b])

labels=['tab:alignment','tab:boundary','tab:hosted','tab:examples',
        'tab:original','tab:endpoints','tab:margins','tab:templates','tab:parser']
for label in labels:
    record(label,body(old,label)==body(new,label),
           'Exact tabular content retained after whitespace normalization; numbering/placement may change.')
eq = lambda text: Counter(canonical(x) for x in re.findall(
    r'\\begin\{equation\}([\s\S]*?)\\end\{equation\}',text))
record('all_four_equations',eq(old)==eq(new) and sum(eq(new).values())==4,
       'Equation content is unchanged; alignment example precedes the original joint statistic in the new order.')
keys=lambda text:set(k.strip() for block in re.findall(r'\\cite\{([^}]+)\}',text) for k in block.split(','))
record('citation_keys',keys(old)==keys(new) and len(keys(new))==10,'All ten keys retained.')
record('author_and_preamble',canonical(old.split(r'\begin{abstract}')[0])==canonical(new.split(r'\begin{abstract}')[0]),
       'Title, both authors/emails, IEEEtran class, font and geometry settings unchanged after whitespace normalization.')
record('no_artificial_spacing',not re.search(r'\\(?:vspace|enlargethispage|linespread|fontsize|geometry)\b',new),
       'No margin/leading reduction, page enlargement or manual negative-space command.')
record('narrative_em_dashes',not ('---' in new or '\u2014' in new),
       'Template-generated abstract separator is outside narrative text.')
record('no_repository_claim',not re.search(r'https?://(?:github|gitlab|zenodo)|we (?:release|have released)',new,re.I),
       'No unverified repository URL or public-release assertion added.')
required=['0/7','INCONCLUSIVE','0/32','+0.059769','+0.048645','0.011124',
          '50,000','1729','0.003571','0.996429','3.208','0.222','0.080','0.022',
          '1,152','768','436','432','1,408','352','40','36']
record('critical_values',all(x in new for x in required),{'required':required})
# Validate the new compact plot data against the original accuracy table.
expected=[['BGE-base','100.0','100.0','0.0','5.2'],['E5-base','94.0','98.8','4.8','7.3'],
          ['Qwen3 embed.','96.2','98.6','2.6','3.8'],['BGE reranker','100.0','100.0','1.2','3.6'],
          ['MiniLM CE','63.7','70.6','26.4','8.9']]
with (ROOT/'source_data/original_temporal_compact.csv').open(newline='',encoding='utf-8') as f:
    values=list(csv.reader(f))[1:]
record('compact_temporal_plot_values',values==expected,'Five models by four forms, matching original table values.')
try:
    import fitz
    pdf=ROOT/'FactGap_CAIT2026_ALIGN3_8page.pdf'
    with fitz.open(pdf) as d:
        record('page_count',len(d)==8,{'pages':len(d)})
        record('letter_page_boxes',all(abs(p.rect.width-612)<.01 and abs(p.rect.height-792)<.01 for p in d),'US Letter on all pages.')
        outside=[];body_sizes=Counter();fonts={}
        for i,p in enumerate(d):
            for f in p.get_fonts(full=True):fonts[f[0]]=f
            for block in p.get_text('dict')['blocks']:
                for line in block.get('lines',[]):
                    for span in line.get('spans',[]):
                        x0,y0,x1,y1=span['bbox']
                        if x0 < -0.1 or y0 < -0.1 or x1 > 612.1 or y1 > 792.1:
                            outside.append({'page':i+1,'bbox':span['bbox'],'text':span['text']})
                        if 'TermesX-Regular' in span['font']:
                            body_sizes[round(span['size'],3)]+=len(span['text'])
        record('text_inside_pages',not outside,{'outside':outside})
        record('body_10_tex_pt',any(abs(sz-9.963)<.02 for sz in body_sizes),dict(body_sizes))
        missing=[];type3=[]
        for xref,f in fonts.items():
            if f[2]=='Type3':type3.append(xref)
            if not d.extract_font(xref)[3]:missing.append(xref)
        record('embedded_fonts',not missing and not type3,{'font_count':len(fonts),'unembedded':missing,'type3':type3})
        text='\n'.join(p.get_text() for p in d)
        record('rendered_authors',all(x in text for x in ['Haoting Qiu','Qibai Chen','qiu.haot@northeastern.edu','qibaic@alumni.cmu.edu']),
               'Both author names and emails are present in extracted PDF text.')
except ImportError:
    record('pdf_checks_available',False,'PyMuPDF is not installed; inspect PDF separately.')
log=(ROOT/'main.log').read_text(errors='replace')
record('latex_no_overflow_or_unresolved',not re.search(r'Overfull|undefined|multiply defined',log,re.I),
       'No overfull box, undefined reference/citation, or duplicate-label warning. Minor underfull spacing is not treated as content failure.')
result={'status':'PASS' if all(c['pass'] for c in checks) else 'FAIL','checks':checks,
        'limits':'Document-to-source validation only. No raw experimental replay, new model execution, novelty audit, release creation or submission validation.'}
(ROOT/'checks/DOCUMENT_CHECKS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(result['status'],len(checks),'checks')
for c in checks:
    if not c['pass']:print(c)
raise SystemExit(0 if result['status']=='PASS' else 1)
