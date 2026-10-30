"""Portable cumulative archives restore exact publication bytes without data loss."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from restore_package_copies import restore, checked_path, pending_path, SCHEMA
from package_platform import published_source


class PackageCopiesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def entry(self, content=b'complete source bytes\n', target='docs/data/example.json', source='public/data/example.json'):
        path=self.root/source
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(content)
        return {'path':target,'source':source,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}

    def manifest(self, *entries):
        (self.root/'PACKAGE_COPIES.json').write_text(json.dumps({'schema':SCHEMA,'copies':entries}))

    def kill_fallback_copy(self, mode):
        """Kill a separate process after it flushes partial or complete bytes."""
        entry=self.entry(bytes(range(256))*16, target='docs/interrupted.bin', source='public/interrupted.bin')
        self.manifest(entry)
        ready=self.root/'copy-ready.txt'
        script=r'''
import os
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
import restore_package_copies as module
def no_hard_links(*args, **kwargs):
    raise OSError('Test filesystem without hard links')
module.os.link=no_hard_links
copy=module.shutil.copyfileobj
calls=0
def pause_destination_copy(source, destination, *args, **kwargs):
    global calls
    calls+=1
    if calls!=2:
        return copy(source,destination,*args,**kwargs)
    if sys.argv[4]=='partial':
        destination.write(source.read(127))
    else:
        copy(source,destination,*args,**kwargs)
    destination.flush()
    os.fsync(destination.fileno())
    Path(sys.argv[3]).write_text('ready',encoding='utf-8')
    # The parent kills this process, so neither Python exceptions nor finally
    # blocks can clean up the incomplete file or its recovery marker.
    sys.stdin.buffer.read(1)
module.shutil.copyfileobj=pause_destination_copy
module.restore(sys.argv[2])
'''
        process=subprocess.Popen([sys.executable,'-c',script,str(ROOT/'scripts'),str(self.root),str(ready),mode],
                                 stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+10
            while not ready.exists() and process.poll() is None and time.monotonic()<deadline:
                time.sleep(.02)
            if not ready.exists():
                if process.poll() is None:process.kill()
                stdout,stderr=process.communicate(timeout=10)
                self.fail('Subprocess did not reach the fallback copy: '+stderr.decode('utf-8',errors='replace'))
            process.kill()
            process.communicate(timeout=10)
            self.assertNotEqual(process.returncode,0)
        finally:
            if process.poll() is None:process.kill()
            process.communicate(timeout=10)
        return entry

    def test_plain_checkout_has_no_restoration_side_effect(self):
        self.assertEqual(restore(self.root)['restored'],0)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_exact_binary_and_unicode_nested_paths_restore_idempotently(self):
        content=b'\x00\xff\x80'+bytes(range(256))
        entry=self.entry(content,'docs/downloads/данные/таблица.bin','public/downloads/данные/таблица.bin')
        self.manifest(entry)
        self.assertEqual(restore(self.root)['restored'],1)
        self.assertEqual((self.root/entry['path']).read_bytes(),content)
        self.assertEqual(restore(self.root,verify_existing=True)['present'],1)

    def test_zero_byte_copy_is_retained(self):
        entry=self.entry(b'','docs/empty.txt','public/empty.txt');self.manifest(entry)
        self.assertEqual(restore(self.root)['restored'],1)
        self.assertEqual((self.root/entry['path']).read_bytes(),b'')

    def test_user_edited_destination_never_overwritten(self):
        entry=self.entry();self.manifest(entry)
        target=self.root/entry['path'];target.parent.mkdir(parents=True);target.write_bytes(b'user edit')
        self.assertEqual(restore(self.root)['present'],1)
        self.assertEqual(target.read_bytes(),b'user edit')
        with self.assertRaisesRegex(ValueError,'left unchanged'):restore(self.root,verify_existing=True)
        self.assertEqual(target.read_bytes(),b'user edit')

    def test_corrupt_source_prevents_all_writes(self):
        good=self.entry(source='public/a',target='docs/a')
        bad=self.entry(source='public/b',target='docs/b');self.manifest(good,bad)
        (self.root/'public/b').write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'has changed'):restore(self.root)
        self.assertFalse((self.root/'docs/a').exists())
        self.assertFalse((self.root/'docs/b').exists())

    def test_missing_source_is_explicit(self):
        entry=self.entry();self.manifest(entry);(self.root/entry['source']).unlink()
        with self.assertRaises(FileNotFoundError):restore(self.root)

    def test_unsafe_paths_and_recursive_aliases_rejected(self):
        for value,target in [('../escape',True),('/tmp/escape',True),('docs/../../escape',True),
                             ('docs\\escape',True),('C:/escape',True),('public/not-docs',True),('docs/copy',False)]:
            with self.subTest(value=value),self.assertRaises(ValueError):checked_path(self.root,value,target=target)

    def test_external_symlink_parent_is_rejected(self):
        outside=Path(self.temp.name).parent
        (self.root/'docs').mkdir()
        try:(self.root/'docs/link').symlink_to(outside,target_is_directory=True)
        except OSError:self.skipTest('Symlinks are unavailable.')
        with self.assertRaises(ValueError):checked_path(self.root,'docs/link/outside',target=True)

    def test_duplicate_manifest_target_is_rejected_before_writes(self):
        entry=self.entry();self.manifest(entry,entry)
        with self.assertRaisesRegex(ValueError,'Duplicate target'):restore(self.root)
        self.assertFalse((self.root/entry['path']).exists())

    def test_dry_run_checks_sources_but_writes_no_copies(self):
        entry=self.entry();self.manifest(entry)
        self.assertEqual(restore(self.root,dry_run=True)['planned'],1)
        self.assertFalse((self.root/entry['path']).exists())

    def test_fat_style_filesystem_without_hard_links(self):
        entry=self.entry();self.manifest(entry)
        with patch('restore_package_copies.os.link',side_effect=OSError('No hard links')):
            self.assertEqual(restore(self.root)['restored'],1)
        self.assertEqual((self.root/entry['path']).read_bytes(),(self.root/entry['source']).read_bytes())
        self.assertFalse(pending_path(self.root/entry['path']).exists())

    def test_killed_partial_fallback_is_detected_on_restart_without_overwrite(self):
        entry=self.kill_fallback_copy('partial')
        target=self.root/entry['path'];marker=pending_path(target)
        partial=target.read_bytes();self.assertEqual(len(partial),127)
        self.assertTrue(marker.is_file())
        with self.assertRaisesRegex(ValueError,'Incomplete published copy.*left unchanged'):
            restore(self.root)
        self.assertEqual(target.read_bytes(),partial)
        self.assertTrue(marker.is_file())
        self.assertEqual((self.root/entry['source']).stat().st_size,entry['bytes'])
        # Matching the byte count alone must not clear a pending recovery.
        wrong_bytes=b'!'*entry['bytes']
        target.write_bytes(wrong_bytes)
        with self.assertRaisesRegex(ValueError,'Incomplete published copy.*left unchanged'):
            restore(self.root)
        self.assertEqual(target.read_bytes(),wrong_bytes)
        self.assertTrue(marker.is_file())

    def test_killed_complete_fallback_is_verified_and_marker_cleared_on_restart(self):
        entry=self.kill_fallback_copy('complete')
        target=self.root/entry['path'];marker=pending_path(target)
        self.assertTrue(marker.is_file())
        complete=target.read_bytes()
        self.assertEqual(hashlib.sha256(complete).hexdigest(),entry['sha256'])
        self.assertEqual(restore(self.root,dry_run=True)['present'],1)
        self.assertTrue(marker.is_file(),'A dry run must not clear recovery metadata.')
        report=restore(self.root)
        self.assertEqual((report['restored'],report['present']),(0,1))
        self.assertFalse(marker.exists())
        self.assertEqual(target.read_bytes(),complete)
        # Once recovery is complete this is an ordinary editable publication.
        target.write_bytes(b'intentional user edit')
        self.assertEqual(restore(self.root)['present'],1)
        self.assertEqual(target.read_bytes(),b'intentional user edit')

    def test_copy_destinations_map_to_complete_retained_sources(self):
        self.assertEqual(published_source('docs/src/app.js'),'src/app.js')
        self.assertEqual(published_source('docs/index.html'),'index.html')
        self.assertEqual(published_source('docs/data/example.json'),'public/data/example.json')
        self.assertIsNone(published_source('inputs/original.zip'))


if __name__=='__main__':unittest.main()
