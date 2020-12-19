# Server for shape recognition. This will be started by systemd.
# NOTE:
#   Opencv must be build with gstreamer support which is not the default.
import cv2
import numpy as np
import imutils
import imagezmq
import sys
import json
import argparse
import warnings
from datetime import datetime
import time,threading, sched
import logging
import os
import os.path
import paho.mqtt.client as mqtt
import socket
from lib.Settings import Settings
from lib.Homie_MQTT import Homie_MQTT

debug = False;

classes = None
colors = None
dlnet = None
imageHub = None
wake_topic = 'homie/turret_tracker/control/set'
loop_running = False
stream_handle = None


def init_models():
  global classes, colors, dlnet
  classes = ["background", "aeroplane", "bicycle", "bird", "boat",
    "bottle", "bus", "car", "cat", "chair", "cow", "diningtable",
    "dog", "horse", "motorbike", "person", "pottedplant", "sheep",
    "sofa", "train", "tvmonitor"]
  colors = np.random.uniform(0, 255, size=(len(classes), 3))
  dlnet = cv2.dnn.readNetFromCaffe("shapes/MobileNetSSD_deploy.prototxt.txt",
    "shapes/MobileNetSSD_deploy.caffemodel")

        
def shapes_detect(image, threshold, debug):
	global dlnet, colors, dlnet
	#self.log("shape check")
	n = 0
	# grab the frame from the threaded video stream and resize it
	# to have a maximum width of 400 pixels
	frame = imutils.resize(image, width=400)

	# grab the frame dimensions and convert it to a blob
	(h, w) = frame.shape[:2]
	blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)),
		0.007843, (300, 300), 127.5)

	# pass the blob through the network and obtain the detections and
	# predictions
	dlnet.setInput(blob)
	detections = dlnet.forward()

	# loop over the detections
	for i in np.arange(0, detections.shape[2]):
		# extract the confidence (i.e., probability) associated with
		# the prediction
		confidence = detections[0, 0, i, 2]

		# filter out weak detections by ensuring the `confidence` is
		# greater than the minimum confidence
		if confidence > threshold:
			# extract the index of the class label from the
			# `detections`, then compute the (x, y)-coordinates of
			# the bounding box for the object
			idx = int(detections[0, 0, i, 1])
			if idx != 15:
				continue
			box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
			(startX, startY, endX, endY) = box.astype("int")
			#print(f'found {startX},{startY},{endX},{endY}')
			rect = (startX, startY, endX, endY)
			return (True, rect)
	
	return (False, None)


def create_stream():
	global stream_handle, settings, loop_running, hmqtt
	log.info('create stream')
	if settings.do_rtsp:
		#cc = f"appsrc ! videoconvert ! video/x-raw, format=I420, width=640, height=480, framerate=30/1 ! rtpvrawpay ! udpsink host={settings.our_IP} port=5000"
		#cc = f"appsrc ! videoconvert ! video/x-raw, format=I420, width=640, height=480, framerate=30/1 ! rtpvrawpay ! udpsink host=127.0.0.1 port=5000"
		cc = f'appsrc ! queue ! videoconvert ! video/x-raw ! omxh264enc ! video/x-h264 ! h264parse ! rtph264pay ! udpsink host={settings.our_IP} port=5000 sync=false'
		stream_handle = cv2.VideoWriter(cc,cv2.CAP_GSTREAMER, 0, 15, (640,480));   
		# notify kodi and Login Panel that the stream is active
		hmqtt.seturi(json.dumps({'uri':f'{settings.our_IP}:5000'}))
	else:
		stream_handle = None

	cnt = 0
	while loop_running:
		#(rpiName, frame) = imageHub.recv_image()
		rpiName, jpg_buffer = imageHub.recv_jpg()
		frame = cv2.imdecode(np.frombuffer(jpg_buffer, dtype='uint8'), -1)
		#log.info(f'got frame from {rpiName}')
		imageHub.send_reply(b'OK')
		tf, rect = shapes_detect(frame, settings.confidence, debug)
		if tf:
			(x, y, ex, ey) = rect
			cnt += 1
			dt = {'cmd': "trk", 'cnt': cnt, "x": int(x), "y": int(y), "ex": int(ex), "ey": int(ey)}
			jstr = json.dumps(dt)
			#log.info(jstr)
			for tur in settings.turrets: 
				hmqtt.client.publish(tur, jstr)
			if stream_handle:
				cv2.rectangle(frame,(x,y),(ex,ey),(0,255,210),4)
				
		if stream_handle:
			stream_handle.write(frame)
		
	if stream_handle:
		stream_handle.release()

  
def end_stream():
  global stream_handle, loop_running
  log.info('end stream')
  # setting uri to none means stream listeners should stop reading
  hmqtt.seturi(json.dumps({'uri':None}))
  pt = {'power': 0}
  for tur in settings.turrets:
    hmqtt.client.publish(tur, json.dumps(pt))
  
# callback is in it's own thread
def ctrlCB(self, jstr):
  global log, loop_running
  args = json.loads(jstr)
  log.info(f'args: {args}')
  if args.get('begin', False):
    loop_running = True
    create_stream()
  elif args.get('end', False):
    loop_running = False
    end_stream()
  else:
    # ignore anything else, we sent it and it's not for us to use
    pass
  
def main():
  global settings, hmqtt, log, imageHub
  # process args - port number, 
  ap = argparse.ArgumentParser()
  ap.add_argument("-c", "--conf", required=True, type=str,
    help="path and name of the json configuration file")
  args = vars(ap.parse_args())
  
  # logging setup
  logging.basicConfig(level=logging.DEBUG,format='%(asctime)s %(message)s')
  log = logging.getLogger('ML_Tracker')
  
  settings = Settings(log, (args["conf"]))
  hmqtt = Homie_MQTT(settings, ctrlCB)
  settings.print()
  
  # load the pre-computed models...
  init_models()

  log.info(f'listen on {settings.our_IP}:{settings.image_port}')
  imageHub = imagezmq.ImageHub(open_port=f'tcp://*:{settings.image_port}')
  
  log.info('tracker running')
  while True:
    time.sleep(5)
    
if __name__ == '__main__':
  sys.exit(main())

