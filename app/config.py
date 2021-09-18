import json
import logging
import os
import pprint

logger = logging.getLogger(__name__)  # app.synology

# TODO: replace with objects (ie. parse URLs, paths etc)
DEFAULTS = {
    'capture_dir': '/capture_dir',
    'detection_labels': ['car', 'person'],
    'min_confidence': 0,
    'min_sizex': 0,
    'min_sizey': 0,
    'timeout': 10,
    # If no trigger interval set then make it 60s
    # (i.e. don't send another event from the triggered camera for at least 60s
    # to stop flooding event notifications
    'trigger_interval': 60,
}

# these mappings keep compatibility with the legacy settings keys
# there was a mix of camel-case and snake case; the new format uses snake case consistently
LEGACY_SETTINGS_MAP = {
    'captureDir': 'capture_dir',
    'deepstackUrl': 'deepstack_url',
    'homebridgeWebhookUrl': 'homebridge_webhook_url',
    'sssUrl': 'sss_url',
    'triggerInterval': 'trigger_interval',
}

LEGACY_CAMERAS_MAP = {
    'triggerUrl': 'trigger_url',
    'homekitAccId': 'homekit_acc_id',
}


class Config:
    def __init__(self):
        self.camera = self._read_json(os.environ.get('CAMERAS_JSON', '/config/cameras.json'))
        self.settings = DEFAULTS.copy()
        self.settings.update(
            self._read_json(os.environ.get('SETTINGS_JSON', '/config/settings.json')))
        self._apply_legacy_keys()
        logger.debug(f'Settings {pprint.pformat(self.settings, indent=2)}')
        logger.debug(f'Cameras {pprint.pformat(self.camera, indent=2)}')

    def _apply_legacy_keys(self):
        def _replace(target, mapping):
            for old_key, new_key in mapping.items():
                if target.get(new_key) is None:
                    target[new_key] = target.get(old_key)

        _replace(self.settings, LEGACY_SETTINGS_MAP)

        for camera in self.camera.values():
            _replace(camera, LEGACY_CAMERAS_MAP)

    @staticmethod
    def _read_json(file_path):
        with open(file_path) as fd:
            return json.load(fd)


