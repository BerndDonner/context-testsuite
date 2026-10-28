# Real PDF extraction parity corpus

Eight independent pages in each PDF (`reference.pdf` = original upstream,
`candidate.pdf` = Hans 2026-10-28), selected from the user's completed
`hans-design-v3` run, same context-src revision 5751e39641a5.

Ordered IDs: A0419, A0452, A0470, A0527, A0554, A0590, A0592, A0593.

`expected.json` records the observed join/split classification for each page.
These are **golden observations**, not claims about correct TeX semantics.

The pytest module tests (a) sorted PyMuPDF text extraction, (b) PyMuPDF
geometrical line grouping using the PDF word block/line indices, and
(c) Poppler `pdftotext -layout` agreement when Poppler is available.

The aim is to determine whether Poppler can be removed from the production
runner in a future **separately approved** refactoring. This test adds no
new runtime dependency and does not modify the production extractor.

Do not change the saved expected results just because an engine update changes
a contemporary test output. A disagreement with these files means either a
PDF analyzer regression or intentionally replaced corpus data.
