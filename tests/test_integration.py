import os
import pytest
from urllib.parse import urlparse


@pytest.mark.parametrize('image_name', ['people', 'cars'])
def test_request(image_name, client, httpserver, test_image, config):
    from app.main import last_trigger_fn as LAST_TRIGGER_FILE
    try:
        os.unlink(LAST_TRIGGER_FILE)
    except FileNotFoundError:
        pass

    camera_id = '2'
    cameraname = config.camera[camera_id]['name']
    x_trigger = urlparse(config.camera[camera_id]['trigger_url']).path

    httpserver.expect_request('/webapi/entry.cgi', method='GET').\
        respond_with_data(test_image(image_name), content_type='image/jpeg')
    httpserver.expect_request(x_trigger, method='GET').respond_with_data('OK')

    response = client.get(f'/{camera_id}')

    assert response.status_code == 200
    assert f'Camera {camera_id}: recording {cameraname}' in response.text
    httpserver.check_assertions()
