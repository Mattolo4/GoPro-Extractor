# GoPro extractor

Small utility to extract media metadata from a GoPro/SD-card folder and move media into organized folders for Windows.


## Setup (once)
Run these in the project folder, in **Powershell**:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
winget install --id Gyan.FFmpeg -e
```

> Re-source the terminal.

## Running
Insert the SD card and double-click `run_gopro.bat`.

From PowerShell in the project folder:

```powershell
.\.venv\Scripts\python.exe main.py --dry-run     # preview, moves nothing
.\.venv\Scripts\python.exe main.py               # actually move the files
```

#### Options

| flag | default | meaning |
|---|---|---|
| `--src`, `-s` | `D:\DCIM` | source folder (SD card) |
| `--dst`, `-d` | `...\Desktop\GoProMedia` | destination root |
| `--drive, '-D'` | `D  ` | Drive letter (e.g. ***D***). Used to formad the SD Card |
| `--max-per-day` | `4` | more files than this in a day means "trip" |
| `--dry-run` | off | log what would happen, move nothing |
| `--verbose` | off | DEBUG logging |

Defaults live at the top of `main.py` (`DEFAULT_SRC`, `DEFAULT_DST`).

Note: SD-card formatting is intentionally left **commented out** in `main.py`.
Verify your files arrived before enabling it.

> The `ffprobe` binary (from FFmpeg) is required to date videos. The script
  finds it even if your terminal's PATH is stale after installing it. Without
  it every `.mp4` lands in `Unsorted` - nothing is lost, but check it is installed.
