"""Run real HTTP browser QA, including GitHub Pages' project subpath.

python tests/run_browser.py --output <directory outside the checkout>
python tests/run_browser.py --base https://arseniy24rus.github.io/family/
"""
import argparse
import functools
import http.server
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]


class PagesHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if path.startswith('/family/'):
            path = path[len('/family'):]
        return super().translate_path(path)

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base')
    parser.add_argument('--browser', help='Optional Chromium executable path')
    parser.add_argument('--output', type=Path, default=Path(tempfile.gettempdir())/'semya-browser-qa')
    args = parser.parse_args()
    server = None
    if not args.base:
        server = http.server.ThreadingHTTPServer(
            ('127.0.0.1', 0), functools.partial(PagesHandler, directory=str(ROOT/'docs')))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        args.base = f'http://127.0.0.1:{server.server_port}/family/'
    try:
        for name in ['browser_check', 'browser_upgrade', 'browser_redesign', 'browser_live']:
            command = [sys.executable, '-X', 'utf8', str(ROOT/'tests'/f'{name}.py'),
                       '--base', args.base, '--output', str(args.output/name)]
            if args.browser:
                command += ['--browser', args.browser]
            subprocess.run(command, cwd=ROOT, check=True,
                           env={**os.environ, 'PYTHONUTF8': '1'})
    finally:
        if server:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()
