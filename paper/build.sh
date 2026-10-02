#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
cp main.pdf FactGap_CAIT2026_ALIGN3_8page.pdf
printf '\nBuilt FactGap_CAIT2026_ALIGN3_8page.pdf. Check page count after further edits.\n'
