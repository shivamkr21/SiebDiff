import argparse
import webbrowser

from . import __version__, server


def main():
    parser = argparse.ArgumentParser(prog="SiebDiff", description="Siebel repository diff checker")
    parser.add_argument("--port", type=int, default=0, help="port to listen on (default: any free port)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    args = parser.parse_args()

    app = server.App()
    httpd = server.create(app, args.port)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"

    print(f"SiebDiff {__version__}")
    print(f"Running at {url}")
    print("Keep this window open while you use SiebDiff. Close it, or click Quit in the page, to stop.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.db.disconnect()
        httpd.server_close()
