#!/usr/bin/env bash

git_tag=`git describe --tags --abbrev=0`

cp "oraclepatchdownloader.py" "oracle_quarter_patch_downloader.py" "config.json.template" "LICENSE" "README.md" build/

cd build/
echo $git_tag
sed -i -E -e "s/[\$]Id[\$]/${git_tag}/g" *.py

zip --junk-paths --move oracle_quarter_patch_downloader_${git_tag}.zip \
"oraclepatchdownloader.py" \
"oracle_quarter_patch_downloader.py" \
"config.json.template" \
"LICENSE" \
"README.md"