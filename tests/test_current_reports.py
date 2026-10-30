"""Publication integrity for the twelve current author reports."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/build_current_reports.py'
spec = importlib.util.spec_from_file_location('build_current_reports', SCRIPT)
reports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reports)


class CurrentReportsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.edition_dir = self.root / 'inputs/revised_expertises/edition-2026-10-30'
        self.edition_dir.mkdir(parents=True)
        records = []
        for identity in reports.EXPECTED_PROJECTS:
            source = self.edition_dir / (identity + '.docx')
            with zipfile.ZipFile(source, 'w') as archive:
                archive.writestr('word/document.xml', f'<document>{identity}</document>')
            pdf_url = f'downloads/projects/{identity}/current/{identity}.pdf'
            docx_url = f'downloads/projects/{identity}/current/{identity}.docx'
            pdf = self.root / 'public' / pdf_url
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(('%PDF-1.7\n' + identity + '\n%%EOF\n').encode())
            records.append({
                'project_id': identity, 'title': identity, 'edition_date': reports.EDITION,
                'edition_label': 'Редакция от 30 октября 2026 года',
                'source_docx': source.relative_to(self.root).as_posix(),
                'pdf': {'url': pdf_url, 'filename': pdf.name, 'bytes': pdf.stat().st_size,
                        'sha256': reports.sha256(pdf), 'pages': 1},
                'docx': {'url': docx_url, 'filename': identity + '.docx',
                         'bytes': source.stat().st_size, 'sha256': reports.sha256(source)},
                'provenance': {'docx_modified': False},
            })
        self.manifest = {'schema': reports.SCHEMA, 'edition_date': reports.EDITION,
                         'source_archive': {'filename': 'author-edition.zip'}, 'reports': records}
        self.write_manifest()

    def write_manifest(self):
        (self.edition_dir / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def test_all_projects_publish_original_docx_and_stable_registry(self):
        first = reports.build(self.root)
        registry = self.root / 'public/data/current-reports.json'
        original_bytes = registry.read_bytes()
        original_mtime = registry.stat().st_mtime_ns
        for report in first['reports']:
            published = self.root / 'public' / report['docx']['url']
            self.assertEqual(reports.sha256(published), report['docx']['sha256'])
        second = reports.build(self.root)
        self.assertEqual(first, second)
        self.assertEqual(original_bytes, registry.read_bytes())
        self.assertEqual(original_mtime, registry.stat().st_mtime_ns)

    def test_modified_pdf_rejects_complete_edition_before_any_publication(self):
        last = self.manifest['reports'][-1]
        pdf = self.root / 'public' / last['pdf']['url']
        pdf.write_bytes(pdf.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            reports.build(self.root)
        self.assertFalse((self.root / 'public/data/current-reports.json').exists())
        self.assertFalse(any((self.root / 'public').rglob('*.docx')))

    def test_missing_project_or_modified_author_docx_is_not_silently_accepted(self):
        original = self.manifest['reports'][:]
        self.manifest['reports'] = original[:-1]
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, '12 projects'):
            reports.build(self.root)
        self.manifest['reports'] = original
        self.write_manifest()
        source = self.root / original[0]['source_docx']
        source.write_bytes(source.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            reports.build(self.root)

    def test_path_escape_is_rejected(self):
        self.manifest['reports'][0]['source_docx'] = '../outside.docx'
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'outside project root'):
            reports.build(self.root)


if __name__ == '__main__':
    unittest.main()
