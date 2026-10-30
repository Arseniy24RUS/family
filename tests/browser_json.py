"""Read original JSON through either the full site or compact Pages transport.

Playwright's APIRequestContext does not run the page's fetch adapter. Keep its
independent data assertions against the same verified source bytes instead of
mistaking a publication forwarding envelope for the dataset.
"""
import gzip
import hashlib
import json
from urllib.parse import urljoin, urlsplit


REDIRECT_SCHEMA = 'national-projects.series-redirect/1'


async def fulfill_json(route, packet):
    """Serve a fault-injection fixture in the requested publication encoding."""
    payload = json.dumps(packet, ensure_ascii=False).encode('utf-8')
    compressed = urlsplit(route.request.url).path.endswith('.gz')
    await route.fulfill(status=200,
                        content_type='application/gzip' if compressed else 'application/json',
                        body=gzip.compress(payload, mtime=0) if compressed else payload)


def decode_transport(envelope, compressed):
    """Validate both transport bytes and the original dataset before decoding."""
    if (len(compressed) != envelope.get('compressed_bytes') or
            hashlib.sha256(compressed).hexdigest() != envelope.get('compressed_sha256')):
        raise AssertionError('Published JSON compressed checksum or size mismatch')
    original = gzip.decompress(compressed)
    if (len(original) != envelope.get('bytes') or
            hashlib.sha256(original).hexdigest() != envelope.get('sha256')):
        raise AssertionError('Published JSON source checksum or size mismatch')
    return json.loads(original)


async def get_json(context, base, path):
    base = base.rstrip('/') + '/'
    url = urljoin(base, path)
    response = await context.request.get(url)
    assert response.ok, (path, response.status)
    packet = await response.json()
    if not isinstance(packet, dict) or packet.get('schema') != REDIRECT_SCHEMA:
        return packet
    relative = packet.get('path')
    compressed_path = packet.get('compressed_path')
    expected = urlsplit(urljoin(base, relative)) if isinstance(relative, str) else None
    requested = urlsplit(url)
    if (expected is None or
            (expected.scheme, expected.netloc, expected.path) !=
            (requested.scheme, requested.netloc, requested.path) or
            compressed_path != relative + '.gz'):
        raise AssertionError('Published JSON forwarding path does not match the request')
    compressed_url = urlsplit(urljoin(base, compressed_path))
    root = urlsplit(base)
    if ((compressed_url.scheme, compressed_url.netloc) != (root.scheme, root.netloc) or
            not compressed_url.path.startswith(root.path)):
        raise AssertionError('Published JSON transport leaves the site root')
    compressed = await context.request.get(compressed_url.geturl())
    assert compressed.ok, (compressed_path, compressed.status)
    return decode_transport(packet, await compressed.body())
