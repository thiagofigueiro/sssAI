from fastapi import FastAPI
from PIL import Image, ImageDraw

import datetime
import pathlib
import requests
import logging
import json
import pickle
import time
import os
from urllib.parse import urljoin

from .config import Config
from .synology import SynologySession

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%dT%H:%M:%S%z')
LOG_LEVEL = logging.getLevelName(os.environ.get("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger('app')  # need the root logger for the whole app, not just 'app.main'
logger.setLevel(LOG_LEVEL)

logger.info(f'App Started logger: {logger.name}')
app = FastAPI()
config = Config()

sss_url = config.settings["sss_url"]
homebridge_webhook_url = config.settings["homebridge_webhook_url"]
username = config.settings["username"]
password = config.settings["password"]
detection_labels = config.settings['detection_labels']
timeout = config.settings['timeout']
min_sizex = config.settings['min_sizex']
min_sizey = config.settings['min_sizey']
min_confidence = config.settings['min_confidence']
capture_path = pathlib.Path(config.settings['capture_dir'])
logger.debug(f'Capture path is {capture_path}')

logger.info(f"Synology login to {config.settings['sss_url']}")
synology_session = SynologySession(config.settings['sss_url'], username, password)

# Dictionary to save last trigger times for camera to stop flooding the capability
last_trigger_fn = "/tmp/last.dict"


def save_last_trigger(last_trigger):
    with open(last_trigger_fn, 'wb') as f:
        pickle.dump(last_trigger, f)


def load_last_trigger():
    if os.path.exists(last_trigger_fn):
        with open(last_trigger_fn, 'rb') as f:
            return pickle.load(f)
    else:
        return {}


def contains(rOutside, rInside):
    return rOutside["x_min"] < rInside["x_min"] < rInside["x_max"] < rOutside["x_max"] and \
        rOutside["y_min"] < rInside["y_min"] < rInside["y_max"] < rOutside["y_max"]


# If you would like to ignore objects outside the ignore area instead of inside, set this to
# contains(rect, ignore_area):
def isIgnored(rect, ignore_areas):
    for ignore_area in ignore_areas:
        if contains(ignore_area, rect):
            logger.info('Object in ignore area, not triggering')
            return True
    return False


def deepstack_detection(image):
    deepstack_url = urljoin(config.settings['deepstack_url'], '/v1/vision/detection')
    try:
        s = time.perf_counter()
        response = requests.post(f"{deepstack_url}", files={"image": image}, timeout=timeout).json()
        e = time.perf_counter()
        logger.debug(f'Deepstack result: {json.dumps(response, indent=2)}. Time: {e - s}s')
    except (json.decoder.JSONDecodeError, requests.exceptions.ConnectionError) as e:
        logger.error(e)
        return None

    return response['predictions']


# TODO: move to Config
def ignore_areas(camera_id):
    areas = []
    for area in config.camera[camera_id].get('ignore_areas', []):
        areas.append({
            "y_min": int(area["y_min"]),
            "x_min": int(area["x_min"]),
            "y_max": int(area["y_max"]),
            "x_max": int(area["x_max"])
        })
    return areas


def should_save(predictions, camera_id, last_trigger):
    homekit_acc_id = config.camera[camera_id].get("homekit_acc_id")

    start = time.time()
    found = False
    for prediction in predictions:
        confidence = round(100 * prediction["confidence"])
        label = prediction["label"]
        sizex = int(prediction["x_max"])-int(prediction["x_min"])
        sizey = int(prediction["y_max"])-int(prediction["y_min"])
        logger.debug(f"  {label} ({confidence}%)   {sizex}x{sizey}")

        if not found and label in detection_labels and \
           sizex > min_sizex and \
           sizey > min_sizey and \
           confidence > min_confidence and \
           not isIgnored(prediction, ignore_areas(camera_id)):
            end = time.time()
            runtime = round(end - start, 1)

            logger.info(f"Found {label} in camera {camera_id} ({confidence}% confidence, took {runtime}s)")
            requests.request("GET", config.camera[camera_id]["trigger_url"])

            found = True
            last_trigger[camera_id] = time.time()
            save_last_trigger(last_trigger)
            logger.debug(f"Saving last camera time for {camera_id} as {last_trigger[camera_id]}")

            if homebridge_webhook_url is not None and homekit_acc_id is not None:
                hb = requests.get(f"{homebridge_webhook_url}/?accessoryId={homekit_acc_id}&state=true")
                logger.debug(f"Sent message to homebridge webhook: {hb.status_code}")
            else:
                logger.debug(f"Skipping HomeBridge Webhook since no webhookUrl or accessory Id")

    return found


@app.get("/{camera_id}")
async def read_item(camera_id):
    start = time.time()
    try:
        cameraname = config.camera[camera_id]["name"]
    except KeyError:
        return f'Configuration for camera {camera_id} not found'
    last_trigger = load_last_trigger()

    # Check we are outside the trigger interval for this camera
    if camera_id in last_trigger:
        t = last_trigger[camera_id]
        logger.info(f"Found last camera time for {camera_id} was {t}")
        if (start - t) < config.settings['trigger_interval']:
            msg = f"Skipping detection on camera {camera_id} since it was only triggered {start - t}s ago"
            logger.info(msg)
            return (msg)
        else:
            logger.info(f"Processing event on camera (last trigger was {start-t}s ago)")
    else:
        logger.info(f"No last camera time for {camera_id}")

    snapshot = synology_session.snapshot(camera_id)
    logger.info('Requesting detection from DeepStack...')
    predictions = deepstack_detection(snapshot.image_data)
    if not predictions:
        return 'Error calling Deepstack'

    found = should_save(predictions, camera_id, last_trigger)

    end = time.time()
    runtime = round(end - start, 1)
    if found:
        save_image(predictions, cameraname, snapshot.file_name, camera_id)
        result = f"triggering {cameraname} because something was found - took {runtime} seconds"
    else:
        result = f"{cameraname} triggered - nothing found - took {runtime} seconds"

    logger.info(result)
    return result


def draw_predictions(predictions, draw):
    for prediction in predictions:
        confidence = round(100 * prediction["confidence"])
        label = f"{prediction['label']} ({confidence}%)"
        draw.rectangle((prediction["x_min"], prediction["y_min"], prediction["x_max"],
                        prediction["y_max"]), outline=(255, 230, 66), width=2)
        draw.text((prediction["x_min"]+10, prediction["y_min"]+10),
                  f"{label}", fill=(255, 230, 66))
    pass


def draw_ignore_areas(areas, draw):
    for coord in areas:
        draw.rectangle((coord["x_min"], coord["y_min"],
                        coord["x_max"], coord["y_max"]), outline=(255, 66, 66), width=2)
        draw.text((coord["x_min"]+10, coord["y_min"]+10), f"ignore", fill=(255, 66, 66))


def capture_image_path(camera_name, camera_id):
    # TODO use timestamp from Synology
    time_format = '%Y-%m-%dT%H:%M:%S'
    time_now = datetime.datetime.now().strftime(time_format)
    file_path = capture_path.joinpath(
        f'{time_now}-camera-{camera_id}-{camera_name}').with_suffix('.jpg')
    file_path.parent.mkdir(parents=True, exist_ok=True)
    return file_path


def save_image(predictions, camera_name, source_path, camera_id):
    start = time.time()
    im = Image.open(source_path)
    draw = ImageDraw.Draw(im)

    draw_predictions(predictions, draw)
    draw_ignore_areas(ignore_areas(camera_id), draw)

    dest_path = capture_image_path(camera_name, camera_id)
    im.save(dest_path, quality=100)
    im.close()
    logger.info(f'Capture saved to {dest_path}')
    end = time.time()
    runtime = round(end - start, 1)
    logger.debug(f"Saved captured and annotated image: {dest_path} in {runtime} seconds.")
