"""Module to support downloading Oracle Patches

Author: Lucas Pimentel Lellis

Requires:
    - requests
    - beautifulsoup4
    - html5lib

Version: $Id$

"""

import collections
import datetime
import hashlib
import logging
import os
import pathlib
import re
import shutil
import xml.etree
import zipfile
from http import HTTPStatus

import requests
from bs4 import BeautifulSoup

# Mandatory as it's the only way to escape Oracle's JavaScript check
_HEADERS = {"User-Agent": "Wget/1.20.3"}

# Mandatory as sometimes Oracle's HTML is broken
_DEFAULT_HTML_PARSER = "html5lib"

_CHUNK_SIZE = 2097152  # 2 MB

_REQUEST_TIMEOUT = 30  # seconds

_DESC_FILE_NAME = "description.txt"


class OraclePatchDownloader:
    """Class that enables downloading Oracle patches

    Author: Lucas Pimentel Lellis
    """

    def __init__(self):
        """Creates an instance of OraclePatchDownloader
        """
        self.__cookie_jar = None
        self.__platforms = None
        self.__download_links = None
        self.__db_release_components = None
        self.__all_db_patches = None
        self.__recommended_db_patches = None
        self.username = None
        self.password = None

    def list_platforms(
        self, target_dir
    ) -> list:
        """Returns a dictionary of all platforms containing a tuple for each
        line with a code and a description.

        Args:
            target_dir (str): The target directory where patches are downloaded

        Returns:
            dict: Dictionary of platforms
        """
        aru_platforms_doc = xml.etree.ElementTree.parse(
            target_dir + os.path.sep + "em_catalog" + os.path.sep + "aru_platforms.xml"
        )
        aru_platforms_doc_root = aru_platforms_doc.getroot()

        platforms = {
            tag.get("id"): tag.text.strip()
            for tag in aru_platforms_doc_root.iterfind("./platform")
        }

        return platforms

    def download_oracle_patch(
        self,
        patch_number,
        target_dir=".",
        progress_function=None,
        dry_run_mode=True,
    ) -> int:
        """Downloads an Oracle Patch for the downloader platforms
        given a patch number,
        a target directory (optional) and a function to display
        download progress (optional).

        Args:
            patch_number (str): an Oracle patch number
            target_dir (str): The target directory where patches are downloaded
                Defaults to ".".
            progress_function (function): a function that will be called with
                the following parameters:
                    - (str): file name
                    - (int): file size in bytes
                    - (int): total downloaded in bytes
                Defaults to None.
            dry_run_mode: Returns the amount downloaded in bytes without
            actually downloading the files. Defaults to True.

        Returns:
            int: Total downloaded in bytes
        """
        if not self.__cookie_jar:
            logging.fatal("Please call initialize_downloader() first")
            return 1

        if self.__download_links:
            self.__download_links.clear()

        self.__build_list_download_links(patch_number)

        pathlib.Path(target_dir).mkdir(parents=True, exist_ok=True)

        total_downloaded_bytes = 0
        for dl_link in self.__download_links:
            try:
                oracle_checksum = self.__obtain_sha256_checksum_oracle(dl_link)
                total_downloaded_bytes += self.__download_link(
                    dl_link,
                    oracle_checksum,
                    target_dir,
                    progress_function,
                    dry_run_mode,
                )
            except ChecksumMismatch:
                local_filename = (
                    target_dir
                    + os.path.sep
                    + self.__extract_file_name_from_url(dl_link)
                )
                error_str = (
                    f"{local_filename}"
                    " checksum does not match Oracle's checksum. "
                    "Please remove it manually and download it again."
                )
                logging.error(error_str)

        return total_downloaded_bytes

    def download_oracle_quarter_patches(
        self,
        target_dir,
        ignored_releases,
        ignored_description_words,
        progress_function,
        dry_run_mode=True,
    ) -> int:
        """Downloads all Oracle DB and GI recommended patches for the
        current quarter.

        Args:
            target_dir (str): The target directory where patches are
            downloaded. Defaults to ".".
            ignored_releases (list): A list containing regexes of versions to
            be ignored for downloads.
            ignored_description_words (list): A list containing regexes of
            words to be matched for descriptions of patches that must not be
            downloaded.
            progress_function (function): a function that will be called with
            the following parameters:
                - (str): file name
                - (int): file size in bytes
                - (int): total downloaded in bytes
            Defaults to None.

        Returns:
            int: Total downloaded in bytes
        """
        desc_file_path_counter = collections.Counter()
        total_downloaded_bytes = 0
        for (
            reco_patch_comp_id,
            reco_patch_plat,
        ) in self.__recommended_db_patches:
            normalized_plat_dir_name = self.__normalize_directory_name(
                self.__platforms[reco_patch_plat]
            )
            version = self.__db_release_components[reco_patch_comp_id][
                "version"
            ]
            if self.__is_expression_ignored(ignored_releases, version):
                continue

            patch_dest_path = (
                target_dir
                + os.path.sep
                + version
                + os.path.sep
                + normalized_plat_dir_name
            )
            pathlib.Path(patch_dest_path).mkdir(parents=True, exist_ok=True)
            desc_file_path = patch_dest_path + os.path.sep + _DESC_FILE_NAME

            desc_file_open_mode = "at"

            with open(
                desc_file_path, encoding="utf-8", mode=desc_file_open_mode
            ) as desc_file:
                for patch_uid in self.__recommended_db_patches[
                    (reco_patch_comp_id, reco_patch_plat)
                ]:
                    if self.__is_expression_ignored(
                        ignored_description_words,
                        self.__all_db_patches[patch_uid].description,
                    ):
                        continue
                    patch = self.__all_db_patches[patch_uid]
                    if patch.access_level.upper() == "PASSWORD PROTECTED":
                        error_str = (
                            f'Patch "{patch.number} - {patch.description}"'
                            " is password-protected. Download it manually"
                            " if you need it."
                        )
                        logging.error(error_str)
                        continue

                    if dry_run_mode:
                        logging.info(patch.description)

                    for file in patch.files:
                        print(
                            f"{file.name} - {patch.description}",
                            file=desc_file,
                        )
                        total_downloaded_bytes += int(file.size)
                        try:
                            self.__download_link(
                                file.download_url,
                                file.sha256sum,
                                patch_dest_path,
                                progress_function,
                                dry_run_mode,
                            )
                        except ChecksumMismatch:
                            error_str = (
                                f"{file.name}"
                                " checksum does not match Oracle's checksum. "
                                "Please remove it manually and download it "
                                "again."
                            )
                            logging.error(error_str)

                desc_file_path_counter[desc_file_path] += 1

        self.__remove_duplicate_lines_desc_files(target_dir)

        return total_downloaded_bytes

    @staticmethod
    def __remove_duplicate_lines_desc_files(target_dir):
        """Removes duplicate lines from description.txt files.

        Args:
            target_dir (str): target_dir (str): The target directory where
            patches are downloaded.
        """
        desc_file_list = pathlib.Path(target_dir).glob(f"**/{_DESC_FILE_NAME}")
        for desc_file in desc_file_list:
            with open(desc_file, "r+t", encoding="utf-8") as desc_file_handler:
                desc_lines_set = sorted(set(desc_file_handler.readlines()))
                desc_file_handler.seek(os.SEEK_SET)
                desc_file_handler.truncate(0)
                desc_file_handler.writelines(desc_lines_set)

    @staticmethod
    def __is_expression_ignored(ignored_expressions, expression) -> bool:
        """Checks if a word is on the list of ignored.

        Args:
            ignored_expressions (list): List of ignored expressions.
            expression (str): expression to be tested.

        Returns:
            bool: True if the expression is ignored.
        """
        for ignored_release_regex in ignored_expressions:
            match = re.search(ignored_release_regex, expression)
            if match is not None:
                return True

        return False

    def initialize_downloader(
        self, platform_names, target_dir, username, password
    ):
        """Initializes the downloader.

        Performs the logon to Oracle Support and downloads the catalog files.

        Args:
            platform_names (_type_): A list of platform names as defined by
                Oracle.
            target_dir (str): The target directory where patches are downloaded
                Defaults to ".".
            username (str): Oracle Support Username
            password (str): Oracle Support Password

        Raises:
            OracleSupportError: when not able to log on to Oracle Support
        """

        self.username = username
        self.password = password

        if self.__cookie_jar is None:
            logging.debug("Starting Oracle Support logon")
            ret = self.__logon_oracle_support()
            if not ret:
                logging.debug("Successfully logged on to Oracle Support")
            else:
                raise OracleSupportError("Status code 401")

        pathlib.Path(target_dir).mkdir(parents=True, exist_ok=True)

        self.__download_em_catalog(target_dir)

        em_catalog_dir = target_dir + os.path.sep + "em_catalog"

        if self.__platforms is None:
            self.__build_dict_platform_codes(
                platform_names,
                em_catalog_dir + os.path.sep + "aru_platforms.xml",
            )

        if not self.__db_release_components:
            self.__build_dict_database_release_components(
                em_catalog_dir + os.path.sep + "components.xml"
            )

        if not self.__recommended_db_patches:
            logging.debug("Process patch_recommendations.xml - Beginning")
            self.__process_patch_recommendations_file(
                em_catalog_dir + os.path.sep + "patch_recommendations.xml"
            )
            logging.debug("Process patch_recommendations.xml - Ended")

    @staticmethod
    def cleanup_downloader_resources(target_dir):
        """Cleans up the em_catalog files.

        Args:
            target_dir (str): The target directory where patches are downloaded
                Defaults to ".".
        """
        catalog_file_path = target_dir + os.path.sep + "em_catalog.zip"
        catalog_directory_path = target_dir + os.path.sep + "em_catalog"

        shutil.rmtree(catalog_directory_path, ignore_errors=True)
        catalog_file = pathlib.Path(catalog_file_path)
        try:
            catalog_file.unlink()
        except FileNotFoundError:
            pass

    def __logon_oracle_support(
        self,
    ):
        """Fills a cookie jar with logon information to Oracle Support

        Oracle Support login does not work with using requests.Session. It also
        does not work with allow_redirects=True, so we have to treat each
        redirect manually while also updating the cookie_jar.

        Setting the headers to Wget/X.X.X is also mandatory, as it's the only
        way to authenticate without JavaScript support.

        """

        login_response = requests.get(
            "https://updates.oracle.com/Orion/Services/download",
            auth=(self.username, self.password),
            allow_redirects=False,
            headers=_HEADERS,
            timeout=_REQUEST_TIMEOUT,
        )
        self.__cookie_jar = login_response.cookies

        status_code = login_response.status_code
        while True:
            if status_code == HTTPStatus.UNAUTHORIZED:
                self.__cookie_jar = None
                break

            if (
                status_code == HTTPStatus.FOUND
                or status_code == HTTPStatus.TEMPORARY_REDIRECT
            ):
                location = login_response.headers["Location"]
                if location.startswith("/"):
                    new_url = "https://updates.oracle.com" + location
                else:
                    new_url = location
                login_response = requests.get(
                    new_url,
                    auth=(self.username, self.password),
                    allow_redirects=False,
                    headers=_HEADERS,
                    cookies=self.__cookie_jar,
                    timeout=_REQUEST_TIMEOUT,
                )
                self.__cookie_jar.update(login_response.cookies)
                status_code = login_response.status_code

            if status_code == HTTPStatus.OK:
                self.__cookie_jar.update(login_response.cookies)
                break

        if login_response.status_code == HTTPStatus.UNAUTHORIZED:
            return 1

        return 0

    def __build_dict_platform_codes(
        self, platforms_names, platform_codes_file_path
    ):
        """Returns a dictionary of Oracle platforms codes
        and names, filtered by the input platform names.

        Args:
            platforms_names (list): List of platforms names as defined by
            Oracle.
            platform_codes_file_path (str): Complete path of the
            aru_platforms.xml file.

        Returns:
            dict: A dictionary of platform codes and names.
        """

        aru_platforms_doc = xml.etree.ElementTree.parse(
            platform_codes_file_path
        )
        aru_platforms_doc_root = aru_platforms_doc.getroot()

        self.__platforms = {
            tag.get("id"): tag.text.strip()
            for tag in aru_platforms_doc_root.iterfind("./platform")
            if tag.text.strip() in platforms_names
        }

    def __build_list_download_links(self, patch_number):
        """Returns a list containing download links for a given patch number
        and a list of platforms.

        Args:
            cookie_jar (requests.RequestsCookieJar): a cookie jar containing
                Oracle Support connection information
            patch_number (str): Oracle Patch number
            list_platforms_codes (list): List of platforms codes as defined by
                                        Oracle

        Returns:
            list: A list of links to be downloaded
        """

        self.__download_links = []

        for platform in self.__platforms:
            resp = requests.get(
                "https://updates.oracle.com/Orion/SimpleSearch/process_form",
                params={
                    "search_type": "patch",
                    "patch_number": patch_number,
                    "plat_lang": platform + "P",
                },
                headers=_HEADERS,
                cookies=self.__cookie_jar,
                timeout=_REQUEST_TIMEOUT,
            )
            resp_soup = BeautifulSoup(resp.text, _DEFAULT_HTML_PARSER)
            links = resp_soup.find_all(
                "a", attrs={"href": re.compile(r"\.zip")}
            )
            for link in links:
                self.__download_links.append(link["href"])

    def __download_link(
        self,
        url,
        oracle_file_checksum,
        target_dir,
        progress_function,
        dry_run_mode=True,
    ):
        """Downloads to the target_dir the file specified by the url.

        Args:
            url (str): the link to be downloaded
            oracle_file_checksum: SHA-256 checksum obtained from the download
                source
            cookie_jar (requests.RequestsCookieJar): a cookie jar containing
                Oracle Support connection information
            target_dir (str): The target directory where patches are downloaded
            progress_function (function): a function that will be called with
                the following parameters:
                    - (str): file name
                    - (int): file size in bytes
                    - (int): total downloaded in bytes
            dry_run_mode: Returns the amount downloaded in bytes without
            actually downloading the files. Defaults to True.

        Returns:
            int: Total downloaded in bytes
        """
        file_name = self.__extract_file_name_from_url(url)

        resp_dl = requests.get(
            url,
            cookies=self.__cookie_jar,
            headers=_HEADERS,
            stream=True,
            timeout=_REQUEST_TIMEOUT,
        )
        file_size = resp_dl.headers.get("content-length")

        if file_size is None:
            file_size = 0
        else:
            file_size = int(file_size)

        if dry_run_mode:
            logging.info(file_name)
            return file_size

        if self.__check_file_exists(target_dir, file_name, file_size):
            progress_function(file_name, file_size, file_size)
        else:
            total_dl = 0
            with open(
                target_dir + os.path.sep + file_name,
                "wb",
            ) as dl_file:
                for chunk in resp_dl.iter_content(_CHUNK_SIZE):
                    total_dl += len(chunk)
                    dl_file.write(chunk)
                    if file_size and progress_function:
                        progress_function(file_name, file_size, total_dl)

        downloaded_file_checksum = self.__calculate_file_checksum(
            target_dir, file_name
        )

        if (
            oracle_file_checksum
            and oracle_file_checksum != downloaded_file_checksum
        ):
            raise ChecksumMismatch

        return file_size

    @staticmethod
    def __extract_file_name_from_url(url) -> str:
        """Extracts the file name from url.

        Args:
            url (str): the link to be downloaded

        Returns:
            str: the file name as defined on the URL
        """

        file_name = re.sub(
            r"https://[^.]+\.oracle\.com/([A-Za-z0-9-_]+/){0,}", "", url
        )
        file_name = re.sub("[?].+$", "", file_name)

        return file_name

    @staticmethod
    def __check_file_exists(target_dir, file_name, file_size) -> bool:
        """Check if a file exists and has the correct size.

        Args:
            target_dir (str): The target directory where patches are downloaded
            file_name (str): Name of the file being downloaded.
            file_size (_type_): Size in bytes of the original file.
        """
        target_file = pathlib.Path(target_dir + os.path.sep + file_name)
        if target_file.is_file():
            if target_file.stat().st_size == file_size:
                return True
            else:
                return False
        else:
            return False

    def __obtain_sha256_checksum_oracle(self, url) -> str:
        """Obtains the SHA-256 checksum from Oracle for a patch file.

        Args:
            url (str): the link to be downloaded

        Returns:
            str: SHA-256 for the file on Oracle Support
        """
        checksum = ""
        aru_matches = re.search("[?]aru=[0-9]+", url)
        if aru_matches:
            aru = aru_matches.group(0).split("=")[1]
            resp_chksum = requests.get(
                "https://updates.oracle.com/Orion/ViewDigest/get_form",
                params={"aru": aru},
                cookies=self.__cookie_jar,
                headers=_HEADERS,
                timeout=_REQUEST_TIMEOUT,
            )
            if resp_chksum.text:
                sha256_matches = re.search(
                    r"\b[A-Fa-f0-9]{64}\b", resp_chksum.text
                )
                if sha256_matches:
                    checksum = sha256_matches.group(0)

        return checksum.upper()

    @staticmethod
    def __calculate_file_checksum(target_dir, file_name) -> str:
        """Calculates the SHA-256 checksum of the downloaded file.

        Args:
            target_dir (str): The target directory where patches are downloaded
            file_name (str): patch file name

        Returns:
            str: SHA-256 checksum of the downloaded file
        """
        hash_chunk_size = 128 * 1024
        with open(target_dir + os.path.sep + file_name, "rb") as checked_file:
            file_hash = hashlib.sha256()
            file_chunk = checked_file.read(hash_chunk_size)
            while file_chunk:
                file_hash.update(file_chunk)
                file_chunk = checked_file.read(hash_chunk_size)

        if file_hash:
            return file_hash.hexdigest().upper()
        else:
            return ""

    def __download_em_catalog(self, target_dir):
        """Downloads em_catalog.zip from Oracle Support.

        This zipped file contains xml files with the latest patches and
        platform codes.

        The zipped file will be extracted to a subdirectory of target_dir named
        em_catalog.

        Args:
            target_dir (str): The target directory where patches are
            downloaded.
        """
        local_file_path = target_dir + os.path.sep + "em_catalog.zip"
        local_directory_path = target_dir + os.path.sep + "em_catalog"

        if not pathlib.Path(local_file_path).is_file():
            self.__download_link(
                "https://updates.oracle.com/download/em_catalog.zip",
                None,
                target_dir,
                None,
                dry_run_mode=False,
            )

        pathlib.Path(target_dir + os.path.sep + "em_catalog").mkdir(
            parents=True, exist_ok=True
        )
        logging.debug("Extract em_catalog.zip - Beginning")
        with zipfile.ZipFile(local_file_path, "r") as cat_zip_file:
            cat_zip_file.extractall(local_directory_path)
        logging.debug("Extract em_catalog.zip - Ended")

    def __build_dict_database_release_components(self, components_file_path):
        """Builds a dict of all database release components from the
        em_catalog/components.xml file.

        Also builds a dict of all database related components from the
        em_catalog/components.xml file.

        Format:
            db_releases = {
                "cid": component.get("cid"),
                {"version": component.find("version").text,
                 "name": component.find("name").text
                 "eol_extended": eol_extended,
                 "eol_premium": eol_premium}
            }

        Args:
            components_file_path (str): Complete path of components.xml file.
        """
        components_doc = xml.etree.ElementTree.parse(components_file_path)

        components_root = components_doc.getroot()

        self.__db_release_components = {}
        for component in components_root.iterfind(
            "./components/ctype[@name='RELEASE']/component"
        ):
            component_name = component.find("name").text
            if component_name in [
                "Oracle Database",
                "RAC One Node",
                "Oracle Clusterware",
            ]:
                lifecycle_tag = component.find("lifecycle")
                eol_extended = None
                eol_premium = None
                if lifecycle_tag:
                    eol_extended_tag = lifecycle_tag.find(
                        "./date[@type='eol_extended']"
                    )
                    if eol_extended_tag is not None:
                        eol_extended = datetime.datetime.strptime(
                            eol_extended_tag.text, r"%Y-%m-%d"
                        )

                    eol_premium_tag = lifecycle_tag.find(
                        "./date[@type='eol_premium']"
                    )
                    if eol_premium_tag is not None:
                        eol_premium = datetime.datetime.strptime(
                            eol_premium_tag.text, r"%Y-%m-%d"
                        )

                self.__db_release_components[component.get("cid")] = {
                    "version": component.find("version").text,
                    "name": component_name,
                    "eol_extended": eol_extended,
                    "eol_premium": eol_premium,
                }

    def __process_patch_recommendations_file(self, recommendations_file_path):
        """Processes the patch_recommendations.xml file.

        Args:
            recommendations_file_path (str): Complete path of
            patch_recommendations.xml file.
        """

        path_counter = collections.Counter()

        self.__all_db_patches = {}

        # format - {(cid, platform): {patch_1, patch_2, ..., patch_n},}
        self.__recommended_db_patches = {}
        for evt, elem in xml.etree.ElementTree.iterparse(
            recommendations_file_path, events=("start", "end")
        ):
            self.__process_patches_tag(path_counter, evt, elem)

            self.__process_standalone_recommendations_tag(
                path_counter, self.__recommended_db_patches, evt, elem
            )

            self.__process_components_recommendations_tag(
                path_counter, self.__recommended_db_patches, evt, elem
            )

    def __process_patches_tag(self, path_counter, evt, elem):
        """Processes the "patches" tags for the patch_recommendations.xml file.

        Args:
            elem (ElementTag): an ElementTag with tag == patch.
            path_counter (Counter): a counter collection to keep track of the
            parent section.
        """
        if evt == "start" and elem.tag == "patches":
            path_counter["patches"] += 1

        if evt == "start" and elem.tag == "fixed_bugs":
            elem.clear()

        if (
            evt == "end"
            and path_counter["patches"] > 0
            and elem.tag == "patch"
        ):
            access_level_tag = elem.find("access")
            if access_level_tag is not None:
                access_level = access_level_tag.text
            platform_id = elem.find("platform").get("id")
            if platform_id in self.__platforms:
                patch_files = []
                for file in elem.iterfind("./files/file"):
                    download_url_tag = file.find("download_url")
                    patch_files.append(
                        OraclePatchFile(
                            download_url_tag.get("host")
                            + download_url_tag.text,
                            sha256sum=file.find(
                                "./digest[@type='SHA-256']"
                            ).text,
                            name=file.find("name").text,
                            size=file.find("size").text,
                        )
                    )

                self.__all_db_patches[elem.get("uid")] = OraclePatch(
                    uid=elem.get("uid"),
                    number=elem.find("name").text,
                    description=elem.find("bug").find("abstract").text,
                    platform_code=platform_id,
                    release_name=elem.find("release").get("name"),
                    access_level=access_level,
                    files=patch_files,
                )

            elem.clear()

        if evt == "end" and elem.tag == "patches":
            path_counter["patches"] -= 1
            elem.clear()

    def __process_standalone_recommendations_tag(
        self, path_counter, recommended_patches, evt, elem
    ):
        """Processes the "standalone_recommendations" tags for the
        patch_recommendations.xml file.

        Args:
            path_counter (Counter): a counter collection to keep track of the
            parent section.
            recommended_patches (set): an existing set of recommended patches
            that will receive the recommendations for the standalone section.
            evt (str): which event is being processed at the moment.
            elem (ElementTag): an ElementTag with tag == patch.
        """
        if evt == "start" and elem.tag == "standalone_recommendations":
            path_counter["standalone_recommendations"] += 1

        if (
            evt == "end"
            and path_counter["standalone_recommendations"] > 0
            and elem.tag == "release"
        ):
            if elem.get("cid") in self.__db_release_components:
                component_id = elem.get("cid")
                for platform in elem:
                    platform_id = platform.get("id")
                    if platform_id in self.__platforms:
                        if (
                            component_id,
                            platform_id,
                        ) not in recommended_patches:
                            recommended_patches[
                                (component_id, platform_id)
                            ] = set()
                        for patch in platform:
                            recommended_patches[
                                (component_id, platform_id)
                            ].add(patch.get("uid"))
            elem.clear()

        if evt == "end" and elem.tag == "standalone_recommendations":
            path_counter["standalone_recommendations"] -= 1
            elem.clear()

    def __process_components_recommendations_tag(
        self, path_counter, recommended_patches, evt, elem
    ):
        """Processes the "components_recommendations" tags for the
        patch_recommendations.xml file.

        Args:
            path_counter (Counter): a counter collection to keep track of the
            parent section.
            recommended_patches (set): an existing set of recommended patches
            that will receive the recommendations for the standalone section.
            evt (str): which event is being processed at the moment.
            elem (ElementTag): an ElementTag with tag == patch.
        """
        if evt == "start" and elem.tag == "components_recommendations":
            path_counter["components_recommendations"] += 1

        if (
            evt == "end"
            and path_counter["components_recommendations"] > 0
            and elem.tag == "release"
        ):
            if elem.get("cid") in self.__db_release_components:
                component_id = elem.get("cid")
                for platform in elem:
                    platform_id = platform.get("id")
                    if platform_id in self.__platforms:
                        if (
                            component_id,
                            platform_id,
                        ) not in recommended_patches:
                            recommended_patches[
                                (component_id, platform_id)
                            ] = set()
                        for patch in platform:
                            recommended_patches[
                                (component_id, platform_id)
                            ].add(patch.get("uid"))
            elem.clear()

        if evt == "end" and elem.tag == "components_recommendations":
            path_counter["components_recommendations"] -= 1
            elem.clear()

    @staticmethod
    def __normalize_directory_name(orig_name) -> str:
        """Replaces undesirable characters from a planned directory name
        with underscore characters.

        Args:
            orig_name (str): The original directory name.

        Returns:
            str: the normalized name.
        """
        normalized_name = re.sub("[^a-zA-Z0-9_.-]+", "_", orig_name)
        normalized_name = re.sub("_$", "", normalized_name)
        normalized_name = re.sub("^_", "", normalized_name)

        return normalized_name


class OraclePatch:
    """Structure grouping attributes of an Oracle Patch."""

    uid = None
    number = None
    platform_code = None
    release_name = None
    description = None
    access_level = None
    files = None

    def __init__(
        self,
        uid,
        number,
        platform_code,
        release_name,
        description,
        access_level,
        files,
    ):
        self.uid = uid
        self.number = number
        self.platform_code = platform_code
        self.release_name = release_name
        self.description = description
        self.access_level = access_level
        self.files = files

    def __str__(self):
        return str(self.__dict__)

    def __repr__(self):
        repr_str = (
            f'OraclePatch("{self.uid}", "{self.number}", '
            f'"{self.platform_code}", "{self.release_name}", '
            f'"{self.description}", "{self.access_level}", "{self.files}")'
        )
        return repr_str

    def __eq__(self, other):
        return self.uid == other.uid

    def __lt__(self, other):
        return self.uid < other.uid


class OraclePatchFile:
    """Structure grouping attributes of an Oracle Patch file."""

    download_url = None
    sha256sum = None
    name = None
    size = None

    def __init__(self, download_url, sha256sum, name, size):
        self.download_url = download_url
        self.sha256sum = sha256sum
        self.name = name
        self.size = size

    def __str__(self):
        return str(self.__dict__)

    def __repr__(self):
        repr_str = (
            f'OraclePatchFile("{self.download_url}",'
            f'"{self.sha256sum}", "{self.name}", "{self.size})'
        )
        return repr_str


class ChecksumMismatch(Exception):
    """Raised when the downloaded file checksum does not match Oracle's."""

class OracleSupportError(Exception):
    """Raised when not able to log on to Oracle Support."""
