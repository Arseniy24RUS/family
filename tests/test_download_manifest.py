"""Regression: interrupted atomic CSV writes never become public downloads."""
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from download_manifest import download_records


class DownloadManifestTests(unittest.TestCase):
    def test_hidden_atomic_remnants_and_backups_are_excluded_without_losing_real_documents(self):
        with tempfile.TemporaryDirectory() as temporary:
            public = Path(temporary) / 'public'
            downloads = public / 'downloads/projects/example/statistical'
            retained = ['observations.csv', 'nested/source.zip', 'report.pdf',
                        'observations_snapshot.csv.gz', 'README.txt', 'source.json']
            excluded = ['.observations.csv.w1jxvsn9.tmp.i0E0bv',
                        'observations.csv.w1jxvsn9.tmp.i0E0bv', 'observations.csv.tmp',
                        '.stage/observations.csv', 'nested/.stage/source.zip',
                        '__pycache__/module.pyc', 'module.pyo', 'old.csv.bak',
                        'old.backup.csv', 'old.csv~', '#observations.csv#',
                        'backup/source.csv', 'backups/source.zip']
            for name in retained + excluded:
                target = downloads / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(('source:' + name).encode())
            before = {path: path.read_bytes() for path in downloads.rglob('*') if path.is_file()}
            records = download_records(downloads, public)
            expected = sorted('downloads/projects/example/statistical/' + name for name in retained)
            self.assertEqual([record['url'] for record in records], expected)
            for record in records:
                raw = (public / record['url']).read_bytes()
                self.assertEqual(record['bytes'], len(raw))
                self.assertEqual(record['sha256'], hashlib.sha256(raw).hexdigest())
            limited = download_records(downloads, public, suffixes={'.csv', '.zip'})
            self.assertEqual([record['url'] for record in limited],
                             [url for url in expected if Path(url).suffix in {'.csv', '.zip'}])
            self.assertEqual(before, {path: path.read_bytes() for path in downloads.rglob('*') if path.is_file()})


if __name__ == '__main__':
    unittest.main()
