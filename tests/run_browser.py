"""Run real HTTP browser QA, including GitHub Pages' project subpath.

python tests/run_browser.py --output <directory outside the checkout>
python tests/run_browser.py --directory .pages --output <directory outside the checkout>
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
SUITES = ['browser_check', 'browser_upgrade', 'browser_redesign', 'browser_live',
          'browser_youth', 'browser_personnel', 'browser_longlife', 'browser_healthtech', 'browser_infrastructure', 'browser_environment', 'browser_competitive', 'browser_dataeconomy', 'browser_tourism', 'browser_transport', 'browser_export', 'browser_platform_system']


class PagesHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if path.startswith('/family/'):
            path = path[len('/family'):]
        return super().translate_path(path)

    def log_message(self, *args):
        pass


class PagesServer(http.server.ThreadingHTTPServer):
    # Several module/data requests arrive together when each fresh browser starts.
    request_queue_size = 64


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base')
    parser.add_argument('--directory', type=Path, default=ROOT/'docs',
                        help='Local site directory, relative to the project root unless absolute. Default: docs. Ignored with --base.')
    parser.add_argument('--browser', help='Optional Chromium executable path')
    parser.add_argument('--suite', action='append', choices=SUITES,
                        help='Run only this suite; repeat for several. Default: all suites.')
    parser.add_argument('--output', type=Path, default=Path(tempfile.gettempdir())/'semya-browser-qa')
    args = parser.parse_args()
    server = None
    if not args.base:
        directory = (ROOT/args.directory).resolve()
        if directory == (ROOT/'docs').resolve():
            subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/'scripts/restore_package_copies.py')],
                           cwd=ROOT, check=True)
        if not directory.is_dir():
            parser.error('Local site directory does not exist: ' + str(directory))
        server = PagesServer(
            ('127.0.0.1', 0), functools.partial(PagesHandler, directory=str(directory)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        args.base = f'http://127.0.0.1:{server.server_port}/family/'
    try:
        for name in args.suite or SUITES:
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
