#!/usr/bin/python3

"""Downloads latest version of important Oracle Database and GI Patches
    - CPU and RU patches
    - OPatch
    - Autonomous Health Framework

Author: Lucas Pimentel Lellis

Configuration: modify config.json.template to config.json and fill in the
               required information.

Based on getMOSPatch v2 from Maris Elsins
(https://github.com/MarisElsins/getMOSPatch).

Requires:
    - requests
    - beautifulsoup4
    - html5lib

Version: $Id$
"""

import argparse
import json
import logging
import math
import os
import sys

from requests import RequestException

from oraclepatchdownloader import OraclePatchDownloader, OraclePatchType, OracleSupportError

_AHF_PATCH_NUMBER = "30166242"
_OPATCH_PATCH_NUMBER = "6880880"

_CONFIG_FILE = "config.json"

_LOGGER_FORMAT = r"%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_LOGGER_DATE_FMT = r"%Y-%m-%d %H:%M:%S"


def print_progress_function(file_name, file_size, total_downloaded):
    """Prints a progress indicator for the downloads

    Args:
        file_name (str): Name of the file being downloaded
        file_size (int): File's total size in bytes
        total_downloaded (int): Bytes already downloaded
    """
    formatted_file_size_mb = f"{(file_size / 1024 / 1024):.0f}"
    if file_size:
        pct = math.floor(total_downloaded * 100 / file_size)
    else:
        pct = 0

    print(
        f"\rFile Name: {file_name.ljust(40)} "
        f"File Size (MB): {formatted_file_size_mb.ljust(6)} "
        f"Downloaded (%): {str(pct).ljust(3)}",
        end="",
        flush=True,
    )

    if pct == 100:
        print("", flush=True)


def print_platforms(target_dir, patch_dler):
    """Prints a dictionary of platforms

    Args:
        target_dir (str): target_dir (str): The target directory where patches
        are downloaded.
        patch_dler (OraclePatchDownloader): Oracle Patch downloader object
    """
    platforms = patch_dler.list_platforms(target_dir)
    sorted_platforms = sorted(platforms.items(), key=lambda kv: kv[1])
    if platforms:
        print(
            "CODE   - NAME\n"
            "=========================================================="
        )
        for plat_code, plat_value in sorted_platforms:
            print(f"{plat_code:6} - {plat_value}")


def read_cli_args():
    """Reads command line interface arguments.

    Returns:
        namespace: the populated namespace of CLI arguments.
    """
    cli_args_parser = argparse.ArgumentParser(
        description="Downloads Oracle recommended patches for the current "
        "quarter."
    )
    cli_args_parser.add_argument(
        "--dry-run",
        action="store_true",
        required=False,
        help="Returns the amount that will be downloaded (in MB) "
        "but does not download the patches",
        dest="dry_run_mode",
    )
    cli_args_parser.add_argument(
        "--debug",
        action="store_true",
        required=False,
        help="Increases the level of information during the execution",
        dest="debug_mode",
    )
    cli_args_parser.add_argument(
        "-l",
        "--list-platforms-only",
        action="store_true",
        required=False,
        help="Only prints the list of platform codes and names",
        dest="list_platforms_only",
    )
    cli_args = cli_args_parser.parse_args()
    return cli_args


def main(argv=None):
    """Entry point."""
    if argv is None:
        argv = sys.argv

    cli_args = read_cli_args()

    logging_level = logging.DEBUG if cli_args.debug_mode else logging.INFO

    logging.basicConfig(
        format=_LOGGER_FORMAT,
        level=logging_level,
        datefmt=_LOGGER_DATE_FMT,
    )

    config_json = []
    try:
        with open(
            os.path.join(sys.path[0], _CONFIG_FILE), encoding="utf-8"
        ) as config_file:
            config_json = json.load(config_file)
    except (FileNotFoundError, json.decoder.JSONDecodeError) as excep:
        error_str = f"Invalid config file - {str(excep)}"
        logging.fatal(error_str)
        return 1

    if config_json is None:
        logging.fatal("Invalid config file")
        return 1

    patch_dler = OraclePatchDownloader(username=config_json["username"],
            password=config_json["password"],
            wanted_platforms=config_json["platforms"],
            target_dir=config_json["target_dir"],
            )

    logging.debug("Cleaning up the em_catalog* files")
    patch_dler.cleanup_downloader_resources()
    logging.debug("Finished")

    print("Downloading em_catalog.zip")
    try:
        patch_dler.initialize_downloader()
    except (RequestException, OracleSupportError) as excep:
        error_str = (
            f"Not able to connect to updates.oracle.com\n"
            f"Error message: {str(excep)}"
        )
        logging.fatal(error_str)
        return 1

    if cli_args.list_platforms_only:
        print_platforms(config_json["target_dir"], patch_dler)
        return 0

    total_downloaded_bytes = 0
    total_downloaded_bytes += patch_dler.download_oracle_patch(
        patch_number=_AHF_PATCH_NUMBER,
        patch_type=OraclePatchType.AHF,
        progress_function=print_progress_function,
        dry_run_mode=cli_args.dry_run_mode,
    )

    total_downloaded_bytes += patch_dler.download_oracle_patch(
        patch_number=_OPATCH_PATCH_NUMBER,
        patch_type=OraclePatchType.OPATCH,
        progress_function=print_progress_function,
        dry_run_mode=cli_args.dry_run_mode,
    )

    total_downloaded_bytes += patch_dler.download_oracle_quarter_patches(
        patch_type=OraclePatchType.QUARTER,
        ignored_releases=config_json["ignored_releases"],
        ignored_description_words=config_json["ignored_description_words"],
        progress_function=print_progress_function,
        dry_run_mode=cli_args.dry_run_mode,
    )

    # em_catalog.zip and em_catalog directory occupy around 300 MB
    total_downloaded_bytes += 300 * 1024 * 1024
    print(f"Total downloaded ~ {total_downloaded_bytes/1024/1024:,.2f} MB")

    logging.debug("Cleaning up the em_catalog* files")
    patch_dler.cleanup_downloader_resources()
    logging.debug("Finished")

    return 0


if __name__ == "__main__":
    sys.exit(main())
