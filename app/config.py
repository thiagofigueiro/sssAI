import json
import os

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

LEGACY_KEYS = {
    'captureDir': 'capture_dir',
    'deepstackUrl': 'deepstack_url',
    'homebridgeWebhookUrl': 'homebridge_webhook_url',
    'sssUrl': 'sss_url',
}


class Config:
    def __init__(self):
        self.camera = self._read_json(os.environ.get('CAMERAS_JSON', '/config/cameras.json'))
        self.settings = self._read_json(os.environ.get('SETTINGS_JSON', '/config/settings.json'))
        self.settings.update(DEFAULTS)
        self._apply_legacy_keys()

    def _apply_legacy_keys(self):
        for old_key, new_key in LEGACY_KEYS.items():
            if self.settings.get(new_key) is None:
                self.settings[new_key] = self.settings.get(old_key)

    @staticmethod
    def _read_json(file_path):
        with open(file_path) as fd:
            return json.load(fd)



