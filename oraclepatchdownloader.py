"""Module to support downloading Oracle Patches

Author: Lucas Pimentel Lellis

Requires:
    - requests
    - beautifulsoup4
    - html5lib
"""

import os
import pathlib
import re
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

    def __init__(self, username, password):
        """Builds an Oracle Patch downloader.

        Creates an empty cookie jar to store logon information.

        Args:
            username (str): Oracle Support Username
            password (str): Oracle Support Password
        """
        self.__cookie_jar = None
        self.__platform_codes = None
        self.__download_links = None
        self.username = username
        self.password = password


    def download_oracle_patch(
        self,
        patch_number,
        platform_names,
        target_dir=".",
        progress_function=None,
    ):
        """Downloads an Oracle Patch given a patch number and a list of
        platforms, a target directory (optional) and a function to display
        download progress (optional).

        Args:
            patch_number (str): an Oracle patch number
            platform_names (_type_): A list of platform names as defined by
                Oracle.
            target_dir (str): The target directory to download the file.
                Defaults to ".".
            progress_function (function): a function that will be called with
                the following parameters:
                    - (str): file name
                    - (int): file size in bytes
                    - (int): total downloaded in bytes
                Defaults to None.
        """
        if self.__cookie_jar is None:
            self.__logon_oracle_support()

        if self.__platform_codes is None:
            self.__build_list_platform_codes(
                platform_names
            )

        pathlib.Path(target_dir).mkdir(parents=True, exist_ok=True)

        if self.__download_links:
            self.__download_links.clear()

        self.__build_list_download_links(
            patch_number
        )

        for dl_link in self.__download_links:
            self.__download_link(dl_link, target_dir, progress_function)

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

    def __build_list_platform_codes(self, platforms_names):
        """Returns a list containing download links for a given patch number
        and a list of platforms.

        Args:
            cookie_jar (requests.RequestsCookieJar): a cookie jar containing
                Oracle Support connection information
            platforms_names (list): List of platforms as defined by Oracle

        Returns:
            list: A list of platform codes
        """

        self.__platform_codes = []
        search_page_content = requests.get(
            "https://updates.oracle.com/Orion/SavedSearches/switch_to_simple",
            cookies=self.__cookie_jar,
            headers=_HEADERS,
            allow_redirects=True,
        )
        search_page_content_soup = BeautifulSoup(
            # We must use html5lib as Oracle's HTML is broken
            # due to the lack of </option> closing tags
            search_page_content.text,
            _DEFAULT_HTML_PARSER,
        )

        plat_options_soup = search_page_content_soup.find(
            "select", attrs={"name": "plat_lang"}
        )
        self.__platform_codes = [
            tag["value"]
            for tag in plat_options_soup.children
            if tag.text.strip() in platforms_names
        ]

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

        for plat_code in self.__platform_codes:
            resp = requests.get(
                "https://updates.oracle.com/Orion/SimpleSearch/process_form",
                params={
                    "search_type": "patch",
                    "patch_number": patch_number,
                    "plat_lang": plat_code,
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

    def __download_link(self, url, target_dir, progress_function):
        """Downloads to the target_dir the file specified by the url.

        Args:
            url (str): the link to be downloaded
            cookie_jar (requests.RequestsCookieJar): a cookie jar containing
                Oracle Support connection information
            target_dir (str): The target directory to download the file.
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

    def __extract_file_name_from_url(self, url):
        """Extracts the file name from url.

        Args:
            url (str): the link to be downloaded

        Returns:
            str: the file name as defined on the URL
        """

        file_name = url.replace(
            "https://updates.oracle.com/Orion/Download/process_form/", ""
        )
        file_name = re.sub("[?].+$", "", file_name)

        return file_name
