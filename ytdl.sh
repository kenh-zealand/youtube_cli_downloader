#!/usr/bin/env bash
# Linux launcher - the counterpart to ytdl.bat.
# Works from anywhere, also via a symlink (e.g. ~/.local/bin/ytdl).
exec python3 "$(dirname "$(readlink -f "$0")")/ytdl.py" "$@"
