# FactGap — ALIGN3-centered eight-page revision

Main manuscript: **FactGap_CAIT2026_ALIGN3_8page.pdf**.

This revision is based on the supplied complete nine-page source package. It promotes ALIGN3 to the abstract, Introduction, Sections IV–V and Figure 1. Earlier studies remain in the main text and appendices with their original results. No model evaluation or new experiment was performed during this editorial pass.

## Build

A TeX distribution with `IEEEtran`, `newtxtext/newtxmath`, `graphicx`, `booktabs`, `amsmath`, `array`, `multirow`, `hyperref`, `url`, `microtype`, `balance`, and `placeins` is required.

- Linux/macOS: `bash build.sh`
- Windows: `build.bat`
- Optional Markdown export after compilation: `python export_markdown.py` (requires Pandoc).
- Optional source/PDF check: `python verify_document.py` (Python standard library plus PyMuPDF for PDF checks).

The body remains 10 TeX pt on US Letter with the inherited IEEEtran conference geometry. Font files are not bundled. The source builds to eight pages in the checked environment; a different TeX distribution can change line breaking.

## Included

`main.tex`, the unchanged bibliography and both-author record, two used figure assets, source values for the compact original-study chart, build/export/verification scripts, the PDF/Markdown, editorial notes and document checks. `editorial/` holds before/after sources and diffs for the owner; it is not material to copy blindly into a public scientific artifact.

Figure 1 (`operand_alignment.pdf`) is preserved byte-for-byte from the supplied nine-page source. Figure 2 is a single-column redraw of exactly the original temporal table values. This source package is not the full raw experimental repository.

## Repository preparation

The separate `repo_handoff/` files specify the task for Codex in the owner's existing local FactGapV2 folder. No existing Codex thread was messaged by this editing run. No repository was published, shared, or uploaded. The final manuscript deliberately contains no unverified artifact URL.

## Limits

Document-level checks compare this revision with the supplied manuscript and report. They do not certify raw experimental correctness, hosted model identity, new literature coverage, venue submission acceptance, or IEEE PDF eXpress validation. Confirm AI-use disclosures, licensing, manuscript/submission status and the eventual artifact URL before submission. The original nine-page package and older paper versions are unchanged.
