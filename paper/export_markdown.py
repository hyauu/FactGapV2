"""Export the final LaTeX as readable Markdown after a successful build.
Requires pandoc; numeric citations and cross-references come from main.aux.
The PDF remains the layout-authoritative version.
"""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent
tex = (ROOT / 'main.tex').read_text(encoding='utf-8')
aux = (ROOT / 'main.aux').read_text(encoding='utf-8')
bib = dict(re.findall(r'\\bibcite\{([^}]+)\}\{([^}]+)\}', aux))
refs = dict(re.findall(r'\\newlabel\{([^}]+)\}\{\{([^}]+)\}', aux))

def convert(value: str) -> str:
    return subprocess.run(
        ['pandoc', '-f', 'latex', '-t', 'gfm', '--wrap=none'],
        input=value, text=True, capture_output=True, check=True, cwd=ROOT,
    ).stdout.strip()

s = re.sub(r'\\cite\{([^}]+)\}', lambda m: '[' + ', '.join(bib[x] for x in m[1].split(',')) + ']', tex)
s = re.sub(r'\\ref\{([^}]+)\}', lambda m: refs[m[1]], s)
s = re.sub(r'\\cmidrule(?:\([^)]*\))?\{[^}]+\}', '', s)
s = s.replace(r'\input{bibliography.tex}', '')
abstract = re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', s, re.S)[1].strip()
# Caption bodies may contain braces, math and macros: parse balanced braces.
changes = []
for m in re.finditer(r'\\caption\{', s):
    start = m.end(); depth = 1; j = start
    while depth:
        if j >= len(s):
            raise ValueError('Unclosed caption')
        if s[j] == '{' and s[j-1] != '\\': depth += 1
        if s[j] == '}' and s[j-1] != '\\': depth -= 1
        j += 1
    label = re.match(r'\s*\\label\{([^}]+)\}', s[j:])
    if label:
        key = label[1]
        kind = 'Figure' if key.startswith('fig:') else 'Table'
        changes.append((m.start(), j, r'\par\textbf{' + kind + ' ' + refs[key] + '.} ' + s[start:j-1] + r'\par'))
for a, b, value in reversed(changes): s = s[:a] + value + s[b:]
md = convert(s)
md = re.sub(r'<div[^>]*>\s*|\s*</div>', '', md)
md = re.sub(r'<span class="smallcaps">(.*?)</span>', lambda m:m[1].upper(), md)
md = re.sub(r'<span id="[^"]*"[^>]*></span>', '', md)
md = re.sub(r'<embed src="([^\"]+)\.pdf"[^>]*\s*/>', r'![Result figure](\1.png)', md)
md = re.sub(r'^(#+) ', r'#\1 ', md, flags=re.M)
header = (
    '# FactGap: A Controlled Paired-Ranking Diagnostic for Equivalent Query Reformulations\n\n'
    '**Haoting Qiu**  \nIndependent Researcher, United States  \nqiu.haot@northeastern.edu\n\n'
    '**Qibai Chen**  \nIndependent Researcher, United States  \nqibaic@alumni.cmu.edu\n\n'
    '## Abstract\n\n' + convert(abstract) + '\n\n'
)
entries = []
bs = (ROOT / 'bibliography.tex').read_text(encoding='utf-8')
for key, value in re.findall(r'\\bibitem\{([^}]+)\}(.*?)(?=\\bibitem|\\end\{thebibliography\})', bs, re.S):
    entries.append(f'[{bib[key]}] {convert(value.strip())}')
md = header + md + '\n\n## References\n\n' + '\n\n'.join(entries) + '\n'
(ROOT / 'FactGap_CAIT2026_ALIGN3_8page.md').write_text(md, encoding='utf-8')
print('Markdown export:', len(entries), 'references;', len(changes), 'numbered captions')
