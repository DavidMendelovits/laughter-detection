"""Lightweight HTTP video player that overlays detected laughter on a timeline."""

from __future__ import annotations

import http.server
import json
import mimetypes
import os
import socket
import socketserver
import threading
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional


HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Laughter Player</title>
<style>
  :root {
    color-scheme: dark;
    --bg: #0e0f12;
    --panel: #16181d;
    --panel-2: #1d2027;
    --fg: #e8eaef;
    --muted: #8a8f99;
    --accent: #ffb300;
    --accent-soft: rgba(255, 179, 0, 0.35);
    --track: #2a2e36;
    --progress: #4a90e2;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    padding: 0;
    background: var(--bg);
    color: var(--fg);
    font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }
  .wrap {
    max-width: 1100px;
    margin: 24px auto;
    padding: 0 16px;
  }
  h1 {
    font-size: 18px;
    font-weight: 600;
    margin: 0 0 4px;
  }
  .sub {
    color: var(--muted);
    font-size: 12px;
    margin-bottom: 16px;
    word-break: break-all;
  }
  video {
    width: 100%;
    background: #000;
    border-radius: 8px;
    display: block;
  }
  .timeline {
    position: relative;
    height: 36px;
    margin-top: 12px;
    background: var(--panel);
    border-radius: 6px;
    cursor: pointer;
    user-select: none;
    overflow: hidden;
  }
  .timeline .track {
    position: absolute;
    inset: 16px 0 16px 0;
    background: var(--track);
    border-radius: 2px;
  }
  .timeline .progress {
    position: absolute;
    top: 16px;
    bottom: 16px;
    left: 0;
    width: 0%;
    background: var(--progress);
    border-radius: 2px;
    pointer-events: none;
  }
  .timeline .playhead {
    position: absolute;
    top: 4px;
    bottom: 4px;
    width: 2px;
    background: #fff;
    transform: translateX(-1px);
    pointer-events: none;
  }
  .marker {
    position: absolute;
    top: 4px;
    bottom: 4px;
    background: var(--accent);
    opacity: 0.85;
    border-radius: 2px;
    min-width: 2px;
    box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.4);
  }
  .marker:hover {
    opacity: 1;
    z-index: 2;
  }
  .controls {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-top: 12px;
    flex-wrap: wrap;
  }
  button {
    background: var(--panel-2);
    color: var(--fg);
    border: 1px solid #2c313a;
    border-radius: 6px;
    padding: 6px 12px;
    font: inherit;
    cursor: pointer;
  }
  button:hover { background: #242832; }
  button:disabled { opacity: 0.4; cursor: not-allowed; }
  .stat {
    color: var(--muted);
    font-size: 12px;
    margin-left: auto;
  }
  .list {
    margin-top: 16px;
    background: var(--panel);
    border-radius: 8px;
    overflow: hidden;
  }
  .list-header {
    padding: 10px 14px;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    border-bottom: 1px solid #20242c;
  }
  .row {
    display: grid;
    grid-template-columns: 32px 1fr 90px 90px 80px;
    gap: 12px;
    padding: 8px 14px;
    align-items: center;
    cursor: pointer;
    border-bottom: 1px solid #1a1d23;
  }
  .row:last-child { border-bottom: none; }
  .row:hover { background: var(--panel-2); }
  .row.active { background: rgba(74, 144, 226, 0.15); }
  .row .idx { color: var(--muted); font-variant-numeric: tabular-nums; }
  .row .bar {
    height: 6px;
    background: var(--track);
    border-radius: 3px;
    position: relative;
    overflow: hidden;
  }
  .row .bar > span {
    position: absolute;
    inset: 0 auto 0 0;
    background: var(--accent);
    border-radius: 3px;
  }
  .row .num { text-align: right; font-variant-numeric: tabular-nums; }
  .empty {
    padding: 24px 14px;
    color: var(--muted);
    text-align: center;
  }
  kbd {
    background: #2a2e36;
    border-radius: 3px;
    padding: 1px 5px;
    font-size: 11px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }
</style>
</head>
<body>
<div class="wrap">
  <h1>Laughter Player</h1>
  <div class="sub" id="source">Loading…</div>

  <video id="video" controls preload="metadata" src="/video"></video>

  <div class="timeline" id="timeline" title="Click to seek">
    <div class="track"></div>
    <div class="progress" id="progress"></div>
    <div class="playhead" id="playhead"></div>
  </div>

  <div class="controls">
    <button id="prev">◀ Prev laugh</button>
    <button id="next">Next laugh ▶</button>
    <span class="stat" id="stat">—</span>
  </div>

  <div class="list" id="list">
    <div class="list-header">Detected segments</div>
    <div class="empty">Loading…</div>
  </div>
</div>

<script>
(function () {
  const video = document.getElementById('video');
  const timeline = document.getElementById('timeline');
  const progress = document.getElementById('progress');
  const playhead = document.getElementById('playhead');
  const list = document.getElementById('list');
  const stat = document.getElementById('stat');
  const sourceEl = document.getElementById('source');
  const prevBtn = document.getElementById('prev');
  const nextBtn = document.getElementById('next');

  let segments = [];
  let markerEls = [];
  let rowEls = [];

  function fmt(t) {
    if (!isFinite(t)) return '0:00';
    const m = Math.floor(t / 60);
    const s = Math.floor(t % 60);
    return m + ':' + (s < 10 ? '0' : '') + s;
  }

  function renderMarkers() {
    markerEls.forEach(el => el.remove());
    markerEls = [];
    const dur = video.duration;
    if (!isFinite(dur) || dur <= 0) return;
    for (const seg of segments) {
      const el = document.createElement('div');
      el.className = 'marker';
      const left = (seg.start_time / dur) * 100;
      const width = Math.max(((seg.end_time - seg.start_time) / dur) * 100, 0.3);
      el.style.left = left + '%';
      el.style.width = width + '%';
      el.title = `${fmt(seg.start_time)}–${fmt(seg.end_time)} · score ${seg.score.toFixed(3)}`;
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        video.currentTime = seg.start_time;
        video.play();
      });
      timeline.appendChild(el);
      markerEls.push(el);
    }
  }

  function renderList() {
    list.innerHTML = '<div class="list-header">Detected segments (' + segments.length + ')</div>';
    rowEls = [];
    if (segments.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = 'No laughter segments detected.';
      list.appendChild(empty);
      return;
    }
    const maxScore = Math.max(...segments.map(s => s.score), 0.01);
    segments.forEach((seg, i) => {
      const row = document.createElement('div');
      row.className = 'row';
      row.innerHTML = `
        <span class="idx">${i + 1}</span>
        <span class="bar"><span style="width:${(seg.score / maxScore) * 100}%"></span></span>
        <span class="num">${fmt(seg.start_time)}</span>
        <span class="num">${seg.duration.toFixed(2)}s</span>
        <span class="num">${seg.score.toFixed(3)}</span>
      `;
      row.addEventListener('click', () => {
        video.currentTime = seg.start_time;
        video.play();
      });
      list.appendChild(row);
      rowEls.push(row);
    });
  }

  function updatePlayhead() {
    const dur = video.duration;
    if (!isFinite(dur) || dur <= 0) return;
    const pct = (video.currentTime / dur) * 100;
    progress.style.width = pct + '%';
    playhead.style.left = pct + '%';
    const t = video.currentTime;
    let activeIdx = -1;
    for (let i = 0; i < segments.length; i++) {
      if (t >= segments[i].start_time && t <= segments[i].end_time) {
        activeIdx = i;
        break;
      }
    }
    rowEls.forEach((r, i) => r.classList.toggle('active', i === activeIdx));
    stat.textContent = `${fmt(t)} / ${fmt(dur)}`;
  }

  timeline.addEventListener('click', (e) => {
    const rect = timeline.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    const dur = video.duration;
    if (isFinite(dur) && dur > 0) video.currentTime = ratio * dur;
  });

  function jump(direction) {
    if (segments.length === 0) return;
    const t = video.currentTime;
    let target;
    if (direction > 0) {
      target = segments.find(s => s.start_time > t + 0.05);
      if (!target) target = segments[segments.length - 1];
    } else {
      const earlier = segments.filter(s => s.start_time < t - 0.5);
      target = earlier.length ? earlier[earlier.length - 1] : segments[0];
    }
    video.currentTime = target.start_time;
    video.play();
  }
  nextBtn.addEventListener('click', () => jump(1));
  prevBtn.addEventListener('click', () => jump(-1));

  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'n' || e.key === 'N') jump(1);
    else if (e.key === 'p' || e.key === 'P') jump(-1);
    else if (e.key === ' ') {
      e.preventDefault();
      video.paused ? video.play() : video.pause();
    }
  });

  video.addEventListener('loadedmetadata', renderMarkers);
  video.addEventListener('timeupdate', updatePlayhead);
  video.addEventListener('seeked', updatePlayhead);
  window.addEventListener('resize', renderMarkers);

  fetch('/results.json').then(r => r.json()).then(data => {
    segments = (data.segments || []).slice().sort((a, b) => a.start_time - b.start_time);
    sourceEl.textContent = data.source_file || '';
    renderList();
    if (isFinite(video.duration) && video.duration > 0) renderMarkers();
  }).catch(err => {
    sourceEl.textContent = 'Failed to load results: ' + err;
  });
})();
</script>
</body>
</html>
"""


def _parse_range(header: str, file_size: int) -> Optional[tuple[int, int]]:
    """Parse a single-range HTTP Range header. Returns (start, end) inclusive or None."""
    if not header or not header.startswith("bytes="):
        return None
    spec = header[6:].split(",", 1)[0].strip()
    if "-" not in spec:
        return None
    start_s, end_s = spec.split("-", 1)
    try:
        if start_s == "":
            length = int(end_s)
            if length <= 0:
                return None
            start = max(0, file_size - length)
            end = file_size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else file_size - 1
    except ValueError:
        return None
    if start > end or start >= file_size or start < 0:
        return None
    end = min(end, file_size - 1)
    return start, end


def _build_handler(video_path: Path, results: dict):
    """Build a request handler bound to a specific video and results payload."""
    results_bytes = json.dumps(results, indent=2).encode("utf-8")
    html_bytes = HTML_PAGE.encode("utf-8")
    video_size = video_path.stat().st_size
    video_mime = mimetypes.guess_type(str(video_path))[0] or "application/octet-stream"

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A002
            # Quieter than the default stderr spam.
            return

        def do_GET(self):  # noqa: N802
            path = urllib.parse.urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send_bytes(html_bytes, "text/html; charset=utf-8")
            elif path == "/results.json":
                self._send_bytes(results_bytes, "application/json; charset=utf-8")
            elif path == "/video":
                self._send_video()
            else:
                self.send_error(404)

        def do_HEAD(self):  # noqa: N802
            path = urllib.parse.urlparse(self.path).path
            if path == "/video":
                self.send_response(200)
                self.send_header("Content-Type", video_mime)
                self.send_header("Content-Length", str(video_size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
            else:
                self.send_error(404)

        def _send_bytes(self, body: bytes, content_type: str):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_video(self):
            range_header = self.headers.get("Range")
            rng = _parse_range(range_header, video_size) if range_header else None

            if rng is None:
                self.send_response(200)
                self.send_header("Content-Type", video_mime)
                self.send_header("Content-Length", str(video_size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                start, length = 0, video_size
            else:
                start, end = rng
                length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Type", video_mime)
                self.send_header("Content-Length", str(length))
                self.send_header("Content-Range", f"bytes {start}-{end}/{video_size}")
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

            chunk_size = 1024 * 1024
            try:
                with open(video_path, "rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(chunk_size, remaining))
                        if not chunk:
                            break
                        try:
                            self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        remaining -= len(chunk)
            except FileNotFoundError:
                # Already sent headers, nothing more to do.
                return

    return Handler


class _ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _find_open_port(preferred: int) -> int:
    """Return the preferred port if free, otherwise an OS-assigned one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve_player(
    video_path: str,
    results: dict,
    port: int = 8000,
    host: str = "127.0.0.1",
    open_browser: bool = True,
) -> None:
    """Start a blocking HTTP server that hosts the video + laughter markers UI.

    Args:
        video_path: Path to the source video file.
        results: Detection results dict (matches process_video output).
        port: Preferred port; falls back to a random free port if taken.
        host: Bind address (default localhost).
        open_browser: If True, open the system browser to the page on start.
    """
    path = Path(video_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Video file not found: {path}")

    handler = _build_handler(path, results)
    actual_port = _find_open_port(port)
    server = _ThreadingServer((host, actual_port), handler)
    url = f"http://{host}:{actual_port}/"

    print(f"Serving laughter player at {url}")
    print("Press Ctrl+C to stop.")

    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down player.")
    finally:
        server.shutdown()
        server.server_close()
