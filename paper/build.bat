@echo off
setlocal
pushd "%~dp0"
pdflatex -interaction=nonstopmode -halt-on-error main.tex
if errorlevel 1 exit /b 1
pdflatex -interaction=nonstopmode -halt-on-error main.tex
if errorlevel 1 exit /b 1
copy /y main.pdf FactGap_CAIT2026_ALIGN3_8page.pdf
popd
endlocal
