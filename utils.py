import os
import glob
import subprocess
import tempfile
import json
import shutil
import logging
from PIL import Image
from PIL.ExifTags import TAGS
from  datetime import datetime, timedelta

# Full timestamp, as stored per-file in the data dicts
FORMAT_DATETIME = '%Y/%m/%d %H:%M'
# Day-only key, used to group files per day
FORMAT_DATE = '%Y/%m/%d'
# Day-only, used as an actual folder name (no slashes!)
FORMAT_FOLDER = '%Y-%m-%d'


_FFPROBE_CHECKED = False
_FFPROBE_OK = False


def ensure_ffprobe() -> bool:
    """Locate the ffprobe binary once and make it reachable.

    winget/choco update the PATH of *new* shells only, so a terminal that was
    already open when ffmpeg got installed will not see it. Look in the usual
    install folders and prepend the right one to this process' PATH.
    """
    global _FFPROBE_CHECKED, _FFPROBE_OK
    if _FFPROBE_CHECKED:
        return _FFPROBE_OK
    _FFPROBE_CHECKED = True

    if shutil.which("ffprobe"):
        _FFPROBE_OK = True
        return True

    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\*\bin"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*FFmpeg*\*\bin"),
        r"C:\ProgramData\chocolatey\bin",
        r"C:\ffmpeg\bin",
    ]
    for pattern in candidates:
        for folder in glob.glob(pattern):
            if os.path.exists(os.path.join(folder, "ffprobe.exe")):
                os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")
                logging.info(f"ffprobe found in {folder}")
                _FFPROBE_OK = True
                return True

    logging.warning("ffprobe NOT found: videos cannot be dated and will all go to "
                    "'Unsorted'. Install it with 'winget install Gyan.FFmpeg', "
                    "then open a NEW terminal.")
    return False


def check_path(path: str) -> bool:
    if not os.path.exists(path):
        logging.error(f"Path {path} does not exist.")
    return os.path.exists(path)


def get_media_number(path: str) -> int:
    if check_path(path):
        return len(os.listdir(path))
    return 0


def list_media(path: str) -> list[str]:
    if not check_path(path):
        return []
    return os.listdir(path)


def is_a_folder(path: str) -> bool:
    return os.path.isdir(path)


def format_sd_card(drive_letter: str = None, fs_type: str = "exFAT", label: str = "SDCARD"):
    """
    Format the SD card on Windows.
    """
    script = f"""
    select volume {drive_letter}
    format fs={fs_type} label={label} quick
    """
    if not drive_letter:
        logging.error("Insert a drive letter!")

    if not input(f"------- FROMAD SD CARD? -------\n\t(Y/n)") == 'Y':
        return

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as f:
        f.write(script)
        f_name = f.name
    
    try:
        subprocess.run(["diskpart", "/s", f_name], check=True, shell=True)
        logging.info(f"Drive {drive_letter}: formatted as {fs_type} with label {label}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error formatting: {e}")
    finally:
        os.remove(f_name)


def ffprobe_metadata(file: str) -> dict:
    cmd = ['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', file]
    try:
        # subprocess.run drains both pipes concurrently, so it cannot deadlock;
        # the timeout is a last-resort guard against a wedged/corrupt file.
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, check=True, timeout=60)
        if not result.stdout:
            logging.warning(f'ffprobe returned no output for {file}. stderr: {result.stderr}')
            return {}

        data = json.loads(result.stdout)

        # Look for creation_time in format.tags or streams[].tags
        creation_time = None
        fmt = data.get('format', {})
        fmt_tags = fmt.get('tags') or {}
        # common keys
        creation_time = fmt_tags.get('creation_time') or fmt_tags.get('com.apple.quicktime.creationdate')

        if not creation_time:
            for s in data.get('streams', []):
                tags = s.get('tags') or {}
                if tags.get('creation_time'):
                    creation_time = tags.get('creation_time')
                    break

        if not creation_time:
            # print(f"No creation_time metadata found for {file}")
            return {}

        # Normalize and parse common ffprobe time formats, e.g. '2024-04-03T11:20:54.000000Z' or '2024-04-03 11:20:54'
        ct = creation_time
        try:
            # remove trailing Z if present
            if ct.endswith('Z'):
                ct_norm = ct[:-1]
                try:
                    dt = datetime.strptime(ct_norm, '%Y-%m-%dT%H:%M:%S.%f')
                except ValueError:
                    dt = datetime.strptime(ct_norm, '%Y-%m-%dT%H:%M:%S')
            else:
                try:
                    dt = datetime.strptime(ct, '%Y-%m-%dT%H:%M:%S.%f')
                except ValueError:
                    try:
                        dt = datetime.strptime(ct, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        dt = datetime.fromisoformat(ct)
        except Exception as e:
            logging.warning(f'Could not parse creation_time "{creation_time}" for {file}: {e}')
            return {}

        return {'DateTime': datetime.strftime(dt, FORMAT_DATETIME)}

    except subprocess.TimeoutExpired:
        logging.warning(f"ffprobe timed out on {os.path.basename(file)}, sending it to Unsorted")
        return {}
    except FileNotFoundError:
        logging.debug(f"ffprobe binary unavailable, cannot date {os.path.basename(file)}")
        return {}
    except subprocess.CalledProcessError as e:
        logging.error(f"ffprobe error extracting metadata from {file}: {e.stderr or e}")
        return {}
    except json.JSONDecodeError as e:
        logging.error(f"ffprobe returned invalid JSON for {file}: {e}")
        return {}


def extract_metadata(file: str, tags_to_keep: list=['DateTime']) -> dict:

    _, ext = os.path.splitext(file)

    # Image files
    if ext.lower() in [".jpg", ".jpeg", ".png"]:
        try:
            with Image.open(file) as image:
                metadata_raw = image.getexif()
        except Exception as e:
            logging.warning(f"Could not read {os.path.basename(file)}: {e}")
            return {}

        if not metadata_raw:
            logging.debug(f"No Metadata_raw for {os.path.basename(file)}")
            return {}

        metadata = {}
        for tag_id, val in metadata_raw.items():

            # decode info
            try:
                tag = TAGS.get(tag_id, tag_id)

                if tag in tags_to_keep:
                    if tag == 'DateTime':
                        val = datetime.strptime(val, '%Y:%m:%d %H:%M:%S')   # convert to datetime
                        val = datetime.strftime(val, FORMAT_DATETIME)       # convert format

                    metadata[tag] = val

            except UnicodeDecodeError:
                metadata[tag] = val.decode('utf-8', 'ignore')
            except ValueError as e:
                logging.warning(f"Bad EXIF {tag} in {os.path.basename(file)}: {e}")

    # Video files
    elif ext.lower() in [".mp4", ".mov", ".avi"]:
        # no binary -> no date -> Unsorted
        if not ensure_ffprobe():        
            return {}
        metadata = ffprobe_metadata(file)
        if metadata:
            logging.debug(f"Data {os.path.basename(file)}: {metadata}")
        return metadata
    else:
        logging.debug(f"Skipping metadata extraction for non-image file {file}")
        return {}

    # print(f"Metadata for {os.path.basename(file)}:\n{metadata}")
    return metadata


def compute_files_data_dict(folder: str, files_to_keep: list, tags_to_keep: list=['DateTime']) -> dict:
    files_data_dict = {}
    media_files = list_media(folder)
    for f in media_files:
        metadata = {}
        file = os.path.join(folder, f)

        if is_a_folder(file):
            continue

        _, ext = os.path.splitext(f)
        if ext.lower() in files_to_keep:   # The file has to be moved
            # Check the where to put this image based on its metadata
            metadata = extract_metadata(file, tags_to_keep=tags_to_keep)
            if metadata:
                files_data_dict[os.path.basename(file)] = metadata['DateTime']

    # Sort the dictionary by datetime
    sorted_dict = sorted(files_data_dict.items(), key=lambda x:
        datetime.strptime(x[1], FORMAT_DATETIME), reverse=False
    )
    return dict(sorted_dict)


def compute_media_list_dict(data_dict: dict) -> dict:
    """Group the {file: timestamp} dict into {day: [files]}, keeping day order."""
    data_medialist_dict = {}
    for file, date in data_dict.items():
        date = datetime.strptime(date, FORMAT_DATETIME)
        date = datetime.strftime(date, FORMAT_DATE)

        if date not in data_medialist_dict.keys():
            data_medialist_dict[date] = [file]
        else:
            data_medialist_dict[date].append(file)

    return data_medialist_dict


def compute_folder_names_dict(media_list_dict: dict, max_photo_per_day: int = 4) -> dict:
    """Decide, per day, which destination folder its files belong to.

    - exactly 1 photo in a day        --> 'Photo_at_home'
    - <= max_photo_per_day in a day   --> 'Extra'
    - >  max_photo_per_day in a day   --> a trip, named after its FIRST day.
      Consecutive days that are also over the threshold are merged into it.
    """
    folder_names = {}
    days_to_skip = set()
    delta_1_day = timedelta(days=1)

    for date, files in media_list_dict.items():
        if date in days_to_skip:                                # already merged into a trip
            continue

        if len(files) == 1:                                     # 1 Photo per day --> the photo at home
            _, ext = os.path.splitext(files[0])
            if ext.lower() in [".jpg", ".jpeg", ".png"]:        # If it s 1 only image it s the photo at home
                folder_names = add_items_to_dict(folder_names, 'Photo_at_home', files)
            else:                                               # 1 Video per day --> Extra
                folder_names = add_items_to_dict(folder_names, 'Extra', files)

        elif len(files) <= max_photo_per_day:                   # it s random photos --> Extra
            folder_names = add_items_to_dict(folder_names, 'Extra', files)

        else:                                                   # More than max per day --> On a trip
            trip_name = datetime.strftime(datetime.strptime(date, FORMAT_DATE), FORMAT_FOLDER)
            folder_names = add_items_to_dict(folder_names, trip_name, files)

            day = date
            while True:                                         # walk forward while the trip continues
                next_day = datetime.strftime(datetime.strptime(day, FORMAT_DATE) + delta_1_day, FORMAT_DATE)
                next_files = media_list_dict.get(next_day)

                if next_files is None or len(next_files) <= max_photo_per_day:
                    break

                logging.info(f"Trip {trip_name}: merging day {next_day}")
                folder_names = add_items_to_dict(folder_names, trip_name, next_files)
                days_to_skip.add(next_day)
                day = next_day

    return folder_names


def add_items_to_dict(dic: dict, key: str, value) -> dict:
    if key not in dic:
        dic[key] = list(value) if isinstance(value, list) else [value]
    elif isinstance(value, list):
        dic[key].extend(value)
    else:
        dic[key].append(value)
    return dic