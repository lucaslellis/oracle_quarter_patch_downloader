"""Module to support downloading Oracle Patches

Author: Lucas Pimentel Lellis

Requires:
    - requests
    - beautifulsoup4
    - html5lib

"""

import collections
import datetime
import hashlib
import os
import pathlib
import re
import sys
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


class OraclePatchDownloader:
    """Class that enables downloading Oracle patches

    Author: Lucas Pimentel Lellis
    """

    def __init__(self):
        """Builds an Oracle Patch downloader.

        Creates an empty cookie jar to store logon information.
        """
        self.__cookie_jar = None
        self.__platforms = None
        self.__download_links = None
        self.__db_release_components = None
        self.__all_db_patches = None
        self.username = None
        self.password = None

    def download_oracle_patch(
        self,
        patch_number,
        target_dir=".",
        progress_function=None,
    ):
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
        """
        if not self.__cookie_jar:
            print("Please call initialize_downloader() first", file=sys.stderr)
            return

        if self.__download_links:
            self.__download_links.clear()

        self.__build_list_download_links(patch_number)

        pathlib.Path(target_dir).mkdir(parents=True, exist_ok=True)

        for dl_link in self.__download_links:
            try:
                oracle_checksum = self.__obtain_sha256_checksum_oracle(dl_link)
                self.__download_link(
                    dl_link, oracle_checksum, target_dir, progress_function
                )
            except ChecksumMismatch:
                local_filename = (
                    target_dir
                    + os.path.sep
                    + self.__extract_file_name_from_url(dl_link)
                )
                print(
                    f"{local_filename}"
                    " checksum does not match Oracle's checksum. "
                    "Please remove it manually and download it again.",
                    file=sys.stderr,
                )

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
        """
        self.username = username
        self.password = password

        if self.__cookie_jar is None:
            self.__logon_oracle_support()

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

        self.__process_patch_recommendations_file(
            em_catalog_dir + os.path.sep + "patch_recommendations.xml"
        )

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
                )
                self.__cookie_jar.update(login_response.cookies)
                status_code = login_response.status_code

            if status_code == HTTPStatus.OK:
                self.__cookie_jar.update(login_response.cookies)
                break

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
            )
            resp_soup = BeautifulSoup(resp.text, _DEFAULT_HTML_PARSER)
            links = resp_soup.find_all(
                "a", attrs={"href": re.compile(r"\.zip")}
            )
            for link in links:
                self.__download_links.append(link["href"])

    def __download_link(
        self, url, oracle_file_checksum, target_dir, progress_function
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
        """
        file_name = self.__extract_file_name_from_url(url)

        resp_dl = requests.get(
            url, cookies=self.__cookie_jar, headers=_HEADERS, stream=True
        )
        file_size = resp_dl.headers.get("content-length")
        if file_size is None:
            file_size = 0
        else:
            file_size = int(file_size)

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
            target_dir (str): _description_
            file_name (str): _description_

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
            )

        pathlib.Path(target_dir + os.path.sep + "em_catalog").mkdir(
            parents=True, exist_ok=True
        )
        with zipfile.ZipFile(local_file_path, "r") as cat_zip_file:
            cat_zip_file.extractall(local_directory_path)

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
        recommended_patches = {}
        for evt, elem in xml.etree.ElementTree.iterparse(
            recommendations_file_path, events=("start", "end")
        ):
            self.__process_patches_tag(path_counter, evt, elem)

            self.__process_standalone_recommendations_tag(
                path_counter, recommended_patches, evt, elem
            )

            self.__process_components_recommendations_tag(
                path_counter, recommended_patches, evt, elem
            )

        for reco_patch_key, reco_patch_plat in recommended_patches:
            print(
                self.__db_release_components[reco_patch_key]["name"]
                + "\t"
                + self.__db_release_components[reco_patch_key]["version"]
                + "\t"
                + self.__platforms[reco_patch_plat]
            )
            for patch_uid in recommended_patches[
                (reco_patch_key, reco_patch_plat)
            ]:
                try:
                    print("\t" + self.__all_db_patches[patch_uid].description)
                except KeyError:
                    print("Patch not found - " + patch_uid)

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
                        )
                    )

                self.__all_db_patches[elem.get("uid")] = OraclePatch(
                    uid=elem.get("uid"),
                    number=elem.find("name").text,
                    description=elem.find("bug").find("abstract").text,
                    platform_code=platform_id,
                    release_name=elem.find("release").get("name"),
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


class OraclePatch:
    """Structure grouping attributes of an Oracle Patch."""

    def __init__(
        self, uid, number, platform_code, release_name, description, files
    ):
        self.uid = uid
        self.number = number
        self.platform_code = platform_code
        self.release_name = release_name
        self.description = description
        self.files = files

    def __str__(self):
        return str(self.__dict__)

    def __repr__(self):
        repr_str = (
            f'OraclePatch("{self.uid}", "{self.number}", '
            f'"{self.platform_code}", "{self.release_name}", '
            f'"{self.description}", "{self.files}")'
        )
        return repr_str

    def __eq__(self, other):
        return self.uid == other.uid

    def __lt__(self, other):
        return self.uid < other.uid


class OraclePatchFile:
    """Structure grouping attributes of an Oracle Patch file."""

    def __init__(self, download_url, sha256sum, name):
        self.download_url = download_url
        self.sha256sum = sha256sum
        self.name = name

    def __str__(self):
        return str(self.__dict__)

    def __repr__(self):
        repr_str = (
            f'OraclePatchFile("{self.download_url}",'
            f'"{self.sha256sum}", "{self.name})'
        )
        return repr_str


class ChecksumMismatch(Exception):
    """Raised when the downloaded file checksum does not match Oracle's."""
