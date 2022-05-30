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

_AHF_PATCH_NUMBER = "30166242"
_OPATCH_PATCH_NUMBER = "6880880"

_CONFIG_FILE = "config.json"

import json
import math
import os
import sys

from oraclepatchdownloader import OraclePatchDownloader


def print_progress_function(file_name, file_size, total_downloaded):
    formatted_file_size_mb = "{:.0f}".format(file_size / 1024 / 1024)
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


def main(argv=None):
    """Entry point."""

    config_json = []
    with open(os.path.join(sys.path[0], _CONFIG_FILE)) as config_file:
        config_json = json.load(config_file)

    if config_json is None:
        print("Invalid config file", file=sys.stderr)
        return 1

    patch_dler = OraclePatchDownloader(
        config_json["username"], config_json["password"]
    )

    patch_dler.download_oracle_patch(
        _AHF_PATCH_NUMBER,
        config_json["platforms"],
        target_dir=config_json["target_dir"],
        progress_function=print_progress_function,
    )

    patch_dler.download_oracle_patch(
        _OPATCH_PATCH_NUMBER,
        config_json["platforms"],
        target_dir=config_json["target_dir"],
        progress_function=print_progress_function,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
