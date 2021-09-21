import pathlib
import pytest
from fastapi.testclient import TestClient

IMAGES_PATH = pathlib.Path('tests/fixtures/images')


@pytest.fixture(scope='session')
def config():
    from app.config import Config
    return Config()


@pytest.fixture
def test_image():
    def fixture(name):
        return open(IMAGES_PATH.joinpath(name).with_suffix('.jpg'), mode='rb').read()
    return fixture


# @pytest.fixture(scope='session')
@pytest.fixture(scope='function')
def client(httpserver):
    httpserver.expect_oneshot_request('/webapi/auth.cgi', method='GET').respond_with_data('OK')

    from app.main import app as fast_api_app

    httpserver.check_assertions()

    return TestClient(fast_api_app)


@pytest.fixture(scope="session")
def httpserver_listen_address():
    return '0.0.0.0', 8000
