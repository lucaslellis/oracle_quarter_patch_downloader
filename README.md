# Oracle Quarter Patch Downloader

Downloads latest version of important Oracle Database and GI Patches:

* CPU and RU patches
* OPatch
* Autonomous Health Framework

Based on [getMosPatch from Maris Elsins.](https://github.com/MarisElsins/getMOSPatch/)

## Requirements

* Python >= 3.6
* Packages listed on [requirements.txt](requirements.txt)

## Instructions

* Ensure that the packages `python3` and `python3-pip` are installed (RHEL 7.x / OEL 7.x)
* Install required packages with pip3

  ```bash
  pip3 install -r requirements.txt --user
  ```

* Download the latest [release](../../releases/latest) and unzip it on a
  directory
* Rename [config.json.template](config.json.template) to `config.json` and fill in the required variables
* Set the execution permission

  ```bash
  chmod +x oracle_quarter_patch_downloader.py
  ```

* Run in dry-run mode to estimate the space needed

  ```bash
  ./oracle_quarter_patch_downloader.py --dry-run
  ```

* Run in normal mode to download the patches

  ```bash
  nohup ./oracle_quarter_patch_downloader.py > oracle_quarter_patch_downloader.log 2>&1 &
  tail -100f oracle_quarter_patch_downloader.log
  ```
