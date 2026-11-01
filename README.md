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

### Debian / Ubuntu (recommended: pipx)

```bash
sudo apt install ffmpeg pipx git
pipx ensurepath          # then open a new terminal
pipx install yt-dlp
pipx install git+https://github.com/kenh-zealand/youtube_cli_downloader
```

That's it — `ytdl` now works from any folder, and there's no code folder to
keep track of (psutil is installed automatically).

Optional: add **YouTube Downloader** to your applications menu. It opens a
terminal window that asks for URL, format and quality, and stays open at the
end so you can read the result:

```bash
ytdl --install-desktop       # remove again with: ytdl --uninstall-desktop
```

Keeping things up to date:

```bash
pipx upgrade yt-dlp                   # do this first if downloads suddenly fail
pipx upgrade youtube-cli-downloader   # get new versions of this tool
```

`yt-dlp` is installed with pipx rather than apt because YouTube changes
often and the apt version lags behind.

To uninstall: `ytdl --uninstall-desktop` and `pipx uninstall youtube-cli-downloader`.

#### Alternative: run from a git checkout

```bash
sudo apt install python3-psutil
git clone https://github.com/kenh-zealand/youtube_cli_downloader
ln -s "$PWD/youtube_cli_downloader/ytdl.sh" ~/.local/bin/ytdl
```

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
ytdl             # after pipx install (or ./ytdl.sh from a git checkout)
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
