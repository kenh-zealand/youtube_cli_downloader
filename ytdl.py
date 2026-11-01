#!/usr/bin/env python3
r"""
YouTube Downloader - a friendly CLI wrapper around yt-dlp.

Download a YouTube video as MP4 (pick a resolution) or grab just the audio
as MP3 (pick a bitrate). Only the qualities that actually exist for the
given video are ever offered.

Usage:
    python ytdl.py                                  fully interactive
    python ytdl.py <url>                             interactive format/quality picker
    python ytdl.py <url> -f mp3                       skip to mp3, still asks bitrate
    python ytdl.py <url> -f mp4 -q 720p                fully non-interactive
    python ytdl.py <url> -f mp3 -q 192 -o D:\Music     fully non-interactive, custom folder
    python ytdl.py <playlist_url> --playlist -f mp3     download a whole playlist as mp3

While a download is running, press:
    P   pause / resume
    S   stop (partial file is kept - rerun the same command to resume it)

Works on Windows and Linux (tested target: Debian). Requires yt-dlp and
ffmpeg on PATH, plus the 'psutil' package for pause/stop (see README).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

try:
    import msvcrt  # Windows
except ImportError:
    msvcrt = None

try:
    import select  # Linux / macOS
    import termios
    import tty
except ImportError:
    termios = None


def _downloads_dir() -> Path:
    """The user's Downloads folder.

    On Linux this respects XDG (e.g. 'Hentede filer' on a Danish desktop);
    everywhere else it falls back to ~/Downloads.
    """
    if sys.platform.startswith("linux") and shutil.which("xdg-user-dir"):
        try:
            out = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True).stdout.strip()
            if out and Path(out) != Path.home():
                return Path(out)
        except OSError:
            pass
    return Path.home() / "Downloads"


DEFAULT_OUTPUT_DIR = _downloads_dir() / "YouTube"

AUDIO_QUALITY_LABELS = [
    ("Best (highest available bitrate)", "0"),
    ("320 kbps", "320K"),
    ("256 kbps", "256K"),
    ("192 kbps", "192K"),
    ("128 kbps", "128K"),
]
AUDIO_QUALITY_CODES = {"best": "0", "320": "320K", "256": "256K", "192": "192K", "128": "128K"}


def find_exe(name: str) -> str:
    path = shutil.which(name)
    if not path:
        sys.exit(f"error: '{name}' not found on PATH. Install it and try again.")
    return path


def fetch_info(url: str, ytdlp: str, playlist: bool) -> dict:
    print("Fetching video info...")
    cmd = [ytdlp, "-J"]
    if not playlist:
        cmd.append("--no-playlist")
    else:
        cmd += ["--flat-playlist"]
    cmd.append(url)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"error: failed to fetch info:\n{proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.exit("error: could not parse video info returned by yt-dlp")


def available_resolutions(info: dict) -> list[int]:
    heights = set()
    for f in info.get("formats", []) or []:
        if f.get("vcodec") not in (None, "none") and f.get("height"):
            heights.add(int(f["height"]))
    return sorted(heights, reverse=True)


def prompt_choice(prompt: str, options: list[str]) -> int:
    """Print a numbered menu and return the chosen index."""
    print(f"\n{prompt}:")
    for i, opt in enumerate(options, 1):
        print(f"  {i}) {opt}")
    while True:
        raw = input(f"Choose [1-{len(options)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print("Invalid choice, try again.")


def fmt_duration(seconds) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"


def _proc_tree(pid):
    """The process plus any children (e.g. ffmpeg spawned by yt-dlp), if still alive."""
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return []
    procs = [parent]
    try:
        procs += parent.children(recursive=True)
    except psutil.Error:
        pass
    return [p for p in procs if p.is_running()]


def _suspend_tree(pid):
    for p in _proc_tree(pid):
        try:
            p.suspend()
        except psutil.Error:
            pass


def _resume_tree(pid):
    for p in _proc_tree(pid):
        try:
            p.resume()
        except psutil.Error:
            pass


def _kill_tree(pid):
    procs = _proc_tree(pid)
    for p in procs:
        try:
            p.terminate()
        except psutil.Error:
            pass
    if procs:
        _, alive = psutil.wait_procs(procs, timeout=3)
        for p in alive:
            try:
                p.kill()
            except psutil.Error:
                pass


class KeyReader:
    """Non-blocking single-key reads from the console, on Windows and POSIX.

    Use as a context manager: on Linux/macOS it puts the terminal in cbreak
    mode (keys arrive immediately, without Enter and without echo) and always
    restores the original settings on exit, even after Ctrl+C or a crash.
    """

    def __init__(self):
        self._fd = None
        self._old = None

    @staticmethod
    def supported() -> bool:
        return msvcrt is not None or termios is not None

    def __enter__(self):
        if msvcrt is None and termios is not None:
            self._fd = sys.stdin.fileno()
            self._old = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        return self

    def __exit__(self, *exc):
        if self._old is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)
        return False

    def read_key(self, timeout: float) -> str | None:
        """Return a lowercase key if one was pressed within `timeout`, else None."""
        if msvcrt is not None:
            if msvcrt.kbhit():
                return msvcrt.getch().decode(errors="ignore").lower()
            time.sleep(timeout)
            return None
        ready, _, _ = select.select([self._fd], [], [], timeout)
        if ready:
            return os.read(self._fd, 1).decode(errors="ignore").lower()
        return None


def run_download(cmd) -> tuple[int, bool]:
    """Run the yt-dlp command, returning (returncode, was_stopped_by_user).

    If psutil or keyboard support isn't available (or there's no real
    console attached), falls back to a plain, non-interactive run.
    """
    if psutil is None or not KeyReader.supported() or not sys.stdin.isatty():
        if psutil is None:
            print("(tip: install psutil to enable pause/stop controls - see README)")
        proc = subprocess.run(cmd)
        return proc.returncode, False

    print("\nControls:  [P] pause/resume    [S] stop\n")
    state = {"paused": False, "stopped": False}
    stop_polling = threading.Event()

    with KeyReader() as keys:
        # stdin=DEVNULL so yt-dlp/ffmpeg can't swallow our P/S keypresses.
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)

        def listen():
            while not stop_polling.is_set():
                try:
                    key = keys.read_key(0.15)
                    if key == "p":
                        if state["paused"]:
                            _resume_tree(proc.pid)
                            state["paused"] = False
                            print("\n[Resumed]")
                        else:
                            _suspend_tree(proc.pid)
                            state["paused"] = True
                            print("\n[Paused] Press P to resume, S to stop.")
                    elif key in ("s", "q"):
                        state["stopped"] = True
                        print("\n[Stopping...]")
                        if state["paused"]:
                            _resume_tree(proc.pid)  # let it unwind before killing
                        _kill_tree(proc.pid)
                        return
                except (OSError, ValueError):
                    time.sleep(0.15)

        t = threading.Thread(target=listen, daemon=True)
        t.start()
        try:
            returncode = proc.wait()
        except KeyboardInterrupt:
            # Ctrl+C: make sure a paused (SIGSTOPped) yt-dlp doesn't linger.
            _resume_tree(proc.pid)
            _kill_tree(proc.pid)
            raise
        finally:
            stop_polling.set()
            t.join(timeout=1)
    return returncode, state["stopped"]


def main():
    parser = argparse.ArgumentParser(description="Download YouTube videos/audio as MP4 or MP3.")
    parser.add_argument("url", nargs="?", help="YouTube video or playlist URL")
    parser.add_argument("-f", "--format", choices=["mp3", "mp4"], help="Output format")
    parser.add_argument("-q", "--quality", help="mp4: e.g. 1080p, 720p, best  |  mp3: e.g. 320, 192, best")
    parser.add_argument("-o", "--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Where to save files")
    parser.add_argument("--playlist", action="store_true", help="Download the whole playlist instead of a single video")
    args = parser.parse_args()

    ytdlp = find_exe("yt-dlp")
    find_exe("ffmpeg")

    url = args.url or input("YouTube URL: ").strip()
    if not url:
        sys.exit("error: no URL provided")

    info = fetch_info(url, ytdlp, args.playlist)

    if args.playlist and "entries" in info:
        count = len(info["entries"])
        print(f"Playlist: {info.get('title', url)}  ({count} videos)")
        # For quality selection on a playlist, probe the first entry for real formats.
        first_url = info["entries"][0].get("url") or info["entries"][0].get("id")
        probe_info = fetch_info(first_url, ytdlp, playlist=False) if first_url else info
    else:
        title = info.get("title", "video")
        print(f"Title: {title}")
        if info.get("duration"):
            print(f"Duration: {fmt_duration(info['duration'])}")
        probe_info = info

    # ---- format ----
    if args.format:
        fmt = args.format
    else:
        idx = prompt_choice("Format", ["mp4 (video)", "mp3 (audio only)"])
        fmt = "mp4" if idx == 0 else "mp3"

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.playlist:
        out_template = str(out_dir / "%(playlist_title)s" / "%(playlist_index)02d - %(title)s.%(ext)s")
    else:
        out_template = str(out_dir / "%(title)s.%(ext)s")

    cmd = [ytdlp, url, "-o", out_template, "--windows-filenames"]
    if not args.playlist:
        cmd.append("--no-playlist")

    if fmt == "mp4":
        heights = available_resolutions(probe_info)
        if not heights:
            sys.exit("error: no downloadable video streams found for this URL")

        if args.quality:
            q = args.quality.lower().replace("p", "")
            if q == "best":
                chosen_height = heights[0]
            elif q.isdigit() and int(q) in heights:
                chosen_height = int(q)
            else:
                avail = ", ".join(f"{h}p" for h in heights)
                sys.exit(f"error: quality '{args.quality}' not available for this video. Available: {avail}")
        else:
            labels = [f"{h}p" + ("  (best available)" if h == heights[0] else "") for h in heights]
            chosen_idx = prompt_choice("Video quality", labels)
            chosen_height = heights[chosen_idx]

        print(f"\nDownloading MP4 @ {chosen_height}p ...")
        selector = f"bestvideo[height<={chosen_height}]+bestaudio/best[height<={chosen_height}]"
        cmd += ["-f", selector, "--merge-output-format", "mp4"]

    else:  # mp3
        if args.quality:
            key = args.quality.lower().replace("kbps", "").replace("k", "").strip()
            code = AUDIO_QUALITY_CODES.get(key)
            if not code:
                sys.exit(f"error: quality '{args.quality}' not recognized. Use one of: best, 320, 256, 192, 128")
        else:
            labels = [label for label, _ in AUDIO_QUALITY_LABELS]
            chosen_idx = prompt_choice("Audio quality", labels)
            code = AUDIO_QUALITY_LABELS[chosen_idx][1]

        print(f"\nDownloading MP3 (quality {code}) ...")
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", code]

    returncode, stopped = run_download(cmd)
    if stopped:
        print(f"\nStopped. Partial file kept in: {out_dir}")
        print("Run the same command again to resume where it left off.")
        sys.exit(0)
    if returncode != 0:
        sys.exit(f"\nDownload failed (yt-dlp exit code {returncode}).")

    print(f"\nDone. Saved under: {out_dir}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nCancelled.")
