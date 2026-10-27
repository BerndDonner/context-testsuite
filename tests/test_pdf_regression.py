import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import sys

import pymupdf

from context_testsuite.pdf import compare, compare_files, pdf_relpath


def make_pdf(path, texts, width=595, height=842):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    for index, text in enumerate(texts):
        page = doc.new_page(width=width, height=height)
        page.insert_text((50, 100), text, fontsize=12)
        if index == 0:
            page.draw_rect(pymupdf.Rect(70, 250, 150, 330), color=(0.1, 0.2, 0.3))
    doc.save(path)
    doc.close()


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.built, self.installed, self.out = [base / x for x in ('build', 'installed', 'out')]
        self.rel = pdf_relpath('Fach/Aufgabenblatt.pdf')
        make_pdf(self.installed / 'Fach/Aufgabenblatt.pdf', ['Hallo Welt', 'Seite zwei'])
        make_pdf(self.built / 'Fach/Aufgabenblatt.pdf', ['Hallo Welt', 'Seite zwei'])

    def test_identical_visual_even_different_metadata(self):
        data, folder = compare(self.rel, self.built, self.installed, self.out, 92, 16)
        self.assertEqual('identical', data['status'])
        self.assertEqual(0, data['summary']['pages_visual_changed'])
        self.assertTrue((folder / 'report.html').exists())

    def test_text_changed_and_visual_diff(self):
        make_pdf(self.built / 'Fach/Aufgabenblatt.pdf', ['Neuer Text', 'Seite zwei'])
        data, folder = compare(self.rel, self.built, self.installed, self.out, 92, 16)
        self.assertEqual('changed', data['status'])
        self.assertEqual(1, data['summary']['pages_text_changed'])
        self.assertEqual(1, data['summary']['pages_visual_changed'])
        self.assertTrue((folder / 'text.diff').exists())
        self.assertTrue((folder / 'page-001-diff.png').exists())
        self.assertFalse((folder / 'page-002-diff.png').exists())
        self.assertEqual(2, len(json.loads((folder / 'report.json').read_text())['pages']))

    def test_page_count(self):
        make_pdf(self.built / 'Fach/Aufgabenblatt.pdf', ['Hallo Welt'])
        data, folder = compare(self.rel, self.built, self.installed, self.out, 92, 16)
        self.assertEqual('changed', data['status'])
        self.assertEqual(2, len(data['pages']))
        self.assertEqual('Build', data['pages'][1]['missing_side'])

    def test_geometry(self):
        make_pdf(self.built / 'Fach/Aufgabenblatt.pdf', ['Hallo Welt', 'Seite zwei'], width=620)
        data, folder = compare(self.rel, self.built, self.installed, self.out, 92, 16)
        self.assertEqual('changed', data['status'])
        self.assertEqual(2, data['summary']['pages_geometry_changed'])
        self.assertIsNone(data['pages'][0]['diff_image'])

    def test_missing_baseline(self):
        (self.installed / 'Fach/Aufgabenblatt.pdf').unlink()
        data, folder = compare(self.rel, self.built, self.installed, self.out, 92, 16)
        self.assertEqual('baseline_missing', data['status'])
        self.assertTrue((folder / 'report.html').exists())

    def test_clears_stale_diff(self):
        make_pdf(self.built / 'Fach/Aufgabenblatt.pdf', ['Unterschied', 'Seite zwei'])
        data, folder = compare(self.rel, self.built, self.installed, self.out, 92, 16)
        self.assertTrue((folder / 'text.diff').exists())
        make_pdf(self.built / 'Fach/Aufgabenblatt.pdf', ['Hallo Welt', 'Seite zwei'])
        data, folder = compare(self.rel, self.built, self.installed, self.out, 92, 16)
        self.assertFalse((folder / 'text.diff').exists())
        self.assertFalse((folder / 'page-001-diff.png').exists())


    def test_image_only_change(self):
        # Identical text, but a changed colored rectangle on page 1.
        path = self.built / 'Fach/Aufgabenblatt.pdf'
        doc = pymupdf.open()
        for i, t in enumerate(['Hallo Welt', 'Seite zwei']):
            page = doc.new_page(width=595, height=842)
            page.insert_text((50, 100), t, fontsize=12)
            if i == 0:
                page.draw_rect(pymupdf.Rect(70, 250, 150, 330), color=(0.9, 0.1, 0.1))
        doc.save(path)
        doc.close()
        data, folder = compare(self.rel, self.built, self.installed, self.out, 92, 16)
        self.assertEqual('changed', data['status'])
        self.assertEqual(0, data['summary']['pages_text_changed'])
        self.assertEqual(1, data['summary']['pages_visual_changed'])
        self.assertTrue((folder / 'page-001-diff.png').exists())

    def test_corrupt_pdf_does_not_remove_previous_report(self):
        _, folder = compare(self.rel, self.built, self.installed, self.out, 92, 16)
        old_html = (folder / 'report.html').read_text()
        (self.built / 'Fach/Aufgabenblatt.pdf').write_text('not PDF!')
        with self.assertRaises((RuntimeError, ValueError, OSError)):
            compare(self.rel, self.built, self.installed, self.out, 92, 16)
        self.assertEqual(old_html, (folder / 'report.html').read_text())

    def test_path_safety(self):
        for raw in ['../../tmp/evil.pdf', '/tmp/x.pdf', 'a/../x.pdf', 'a//b.pdf', 'a\\b.pdf', 'hello.tex', '']:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    pdf_relpath(raw)

if __name__ == '__main__':
    unittest.main()
