"""Lossless, isolated and bounded publication builds."""

from pathlib import Path
import gzip
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('build_pages', ROOT / 'scripts/build_pages.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class PagesBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='nationalprojects-pages-test-')
        self.base = Path(self.temporary.name)
        self.source = self.base / 'docs'
        self.output = self.base / 'publication'
        self.report = self.base / 'verification.json'
        self.relative = 'data/projects/example/series/62900.json'
        self.source_file = self.source / self.relative
        self.source_file.parent.mkdir(parents=True)
        # Preserve numeric spelling too: parsing and reserializing this JSON
        # would change several lexemes even if ordinary values compared equal.
        self.raw = ('{\n  "observations": [123456789012345678901234567890, '
                    '-0, 0.00, 1.2500e+03],\n  "text": "Туризм \\\"2026\\\"", '
                    '"escaped": "\\u0420\\u0424"\n}\n').encode('utf-8')
        json.loads(self.raw)
        self.source_file.write_bytes(self.raw)
        (self.source / '.nojekyll').write_bytes(b'')
        (self.source / 'index.html').write_bytes(b'<!doctype html>\n<html><head><title>Study</title></head><body>OK</body></html>\n')
        (self.source / 'assets').mkdir()
        (self.source / 'assets/info.txt').write_bytes(b'Unchanged static asset.\n')
        (self.source / 'data/.rsync-partial').mkdir()
        (self.source / 'data/.rsync-partial/unfinished.json').write_bytes(b'{broken')
        (self.source / 'data/unpublished.tmp').write_bytes(b'not a publication')

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def contents(directory):
        return {p.relative_to(directory).as_posix(): p.read_bytes()
                for p in directory.rglob('*') if p.is_file()}

    def test_roundtrip_preserves_raw_lexemes_and_records_physical_hashes(self):
        report = builder.build(self.source, self.output, report_path=self.report)
        manifest = json.loads((self.output / builder.MANIFEST_PATH).read_text())
        self.assertEqual(manifest['schema'], builder.MANIFEST_SCHEMA)
        self.assertEqual(len(manifest['files']), 1)
        record = manifest['files'][0]
        compressed = (self.output / record['compressed_path']).read_bytes()
        self.assertEqual(gzip.decompress(compressed), self.raw)
        self.assertEqual(record['path'], self.relative)
        self.assertEqual(record['bytes'], len(self.raw))
        self.assertEqual(record['sha256'], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(record['compressed_bytes'], len(compressed))
        self.assertEqual(record['compressed_sha256'], hashlib.sha256(compressed).hexdigest())
        self.assertEqual(json.loads((self.output / self.relative).read_text()),
                         {'schema': builder.REDIRECT_SCHEMA, **record})
        self.assertEqual((self.output / 'index.html').read_bytes().count(builder.META), 1)
        self.assertNotIn(builder.META, (self.source / 'index.html').read_bytes())
        self.assertFalse((self.output / 'data/.rsync-partial').exists())
        self.assertFalse((self.output / 'data/unpublished.tmp').exists())
        self.assertEqual(report['output_bytes'], sum(len(b) for b in self.contents(self.output).values()))
        self.assertEqual(json.loads(self.report.read_text()), report)
        self.assertTrue(all(report['checks'].values()))

    def test_link_mode_does_not_mutate_shared_source_inodes(self):
        before = self.contents(self.source)
        alias_series = self.base / 'public-series.json'
        alias_index = self.base / 'public-index.html'
        os.link(self.source_file, alias_series)
        os.link(self.source / 'index.html', alias_index)
        report = builder.build(self.source, self.output, link=True)
        self.assertEqual(self.contents(self.source), before)
        self.assertEqual(alias_series.read_bytes(), self.raw)
        self.assertEqual(alias_index.read_bytes(), before['index.html'])
        self.assertEqual((self.output / 'assets/info.txt').stat().st_ino,
                         (self.source / 'assets/info.txt').stat().st_ino)
        self.assertNotEqual((self.output / self.relative).stat().st_ino, self.source_file.stat().st_ino)
        self.assertNotEqual((self.output / 'index.html').stat().st_ino,
                            (self.source / 'index.html').stat().st_ino)
        self.assertEqual(report['gzip_roundtrips_verified'], 1)
        self.assertEqual(report['source_files_verified_unchanged'], 4)

    def test_size_gate_rejects_before_replacing_a_valid_publication(self):
        builder.build(self.source, self.output)
        previous = self.contents(self.output)
        (self.source / 'assets/info.txt').write_bytes(b'Later source revision.\n')
        with mock.patch.object(builder, 'LIMIT_BYTES', 64):
            with self.assertRaisesRegex(ValueError, 'maximum is 64'):
                builder.build(self.source, self.output, report_path=self.report)
        self.assertEqual(self.contents(self.output), previous)
        self.assertFalse(self.report.exists())
        self.assertFalse(any(self.base.glob('.publication.build-*')))

    def test_rebuild_is_deterministic_and_foreign_targets_are_preserved(self):
        first = builder.build(self.source, self.output)
        before = self.contents(self.output)
        second = builder.build(self.source, self.output)
        self.assertEqual(self.contents(self.output), before)
        self.assertEqual(first['transport_manifest_sha256'], second['transport_manifest_sha256'])
        self.assertFalse(any(self.base.glob('.publication.previous-*')))
        foreign = self.base / 'unrelated'
        foreign.mkdir()
        sentinel = foreign / 'personal.txt'
        sentinel.write_text('Must remain intact.', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Refusing to replace a nonempty output'):
            builder.build(self.source, foreign)
        self.assertEqual(sentinel.read_text(), 'Must remain intact.')
        with self.assertRaisesRegex(ValueError, 'separate, non-nested'):
            builder.build(self.source, self.source / 'publication')
        with self.assertRaisesRegex(ValueError, 'outside both source and publication'):
            builder.build(self.source, self.output, report_path=self.output / 'report.json')

    def test_large_runtime_json_is_exact_and_source_downloads_stay_ordinary_files(self):
        raw = ('{\n"number": 1.2300e+04, "description": "' + 'Данные ' * 12000 + '"\n}\n').encode()
        for relative in ['data/projects/example/analytics.json', 'data/projections/cohort/77.json',
                         'downloads/projects/example/analytics.json']:
            target = self.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        small = self.source / 'data/authors.json'
        small.write_bytes(b'{"authors":[]}\n')
        report = builder.build(self.source, self.output)
        records = {r['path']: r for r in json.loads((self.output / builder.MANIFEST_PATH).read_text())['files']}
        self.assertEqual(report['series_count'], 1)
        self.assertEqual(report['runtime_json_count'], 2)
        self.assertEqual(report['transport_count'], 3)
        for relative in ['data/projects/example/analytics.json', 'data/projections/cohort/77.json']:
            self.assertEqual(gzip.decompress((self.output / records[relative]['compressed_path']).read_bytes()), raw)
            self.assertEqual((self.source / relative).read_bytes(), raw)
        self.assertEqual((self.output / 'downloads/projects/example/analytics.json').read_bytes(), raw)
        self.assertEqual((self.output / 'data/authors.json').read_bytes(), small.read_bytes())

    def test_static_articles_resolve_transport_and_module_under_nested_project_prefix(self):
        article = self.source / 'research/projects/example/map.html'
        article.parent.mkdir(parents=True)
        article.write_bytes(b'<html><head><title>Map</title></head><body>Source links</body></html>')
        entry = self.source / builder.STATIC_ENTRY
        entry.parent.mkdir(parents=True)
        entry.write_text('/* standalone adapter */')
        original = article.read_bytes()
        report = builder.build(self.source, self.output)
        rendered = (self.output / article.relative_to(self.source)).read_text()
        self.assertIn('content="../../../data/series-transport.json"', rendered)
        self.assertIn('src="../../../src/core/data-transport-entry.js"', rendered)
        self.assertEqual(report['html_adapters_injected'], 2)
        self.assertEqual(article.read_bytes(), original)

    def test_runtime_compression_collision_and_missing_static_adapter_fail_before_publish(self):
        runtime = self.source / 'data/research.json'
        runtime.write_text(' ' * (builder.RUNTIME_MIN_BYTES + 1))
        (self.source / 'data/research.json.gz').write_bytes(b'existing user file')
        with self.assertRaisesRegex(ValueError, 'collide'):
            builder.build(self.source, self.output)
        (self.source / 'data/research.json.gz').unlink()
        article = self.source / 'research/index.html'
        article.parent.mkdir()
        article.write_text('<html><head></head><body>Research</body></html>')
        with self.assertRaisesRegex(ValueError, 'download adapter'):
            builder.build(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_static_json_links_are_real_gzip_even_without_javascript(self):
        original = b'''<a href="../../../data/projects/example/series/62900.json?revision=2&amp;kind=full#source">JSON</a>
<a href="../../../downloads/original.json">Original</a>
<a href="https://external.test/data/projects/example/series/62900.json">External</a>
<a href="#section">Section</a>'''
        output, count = builder.rewrite_runtime_links(original, 'research/projects/example/map.html', {self.relative})
        self.assertEqual(count, 1)
        self.assertIn(b'62900.json.gz?revision=2&amp;kind=full#source', output)
        self.assertIn(b'href="../../../downloads/original.json"', output)
        self.assertIn(b'href="https://external.test/data/projects/example/series/62900.json"', output)
        self.assertIn(b'href="#section"', output)


if __name__ == '__main__':
    unittest.main()
