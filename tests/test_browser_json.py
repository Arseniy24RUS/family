import gzip
import hashlib
import json
import unittest
from types import SimpleNamespace

from browser_json import REDIRECT_SCHEMA, get_json


class Response:
    ok = True
    status = 200

    def __init__(self, data):
        self.data = data

    async def json(self):
        return json.loads(self.data)

    async def body(self):
        return self.data


class BrowserJSONTests(unittest.IsolatedAsyncioTestCase):
    async def read(self, compressed_site=False, corrupt=None):
        original = json.dumps({'rows': [{'territory': 'Москва', 'value': 0}]}).encode()
        compressed = gzip.compress(original, mtime=0)
        path = 'data/projects/test/statistics.json'
        envelope = {
            'schema': REDIRECT_SCHEMA, 'path': path, 'compressed_path': path + '.gz',
            'bytes': len(original), 'sha256': hashlib.sha256(original).hexdigest(),
            'compressed_bytes': len(compressed),
            'compressed_sha256': hashlib.sha256(compressed).hexdigest(),
        }
        if corrupt == 'compressed':
            compressed = compressed[:-1] + bytes([compressed[-1] ^ 1])
        elif corrupt == 'source':
            envelope['sha256'] = '0' * 64
        elif corrupt == 'path':
            envelope['compressed_path'] = 'https://external.test/packet.gz'
        requests = []

        async def fetch(url):
            requests.append(url)
            if url.endswith('.gz'):
                return Response(compressed)
            return Response(json.dumps(envelope).encode() if compressed_site else original)

        result = await get_json(SimpleNamespace(request=SimpleNamespace(get=fetch)),
                                'https://example.test/family/', path)
        self.assertEqual(result, json.loads(original))
        self.assertEqual(len(requests), 2 if compressed_site else 1)
        if compressed_site:
            self.assertEqual(requests[-1], 'https://example.test/family/' + path + '.gz')

    async def test_full_site_json(self):
        await self.read()

    async def test_compact_json_under_project_subpath(self):
        await self.read(compressed_site=True)

    async def test_corrupt_compressed_bytes_are_rejected(self):
        with self.assertRaisesRegex(AssertionError, 'compressed checksum'):
            await self.read(compressed_site=True, corrupt='compressed')

    async def test_wrong_original_hash_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, 'source checksum'):
            await self.read(compressed_site=True, corrupt='source')

    async def test_external_transport_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, 'forwarding path'):
            await self.read(compressed_site=True, corrupt='path')


if __name__ == '__main__':
    unittest.main()
