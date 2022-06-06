#!/usr/bin/python3

"""Downloads latest version of important Oracle Database and GI Patches
    - CPU and RU patches
    - OPatch
    - Autonomous Health Framework

Author: Lucas Pimentel Lellis

Configuration: modify config.json.template to config.json and fill in the
               required information.

Requires:
    - requests
    - beautifulsoup4
    - html5lib
"""

import argparse
import json
import math
import os
import sys

from requests import RequestException

from oraclepatchdownloader import OraclePatchDownloader

_AHF_PATCH_NUMBER = "30166242"
_OPATCH_PATCH_NUMBER = "6880880"

_CONFIG_FILE = "config.json"


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
        "-d",
        "--dry-run",
        action="store_true",
        required=False,
        help="Returns the amount that will be downloaded (in MB) "
        "but does not download the patches",
        dest="dry_run_mode",
    )
    cli_args = cli_args_parser.parse_args()
    return cli_args


def main(argv=None):
    """Entry point."""
    if argv is None:
        argv = sys.argv

    cli_args = read_cli_args()

    config_json = []
    with open(
        os.path.join(sys.path[0], _CONFIG_FILE), encoding="utf-8"
    ) as config_file:
        config_json = json.load(config_file)

    if config_json is None:
        print("Invalid config file", file=sys.stderr)
        return 1

    patch_dler = OraclePatchDownloader()

    try:
        patch_dler.initialize_downloader(
            config_json["platforms"],
            config_json["target_dir"],
            config_json["username"],
            config_json["password"],
        )
    except RequestException as excep:
        print("Not able to connect to updates.oracle.com", file=sys.stderr)
        print("Error message: " + str(excep))
        return 1

    total_downloaded_bytes = 0
    total_downloaded_bytes += patch_dler.download_oracle_patch(
        patch_number=_AHF_PATCH_NUMBER,
        target_dir=config_json["target_dir"] + os.path.sep + "ahf",
        progress_function=print_progress_function,
        dry_run_mode=cli_args.dry_run_mode,
    )

    total_downloaded_bytes += patch_dler.download_oracle_patch(
        patch_number=_OPATCH_PATCH_NUMBER,
        target_dir=config_json["target_dir"] + os.path.sep + "opatch",
        progress_function=print_progress_function,
        dry_run_mode=cli_args.dry_run_mode,
    )

    total_downloaded_bytes += patch_dler.download_oracle_quarter_patches(
        target_dir=config_json["target_dir"] + os.path.sep + "quarter_patches",
        ignored_releases=config_json["ignored_releases"],
        ignored_description_words=config_json["ignored_description_words"],
        progress_function=print_progress_function,
        dry_run_mode=cli_args.dry_run_mode,
    )

    # em_catalog.zip and em_catalog directory occupy around 300 MB
    total_downloaded_bytes += 300 * 1024 * 1024
    print(f"Total downloaded ~ {total_downloaded_bytes/1024/1024:,.2f} MB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
