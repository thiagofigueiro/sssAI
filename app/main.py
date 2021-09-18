from fastapi import FastAPI
from PIL import Image, ImageDraw

import requests
import logging
import json
import pickle
import time
import os
from urllib.parse import urljoin

from .config import Config
from .synology import SynologySession

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
logging.info('App Started')
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

synology_session = SynologySession(config.settings['sss_url'], username, password)

# Dictionary to save last trigger times for camera to stop flooding the capability
last_trigger_fn = f"/tmp/last.dict"


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


# If you would like to ignore objects outside the ignore area instead of inside, set this to contains(rect, ignore_area):
def isIgnored(rect, ignore_areas):
    for ignore_area in ignore_areas:
        if contains(ignore_area, rect):
            logging.info('Object in ignore area, not triggering')
            return True
    return False


def deepstack_detection(image):
    deepstack_url = urljoin(config.settings['deepstack_url'], '/v1/vision/detection')
    try:
        s = time.perf_counter()
        response = requests.post(f"{deepstack_url}", files={"image": image}, timeout=timeout).json()
        e = time.perf_counter()
        logging.debug(f'Deepstack result: {json.dumps(response, indent=2)}. Time: {e - s}s')
    except (json.decoder.JSONDecodeError, requests.exceptions.ConnectionError) as e:
        logging.error(e)
        return None
    return response


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
        logging.info(f"Found last camera time for {camera_id} was {t}")
        if (start - t) < config.settings['trigger_interval']:
            msg = f"Skipping detection on camera {camera_id} since it was only triggered {start - t}s ago"
            logging.info(msg)
            return (msg)
        else:
            logging.info(f"Processing event on camera (last trigger was {start-t}s ago)")
    else:
        logging.info(f"No last camera time for {camera_id}")

    triggerurl = config.camera[camera_id]["trigger_url"]
    if "homekit_acc_id" in config.camera[camera_id]:
        homekit_acc_id = config.camera[camera_id]["homekit_acc_id"]

    ignore_areas = []
    if "ignore_areas" in config.camera[camera_id]:
        for ignore_area in config.camera[camera_id]["ignore_areas"]:
            ignore_areas.append({
                "y_min": int(ignore_area["y_min"]),
                "x_min": int(ignore_area["x_min"]),
                "y_max": int(ignore_area["y_max"]),
                "x_max": int(ignore_area["x_max"])
            })

    snapshot = synology_session.snapshot(camera_id)
    logging.info('Requesting detection from DeepStack...')
    response = deepstack_detection(snapshot.image_data)
    if not response:
        return 'Error calling Deepstack'

    labels = ''
    predictions = response["predictions"]
    for object in predictions:
        label = object["label"]
        if label != 'person':
            labels = labels + label + ' '

    i = 0
    found = False

    for prediction in response["predictions"]:
        confidence = round(100 * prediction["confidence"])
        label = prediction["label"]
        sizex = int(prediction["x_max"])-int(prediction["x_min"])
        sizey = int(prediction["y_max"])-int(prediction["y_min"])
        logging.debug(f"  {label} ({confidence}%)   {sizex}x{sizey}")

        if not found and label in detection_labels and \
           sizex > min_sizex and \
           sizey > min_sizey and \
           confidence > min_confidence and \
           not isIgnored(prediction, ignore_areas):

            requests.request("GET", triggerurl, data={})
            end = time.time()
            runtime = round(end - start, 1)
            logging.info(f"{confidence}% sure we found a {label} - triggering {cameraname} - took {runtime} seconds")

            found = True
            last_trigger[camera_id] = time.time()
            save_last_trigger(last_trigger)
            logging.debug(f"Saving last camera time for {camera_id} as {last_trigger[camera_id]}")

            if homebridge_webhook_url is not None and homekit_acc_id is not None:
                hb = requests.get(f"{homebridge_webhook_url}/?accessoryId={homekit_acc_id}&state=true")
                logging.debug(f"Sent message to homebridge webhook: {hb.status_code}")
            else:
                logging.debug(f"Skipping HomeBridge Webhook since no webhookUrl or accessory Id")
        i += 1

    end = time.time()
    runtime = round(end - start, 1)
    if found:
        save_image(predictions, cameraname, snapshot.file_name, ignore_areas)
        result = f"triggering {cameraname} because something was found - took {runtime} seconds"
    else:
        result = f"{cameraname} triggered - nothing found - took {runtime} seconds"

    logging.info(result)
    return result


def save_image(predictions, camera_name, file_handle, ignore_areas):
    start = time.time()
    logging.debug(f"Saving new image file....")
    im = Image.open(file_handle)

    draw = ImageDraw.Draw(im)

    for object in predictions:
        confidence = round(100 * object["confidence"])
        label = f"{object['label']} ({confidence}%)"
        draw.rectangle((object["x_min"], object["y_min"], object["x_max"],
                        object["y_max"]), outline=(255, 230, 66), width=2)
        draw.text((object["x_min"]+10, object["y_min"]+10),
                  f"{label}", fill=(255, 230, 66))

    for ignore_area in ignore_areas:
        draw.rectangle((ignore_area["x_min"], ignore_area["y_min"],
                        ignore_area["x_max"], ignore_area["y_max"]), outline=(255, 66, 66), width=2)
        draw.text((ignore_area["x_min"]+10, ignore_area["y_min"]+10), f"ignore", fill=(255, 66, 66))

    file_name = f"{config.settings['capture_dir']}/{camera_name}-{start}.jpg"
    im.save(file_name, quality=100)
    im.close()
    end = time.time()
    runtime = round(end - start, 1)
    logging.debug(f"Saved captured and annotated image: {file_name} in {runtime} seconds.")
