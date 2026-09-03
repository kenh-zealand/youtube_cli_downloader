#!/usr/bin/env python3
"""
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

Requires yt-dlp and ffmpeg on PATH (both are already installed on this machine).
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_OUTPUT_DIR = Path.home() / "Downloads" / "YouTube"

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

    cmd = [ytdlp, url, "-o", out_template, "--windows-filenames", "--no-part"]
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

    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        sys.exit(f"\nDownload failed (yt-dlp exit code {proc.returncode}).")

    print(f"\nDone. Saved under: {out_dir}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nCancelled.")
