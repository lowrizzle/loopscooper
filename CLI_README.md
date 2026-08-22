# Loopscooper CLI Reference

## loopscooper

![`loopscooper --help`](img/pymusiclooper.svg)

A single command for detecting and exporting seamless audio loops.

```
Usage: loopscooper [OPTIONS] [FILENAME]

A program for detecting and exporting seamless music loops for game audio.

Options:
  -d, --debug      Enables debugging mode.
  -v, --verbose    Enables verbose logging output.
  --version        Show the version and exit.
  --url TEXT       Link to a YouTube video (or any stream supported by yt-dlp).
  --help           Show this message and exit.
```

### Examples

```bash
# Basic usage — finds file in CWD, auto-detects BPM, interactive preview & export
loopscooper song.wav

# Absolute path
loopscooper /Users/youruser/Music/song.wav

# Relative path
loopscooper ./music/song.wav
```

If the file is not found in the current working directory, the script will attempt to resolve it as a relative or absolute path. If still not found, it errors with a message asking the user to provide a valid file path.
