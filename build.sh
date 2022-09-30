#!/usr/bin/env bash

git_tag=$(git describe --tags --abbrev=0)

mkdir -p build

cp "oraclepatchdownloader.py" "oracle_quarter_patch_downloader.py" "config.json.template" "LICENSE" "README.md" "requirements.txt" "patches.csv.template" build/

cd build/
echo "${git_tag}"
sed -i -E -e "s/[\$]Id[\$]/${git_tag}/g" *.py

chmod 0755 "oracle_quarter_patch_downloader.py"
chmod 0644 "oraclepatchdownloader.py" "config.json.template" "LICENSE" "README.md" "requirements.txt" "patches.csv.template"

zip --junk-paths --move oracle_quarter_patch_downloader_"${git_tag}".zip \
"oraclepatchdownloader.py" \
"oracle_quarter_patch_downloader.py" \
"config.json.template" \
"LICENSE" \
"README.md" \
"requirements.txt" \
"patches.csv.template"
