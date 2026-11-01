# YouTube Downloader

A small CLI wrapper around [yt-dlp](https://github.com/yt-dlp/yt-dlp) for
downloading YouTube videos as **MP4** (choose a resolution) or extracting
audio as **MP3** (choose a bitrate). It only ever offers qualities that
actually exist for the video you give it.

Works on **Windows** and **Linux** (Debian). Requires `yt-dlp` and `ffmpeg`
on PATH, plus the `psutil` package for the pause/stop controls below.

## Installation

### Windows

Install `yt-dlp` and `ffmpeg` so they're on PATH, then:

```
pip install psutil
```

### Debian / Ubuntu

```bash
sudo apt install python3 python3-psutil ffmpeg pipx
pipx ensurepath          # then open a new terminal
pipx install yt-dlp
```

`yt-dlp` is installed with pipx rather than apt because YouTube changes
often and the apt version lags behind. Keep it current with
`pipx upgrade yt-dlp` — if downloads suddenly start failing, that's the
first thing to try.

Make the launcher executable and (optionally) put it on your PATH as `ytdl`:

```bash
chmod +x ytdl.sh
ln -s "$PWD/ytdl.sh" ~/.local/bin/ytdl
```

Now `ytdl` works from any folder.

## Usage

Fully interactive (prompts for URL, format, and quality):

```
python ytdl.py
```

or on Windows, double-click-friendly:

```
ytdl.bat
```

or on Linux:

```
./ytdl.sh        # or just `ytdl` if you made the symlink above
```

Pass a URL and let it prompt for the rest:

```
python ytdl.py https://www.youtube.com/watch?v=XXXXXXXXXXX
```

Fully non-interactive:

```
python ytdl.py <url> -f mp4 -q 720p
python ytdl.py <url> -f mp3 -q 192
python ytdl.py <url> -f mp3 -q best -o D:\Music
```

Download an entire playlist as MP3:

```
python ytdl.py <playlist_url> --playlist -f mp3 -q 192
```

## Options

| Flag | Meaning |
|---|---|
| `-f, --format {mp3,mp4}` | Output format |
| `-q, --quality` | mp4: `1080p`, `720p`, `480p`, `best`, ... (only shows what's available) · mp3: `320`, `256`, `192`, `128`, `best` |
| `-o, --output-dir` | Save location (default: your Downloads folder + `YouTube`, e.g. `%USERPROFILE%\Downloads\YouTube` on Windows, `~/Downloads/YouTube` or `~/Hentede filer/YouTube` on Linux) |
| `--playlist` | Download the whole playlist instead of a single video |

Files are saved as `<Title>.mp4` / `<Title>.mp3` in the output folder
(playlists get their own subfolder, numbered by track order).

## While a download is running

| Key | Effect |
|---|---|
| `P` | Pause / resume the download in place |
| `S` (or `Q`) | Stop the download |

Stopping keeps the partial file on disk — run the exact same command again
and yt-dlp will resume from where it left off instead of starting over.
(Requires a real console/terminal window and `psutil`; if either is missing,
the download just runs straight through with no interactive controls.
Ctrl+C also works and cleanly stops the download.)

## Notes

- For personal/offline use of content you have the right to download.
- Video quality choices are limited to what YouTube actually offers for that
  specific video — a low-res upload won't magically get a "1080p" option.
- MP4 downloads pick the best available audio + video streams for the chosen
  resolution and merge them with ffmpeg.
- Filenames are made Windows-safe on every OS, so files can be moved
  between Linux, Windows and a NAS without trouble.
