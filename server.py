"""Local helper for yt-downloader.html (wraps yt-dlp).

Setup:   pip install -U yt-dlp      (and install ffmpeg: https://ffmpeg.org)
Run:     python server.py
Then open yt-downloader.html in your browser and keep this window open.
"""
import json, os, shutil, tempfile, uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote

import yt_dlp

PORT = int(os.environ.get("PORT", 8765))
OUT = tempfile.mkdtemp(prefix="ytdl_")
FILES = {}


def info(url):
    with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True, "no_color": True}) as y:
        d = y.extract_info(url, download=False)
    heights = sorted(
        {f["height"] for f in d["formats"] if f.get("height") and f.get("vcodec") != "none"},
        reverse=True,
    )
    return {
        "title": d.get("title"),
        "channel": d.get("uploader"),
        "thumbnail": d.get("thumbnail"),
        "duration": d.get("duration"),
        "heights": heights,
    }


def prepare(url, height):
    if height != "audio" and not height.isdigit():
        raise ValueError("Invalid quality")
    fid = uuid.uuid4().hex
    opts = {
        "quiet": True,
        "noplaylist": True,
        "no_color": True,
        "outtmpl": os.path.join(OUT, fid + "_%(title).100s.%(ext)s"),
    }
    if height == "audio":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ]
    else:
        opts["format"] = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        opts["merge_output_format"] = "mp4"
    with yt_dlp.YoutubeDL(opts) as y:
        y.extract_info(url, download=True)
    path = next(os.path.join(OUT, n) for n in os.listdir(OUT) if n.startswith(fid))
    FILES[fid] = path
    return {"id": fid, "name": os.path.basename(path)[33:]}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, fid):
        path = FILES[fid]
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(os.path.getsize(path)))
        self.send_header(
            "Content-Disposition",
            "attachment; filename*=UTF-8''" + quote(os.path.basename(path)[33:]),
        )
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with open(path, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/info":
                return self.send_json(200, info(q["url"]))
            if u.path == "/prepare":
                return self.send_json(200, prepare(q["url"], q.get("height", "audio")))
            if u.path == "/file":
                return self.send_file(q["id"])
            self.send_json(404, {"error": "Not found"})
        except Exception as e:
            self.send_json(500, {"error": str(e)[:300]})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"Helper running on port {PORT}...")
    try:
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    finally:
        shutil.rmtree(OUT, ignore_errors=True)