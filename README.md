# Oracle Quarter Patch Downloader

Downloads latest version of important Oracle Database and GI Patches based on the Automated Release Update (ARU)
catalog (same catalog used by Enterprise Manager).

* CPU and RU patches
* OPatch
* Autonomous Health Framework

Based on [getMOSPatch from Maris Elsins.](https://github.com/MarisElsins/getMOSPatch/) If you need to download an
specific set of patches, [getMOSPatch](https://github.com/MarisElsins/getMOSPatch/) is the better option.

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

* Command-line options

  ```default
  [lucas@vm01 oracle_quarter_patch_downloader]$ ./oracle_quarter_patch_downloader.py -h
  usage: oracle_quarter_patch_downloader.py [-h] [--dry-run] [--debug] [-l]

  Downloads Oracle recommended patches for the current quarter.

  optional arguments:
    -h, --help            show this help message and exit
    --dry-run             Returns the amount that will be downloaded (in MB) but
                          does not download the patches
    --debug               Increases the level of information during the
                          execution
    -l, --list-platforms-only
                          Only prints the list of platform codes and names
  [lucas@vm01 oracle_quarter_patch_downloader]$
  ```

* List the platforms available and choose which ones should have the patches downloaded by filling the `platforms`
  section on `config.json`

* Run in dry-run mode to estimate the space needed

  ```bash
  ./oracle_quarter_patch_downloader.py --dry-run
  ```

* In case you need to restrict even further the releases for which the patches are downloaded, you can do so by adding
  regular expressions on the `platforms` section of `config.json`

* Options `ignored_releases` and `ignored_description_words` accept case-sensitive regular expressions, which must be
  escaped. Recommended tools to escape the strings:

  * [Free Formatter - Web](https://www.freeformatter.com/json-escape.html)
  * [DevToys - Desktop/Win](https://devtoys.app/)

* After modifying `config.json`, a new dry-run execution is suggested to confirm the changes are effective

* Run in normal mode to download the patches

  ```bash
  nohup ./oracle_quarter_patch_downloader.py > oracle_quarter_patch_downloader.log 2>&1 &
  tail -100f oracle_quarter_patch_downloader.log
  ```

* For platforms and releases specified on `config.json`, it creates the following
  directory structure:

  ```bash
  [lucas@vm01 patches]$ tree
  .
  ├── ahf
  │   ├── AHF-AIX-PPC64_v22.1.1.zip
  │   ├── AHF-LINUX_v22.1.1.zip
  │   └── AHF-Win_v22.1.1.zip
  ├── opatch
  │   ├── p6880880_101000_AIX64-5L.zip
  │   ├── p6880880_101000_Linux-x86-64.zip
  │   ├── p6880880_101000_MSWIN-x86-64.zip
  │   ├── p6880880_102000_AIX64-5L.zip
  │   ├── p6880880_102000_Linux-x86-64.zip
  │   ├── p6880880_102000_MSWIN-x86-64.zip
  │   ├── p6880880_111000_AIX64-5L.zip
  │   ├── p6880880_111000_Linux-x86-64.zip
  │   ├── p6880880_111000_MSWIN-x86-64.zip
  │   ├── p6880880_112000_AIX64-5L.zip
  │   ├── p6880880_112000_Linux-x86-64.zip
  │   ├── p6880880_112000_MSWIN-x86-64.zip
  │   ├── p6880880_121010_AIX64-5L.zip
  │   ├── p6880880_121010_Linux-x86-64.zip
  │   ├── p6880880_121010_MSWIN-x86-64.zip
  │   ├── p6880880_122010_AIX64-5L.zip
  │   ├── p6880880_122010_Linux-x86-64.zip
  │   ├── p6880880_122010_MSWIN-x86-64.zip
  │   ├── p6880880_131000_Generic.zip
  │   ├── p6880880_132000_Generic.zip
  │   ├── p6880880_139000_Generic.zip
  │   ├── p6880880_180000_AIX64-5L.zip
  │   ├── p6880880_180000_Linux-x86-64.zip
  │   ├── p6880880_180000_MSWIN-x86-64.zip
  │   ├── p6880880_190000_AIX64-5L.zip
  │   ├── p6880880_190000_Linux-x86-64.zip
  │   ├── p6880880_190000_MSWIN-x86-64.zip
  │   ├── p6880880_200000_AIX64-5L.zip
  │   ├── p6880880_200000_Linux-x86-64.zip
  │   ├── p6880880_200000_MSWIN-x86-64.zip
  │   ├── p6880880_210000_AIX64-5L.zip
  │   ├── p6880880_210000_Linux-x86-64.zip
  │   └── p6880880_210000_MSWIN-x86-64.zip
  └── quarter_patches
      ├── 12.1.0.1.0
      │   ├── IBM_AIX_on_POWER_Systems_64-bit
      │   │   ├── description.txt
      │   │   ├── p23054354_121010_AIX64-5L.zip
      │   │   ├── p23177541_121010_AIX64-5L.zip
      │   │   └── p23273958_121010_AIX64-5L.zip
      │   ├── Linux_x86-64
      │   │   ├── description.txt
      │   │   ├── p23054354_121010_Linux-x86-64.zip
      │   │   ├── p23177541_121010_Linux-x86-64.zip
      │   │   └── p23273935_121010_Linux-x86-64.zip
      │   └── Microsoft_Windows_x64_64-bit
      │       ├── description.txt
      │       └── p22839627_121010_MSWIN-x86-64.zip
      ├── 12.1.0.2.0
      │   ├── IBM_AIX_on_POWER_Systems_64-bit
      │   │   ├── description.txt
      │   │   ├── p19141838_121010_AIX64-5L.zip
      │   │   ├── p33711081_121020_AIX64-5L.zip
      │   │   ├── p33808385_121020_AIX64-5L.zip
      │   │   ├── p33829718_121020_AIX64-5L.zip
      │   │   └── p33880550_121020_AIX64-5L.zip
      │   ├── Linux_x86-64
      │   │   ├── description.txt
      │   │   ├── p19141838_121010_Linux-x86-64.zip
      │   │   ├── p20877664_121025DBEngSysandDBIM_Linux-x86-64.zip
      │   │   ├── p21373076_121020_Linux-x86-64.zip
      │   │   ├── p33711081_121020_Linux-x86-64.zip
      │   │   ├── p33808385_121020_Linux-x86-64.zip
      │   │   ├── p33829718_121020_Linux-x86-64.zip
      │   │   └── p33880550_121020_Linux-x86-64.zip
      │   └── Microsoft_Windows_x64_64-bit
      │       ├── description.txt
      │       ├── p33777450_121020_MSWIN-x86-64.zip
      │       └── p33881387_121020_MSWIN-x86-64.zip
      ├── 12.2.0.1.0
      │   ├── IBM_AIX_on_POWER_Systems_64-bit
      │   │   ├── description.txt
      │   │   ├── p24416451_122010_AIX64-5L.zip
      │   │   ├── p27986817_12201171017DBRU_AIX64-5L.zip
      │   │   └── p33561275_122010_AIX64-5L.zip
      │   ├── Linux_x86-64
      │   │   ├── description.txt
      │   │   ├── p24416451_122010_Linux-x86-64.zip
      │   │   └── p33561275_122010_Linux-x86-64.zip
      │   └── Microsoft_Windows_x64_64-bit
      │       ├── description.txt
      │       ├── p33488333_122010_MSWIN-x86-64.zip
      │       └── p33577550_122010_MSWIN-x86-64.zip
      ├── 18.0.0.0.0
      │   ├── IBM_AIX_on_POWER_Systems_64-bit
      │   │   ├── description.txt
      │   │   ├── p32524152_180000_AIX64-5L.zip
      │   │   ├── p32524155_180000_AIX64-5L.zip
      │   │   └── p32552752_180000_AIX64-5L.zip
      │   ├── Linux_x86-64
      │   │   ├── description.txt
      │   │   ├── p32524152_180000_Linux-x86-64.zip
      │   │   ├── p32524155_180000_Linux-x86-64.zip
      │   │   └── p32552752_180000_Linux-x86-64.zip
      │   └── Microsoft_Windows_x64_64-bit
      │       ├── description.txt
      │       ├── p32438481_180000_MSWIN-x86-64.zip
      │       └── p32552752_180000_MSWIN-x86-64.zip
      ├── 19.0.0.0.0
      │   ├── IBM_AIX_on_POWER_Systems_64-bit
      │   │   ├── description.txt
      │   │   ├── p33803476_190000_AIX64-5L.zip
      │   │   ├── p33806152_190000_AIX64-5L.zip
      │   │   └── p33808367_190000_AIX64-5L.zip
      │   ├── Linux_x86-64
      │   │   ├── description.txt
      │   │   ├── p33803476_190000_Linux-x86-64.zip
      │   │   ├── p33806152_190000_Linux-x86-64.zip
      │   │   └── p33808367_190000_Linux-x86-64.zip
      │   └── Microsoft_Windows_x64_64-bit
      │       ├── description.txt
      │       └── p33808367_190000_MSWIN-x86-64.zip
      └── 21.0.0.0.0
          └── Linux_x86-64
              ├── description.txt
              ├── p33843745_210000_Linux-x86-64.zip
              └── p33859395_210000_Linux-x86-64.zip

  25 directories, 97 files
  [lucas@vm01 patches]$
  ```

* Each `description.txt` contains a list of the patches downloaded on that folder with a description of the patch.
  Example:

  ```default
  [lucas@vm01 patches]$ cat quarter_patches/19.0.0.0.0/Linux_x86-64/description.txt
  p33806152_190000_Linux-x86-64.zip - DATABASE RELEASE UPDATE 19.15.0.0.0
  p33808367_190000_Linux-x86-64.zip - OJVM RELEASE UPDATE 19.15.0.0.0
  p33803476_190000_Linux-x86-64.zip - GI RELEASE UPDATE 19.15.0.0.0
  [lucas@vm01 patches]$
  ```
