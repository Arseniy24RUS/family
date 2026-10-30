#!/usr/bin/env python3
"""Preview the prebuilt platform locally using Python's standard library."""
import argparse
import functools
import http.server
from pathlib import Path
import threading
import webbrowser
from restore_package_copies import restore

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8080)
    parser.add_argument('--no-open',action='store_true')
    args=parser.parse_args()
    restored=restore()
    if restored['restored']:
        print('Prepared published files:',restored['restored'],flush=True)
    directory=Path(__file__).resolve().parents[1]/'docs'
    if not (directory/'index.html').is_file():
        parser.error('Missing docs/index.html. Run npm run build first.')
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(directory))
    try:
        server=http.server.ThreadingHTTPServer(('127.0.0.1',args.port),handler)
    except OSError as error:
        parser.error(f'Cannot open port {args.port}: {error}. Try --port 8081.')
    url=f'http://127.0.0.1:{server.server_port}/'
    print('National Projects platform:',url,'\nPress Ctrl+C to stop.',flush=True)
    if not args.no_open:
        threading.Timer(.4,lambda:webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__=='__main__': main()
