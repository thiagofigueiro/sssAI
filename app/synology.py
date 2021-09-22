import os
import logging
import pickle
import requests
import tempfile

from urllib.parse import urljoin

LOGIN_PATH_TEMPLATE = '/webapi/auth.cgi?api=SYNO.API.Auth&method=Login&version=1&account={username}&passwd={password}&session=SurveillanceStation'
SNAPSHOT_PATH_TEMPLATE = '/webapi/entry.cgi?camStm=1&version=2&cameraId={camera_id}&api=%22SYNO.SurveillanceStation.Camera%22&method=GetSnapshot'
COOKIE_FILEPATH = 'cookie'

logger = logging.getLogger(__name__)  # app.synology


def save_cookies(requests_cookiejar, filename):
    with open(filename, 'wb') as f:
        pickle.dump(requests_cookiejar, f)


def load_cookies(filename):
    with open(filename, 'rb') as f:
        return pickle.load(f)


class Snapshot:
    def __init__(self, content):
        self.temp_file = self._save(content)
        self.file_name = self.temp_file.name

    def __del__(self):
        logger.debug(f'Deleting temporary snapshot {self.file_name}')
        try:
            os.unlink(self.file_name)
        except FileNotFoundError:
            pass

    @property
    def image_data(self):
        return open(self.file_name, 'rb').read()

    @staticmethod
    def _save(content):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            logger.debug(f'Wrote snapshot to {f.name}')
            return f


class SynologySession:
    def __init__(self, url, username, password, cookie_filepath=COOKIE_FILEPATH):
        self.url = url
        self.username = username
        self.password = password
        self.cookie_filepath = cookie_filepath
        self.login()

    def _request(self, url_path, **kwargs):
        url = urljoin(self.url, url_path)
        logger.debug(f'GET {url}')
        return requests.get(url, **kwargs)

    def login(self):
        url_path = LOGIN_PATH_TEMPLATE.format(username=self.username, password=self.password)
        try:
            r = self._request(url_path)
            save_cookies(r.cookies, self.cookie_filepath)
        except requests.exceptions.ConnectionError as e:
            logger.error(f'Login error: {e}')
            raise e from None

    def cookies(self):
        return load_cookies(self.cookie_filepath)

    def snapshot(self, camera_id):
        url_path = SNAPSHOT_PATH_TEMPLATE.format(camera_id=camera_id)
        err_msg = ''
        try:
            response = self._request(url_path, cookies=self.cookies())
            if response.status_code == 200:
                return Snapshot(response.content)
            err_msg = f'{response.status_code} {response.content}'
        except requests.exceptions.ConnectionError as e:
            err_msg += str(e)

        logger.error(f'Could not get snapshot: {err_msg}')
