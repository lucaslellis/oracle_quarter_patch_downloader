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
import csv
import getpass
import math
import os
import sys

from requests import RequestException

from oraclepatchdownloader import (
    OraclePatchDownloader,
    OraclePatchType,
    OracleSupportError,
)

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


def print_platforms(patch_dler):
    """Prints a dictionary of platforms

    Args:
        patch_dler (OraclePatchDownloader): Oracle Patch downloader object
    """
    platforms = patch_dler.list_platforms()
    sorted_platforms = sorted(platforms.items(), key=lambda kv: kv[1])
    if platforms:
        print(
            "CODE   - NAME\n"
            "=========================================================="
        )
        for plat_code, plat_value in sorted_platforms:
            print(f"{plat_code:6} - {plat_value}")


def handle_file(filehandle, patch_dler, dry_run_mode=True):
    """Download the patches listed in the passed file
    Arguments:
        filehandle (FILE): The file containing the patch list
        patch_dler: The patch downloader object.
        dry_run_mode (bool): Whether dry run has been passed.

        The file contains a list of patches to download which will end
        up in the patchinfo array as:
        0 - Patch number
        1 - CPU | version (Ignored)
        2 - Description (Ignored)
        3 - Group (Download subdirectory)
        4 - Platform. Needs to be as per the output of -l
    """
    platforms = patch_dler.list_platforms()
    bytes_downloaded = 0

    with filehandle as patch_list_handle:
        patchreader = csv.reader(
            filter(lambda row: row[0] != "#", patch_list_handle)
        )
        for patchinfo in patchreader:
            if len(patchinfo) != 5:
                logging.warning(
                    "Skipping as line doesn't have 5 columns: %s",
                    ",".join(map(str, patchinfo)),
                )
                continue
            logging.debug(
                "Downloading Patch %s for platform %s",
                patchinfo[0],
                patchinfo[4],
            )
            # Is the platform a number, if not convert it.
            if patchinfo[4].isnumeric():
                platform = int(patchinfo[4])
            # If platform is blank, use generic platform (Hard coded)
            elif not patchinfo[4].strip():
                platform = 2000
            else:
                if patchinfo[4] in platforms.values():
                    platform = list(platforms.keys())[
                        list(platforms.values()).index(patchinfo[4])
                    ]
                else:
                    logging.warning(
                        "Platform (%s) for patch %s} is missing."
                        " Skipping this line.",
                        patchinfo[4],
                        patchinfo[0],
                    )
                    continue

            patchsz = patch_dler.download_patch_files(
                patchinfo[0],
                str(platform),
                patchinfo[3],
                print_progress_function,
                dry_run_mode,
            )
            if patchsz == 0:
                logging.warning('No data downloaded for patch %s platform %s.',
                    patchinfo[0],
                    patchinfo[4])
            bytes_downloaded += patchsz
    return bytes_downloaded


def get_ora_pass(argpass, jsonpass):
    """Returns the password for Oracle support. If specified on the
    command line returns that, if prompt requested on the command line
    prompt and read the password, otherwise returns the password from
    the JSON config.

    Args:
        argpass (str): Password from argument object
        jsonpass (str): Password from json config file

    Returns:
        str: The password to  use
    """
    if argpass:
        if argpass == "*":
            return getpass.getpass(prompt="Oracle Support Password: ")
        return argpass
    return jsonpass


def get_ora_user(arguser, jsonuser):
    """Returns the username for Oracle support. If specified on the
    command line returns that, otherwise returns the username from
    the JSON config.

    Args:
        arguser (str): User name from argument object
        jsonuser (str): User name from json config file

    Returns:
        str: The username to  use
    """
    if arguser:
        return arguser
    return jsonuser


def read_cli_args():
    """Reads command line interface arguments.

    Returns:
        namespace: the populated namespace of CLI arguments.
    """
    cli_args_parser = argparse.ArgumentParser(
        description="Downloads Oracle recommended patches for the current "
        "quarter. Alternatively download patches specified in a csv file.",
        prefix_chars="+-",
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
        "-f",
        type=argparse.FileType("r", encoding="utf-8"),
        action="store",
        required=False,
        help="Download the list of patches in the specified CSV file. "
        "See patches.csv.template for an example. If this is not "
        "specified, the recomended patches are downloaded.",
        dest="patch_list_file",
    )
    cli_args_parser.add_argument(
        "-p",
        "--password",
        type=str,
        nargs="?",
        const="*",
        required=False,
        help="Oracle support password. "
        "Prompted if not specified on command line. "
        "Read from json config if omitted.",
        dest="oracle_password",
    )
    cli_args_parser.add_argument(
        "-u",
        "--user",
        type=str,
        action="store",
        required=False,
        help="Username to connect to Oracle Support. "
        "Read from json config if omitted.",
        dest="oracle_username",
    )
    cli_args_parser.add_argument(
        "-l",
        "--list-platforms-only",
        action="store_true",
        required=False,
        help="Only prints the list of platform codes and names",
        dest="list_platforms_only",
    )
    cli_args_parser.add_argument(
        "-r",
        "--refresh-catalog",
        action="store_true",
        required=False,
        help="Forcefully download a new em_catalog.zip",
        dest="refresh_catalog",
    )

    cli_args = cli_args_parser.parse_args()
    return cli_args


def main(argv=None):
    """Entry point."""

    if argv is None:
        argv = sys.argv

    total_downloaded_bytes = 0
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

    patch_dler = OraclePatchDownloader(
        username=get_ora_user(
            cli_args.oracle_username, config_json["username"]
        ),
        password=get_ora_pass(
            cli_args.oracle_password, config_json["password"]
        ),
        wanted_platforms=config_json["platforms"],
        target_dir=config_json["target_dir"],
    )

    if cli_args.refresh_catalog:
        logging.debug("Cleaning up the em_catalog* files")
        patch_dler.cleanup_downloader_resources()
        logging.debug("Finished")

    print("Initializing Downloader.")
    try:
        total_downloaded_bytes = patch_dler.initialize_downloader(
            cli_args.patch_list_file
        )
    except (RequestException, OracleSupportError) as excep:
        error_str = (
            f"Not able to connect to updates.oracle.com\n"
            f"Error message: {str(excep)}"
        )
        logging.fatal(error_str)
        return 1

    if cli_args.list_platforms_only:
        print_platforms(patch_dler)
        return 0

    if cli_args.patch_list_file:
        logging.debug("File %s passed", cli_args.patch_list_file)
        total_downloaded_bytes += handle_file(
            cli_args.patch_list_file,
            patch_dler,
            cli_args.dry_run_mode,
        )

    else:
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

    # Looks like original idea was to indicate file size rather than
    # download amount.
    ## em_catalog.zip and em_catalog directory occupy around 300 MB
    # total_downloaded_bytes += 300 * 1024 * 1024
    print(f"Total downloaded ~ {total_downloaded_bytes/1024/1024:,.2f} MB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
