import os
import shutil
import argparse
import logging
import utils
from tqdm import tqdm
from datetime import datetime

UNSORTED_FOLDER = "Unsorted"

class GoProExtractor():
    def __init__(self, src_folder: str = "D:\\DCIM", dst_folder: str = "C:\\Users\\matte\\OneDrive\\Desktop\\GoProMedia", dry_run: bool = False, max_photo_per_day: int = 4):
        self.sd_card_path = src_folder

        # The folder containing all the media stored in other folders
        self.dst_folder = dst_folder
        self.files_to_keep = [".mp4", ".jpg"]
        self.tags_to_keep = ['DateTime']
        self.folder_names_global = {}
        self.max_photo_per_day = max_photo_per_day
        # kept files whose capture date could not be read -> go to Unsorted
        self.undated_files = []

        self.dry_run = dry_run


    def collect_media_files(self, folder: str) -> list:
        """Cheap recursive walk: collects path of files to be moved.
        """
        found = []
        for f in utils.list_media(folder):
            file_name = os.path.join(folder, f)
            if utils.is_a_folder(file_name):        # if it s a folder, re-call
                logging.debug(f"Folder: {file_name}")
                found.extend(self.collect_media_files(file_name))
                continue

            _, ext = os.path.splitext(f)
            if ext.lower() in self.files_to_keep:
                found.append(file_name)
        return found


    def all_media_in_dict(self, files_data_all: dict, folder: str="D:\\DCIM") -> dict:
        local_dict = {}
        if files_data_all is None:
            logging.warning("Not-existing dict, returning!")
            return {}

        print(f"Checking {folder} ...")
        media_files = self.collect_media_files(folder)

        with tqdm(total=len(media_files), desc="Sorting fotos..", unit="file") as pbar:
            for file_name in media_files:
                metadata = utils.extract_metadata(file_name, self.tags_to_keep)
                if metadata.get('DateTime'):
                    local_dict[file_name] = metadata['DateTime']
                else:
                    # no readable date put in Unsorted
                    self.undated_files.append(file_name)
                pbar.update(1)
                pbar.set_postfix({"dated": len(local_dict), "undated": len(self.undated_files)})

        # reported after the bar closes so it does not chop the bar in half
        for f in self.undated_files:
            logging.warning(f"No capture date for {os.path.basename(f)}, sending it to {UNSORTED_FOLDER}")

        sorted_dict = dict(sorted(local_dict.items(), key=lambda x:
            datetime.strptime(x[1], utils.FORMAT_DATETIME), reverse=False
        ))

        logging.info(f"{len(sorted_dict)} dated file(s), {len(self.undated_files)} undated")
        files_data_all.update(sorted_dict)
        return files_data_all


    def empty_folder(self, all_data_dict: dict) -> dict:
        # global sort (least recent -> most recent) across every subfolder
        all_data_dict = dict(sorted(all_data_dict.items(), key=lambda x:
            datetime.strptime(x[1], utils.FORMAT_DATETIME), reverse=False
        ))

        data_medialist_dict = utils.compute_media_list_dict(all_data_dict)
        folder_names_dict = utils.compute_folder_names_dict(data_medialist_dict, self.max_photo_per_day)

        if self.undated_files:
            folder_names_dict[UNSORTED_FOLDER] = list(self.undated_files)

        items = sum(len(files) for files in folder_names_dict.values())
        i = 0
        with tqdm(total=items, desc="Moving files", unit="file", )  as pbar:

            for date, files in folder_names_dict.items():
                for file in files:
                    file_name = os.path.basename(file)

                    _, ext = os.path.splitext(file_name)
                    if ext.lower() in self.files_to_keep:   # The file has to be moved
                        dst_folder = date
                        self.move_file(file, dst_folder)
                    else:
                        logging.debug(f"File {file_name} does not match the criteria.")

                    i += 1
                    pbar.update(1)
                    pbar.set_postfix({"moved": i})
        return folder_names_dict

    def move_file(self, src_file: str, dst_folder: str):
        file_name = os.path.basename(src_file)
        dst_path = os.path.join(self.dst_folder, dst_folder)
        dst_file = os.path.join(dst_path, file_name)
        try:
            os.makedirs(dst_path, exist_ok=True)
            stem, ext = os.path.splitext(file_name)
            n = 1
            while os.path.exists(dst_file):
                dst_file = os.path.join(dst_path, f"{stem}_{n}{ext}")
                n += 1

            if self.dry_run:
                logging.info(f"Dry-run: would move {src_file} -> {dst_file}")
            else:
                shutil.move(src=src_file, dst=dst_file)
                logging.info(f"Moved {src_file} -> {dst_file}")
        except Exception as e:
            logging.error(f"Error moving {src_file} to {dst_file}: {e}")



# Insert the SD card and just run the script: these are the defaults.
DEFAULT_SRC = r'D:\DCIM'
DEFAULT_DST = r'C:\Users\matte\OneDrive\Desktop\GoProMedia'


def main(argv=None):
    parser = argparse.ArgumentParser(description='GoPro media extractor')
    parser.add_argument('--src', '-s', default=DEFAULT_SRC, help='Source media folder (SD card)')
    parser.add_argument('--dst', '-d', default=DEFAULT_DST, help='Destination root folder')
    parser.add_argument('--max-per-day', type=int, default=4, help='More than this many files in a day means "trip"')
    parser.add_argument('--dry-run', action='store_true', help='Do not perform file moves, only log actions')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging (DEBUG)')
    parser.add_argument('--drive', '-D', default='D', help='Drive letter (e.g. \'D\')')
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format='%(levelname)s: %(message)s')
    logging.getLogger('PIL').setLevel(logging.INFO)

    if not utils.check_path(args.src):
        logging.error(f"Source {args.src} not found - is the SD card inserted?")
        return 1

    extractor = GoProExtractor(
        src_folder=args.src, 
        dst_folder=args.dst,
        dry_run=args.dry_run, 
        max_photo_per_day=args.max_per_day
    )
    all_data = {}
    extractor.all_media_in_dict(all_data, args.src)
    logging.info(f"All data size: {len(all_data)}")
    folders = extractor.empty_folder(all_data)

    print(f"\n=== {'Creating' if args.dry_run else 'Created'} in {args.dst} ===")
    for name in sorted(folders):
        print(f"  {name:<16} {len(folders[name]):>4} files")
    print(f"=== {sum(len(f) for f in folders.values())} files in {len(folders)} folders ===\n")

    # UNCOMMENT TO FORMAT SD CARD 
    # utils.format_sd_card(args.drive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())