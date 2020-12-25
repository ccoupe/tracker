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
from http.server import BaseHTTPRequestHandler,HTTPServer
import queue as Queue
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
http_active = False
zmq_active = False
loop_running = False
stream_handle = None
imageQ = None

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
  #frame = imutils.resize(image, width=400) 
  frame = image
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


def create_stream(keep=False):
  global stream_handle, settings, loop_running, hmqtt, log, http_active, zmq_active
  log.info('create stream')
  http_active = False
  debugF = None
  if keep:
    # write to a file for debugging
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    debugF = cv2.VideoWriter('/tmp/tracker.avi',fourcc, 15, (640,480)); 
      
  # notify kodi and Login Panel that the stream is active
  hmqtt.seturi(json.dumps({'uri':f'http://{settings.our_IP}:{settings.http_post}/tracker.cam'}))
  totfr = 0
  cnt = 0
  zmq_active = True
  while zmq_active:
    #(rpiName, frame) = imageHub.recv_image()
    rpiName, jpg_buffer = imageHub.recv_jpg()
    frame = cv2.imdecode(np.frombuffer(jpg_buffer, dtype='uint8'), -1)
    #log.info(f'got frame from {rpiName}')
    tf, rect = shapes_detect(frame, settings.confidence, debug)
    if tf:
      (x, y, ex, ey) = rect
      cnt += 1
      dt = {'cmd': "trk", 'cnt': cnt, "x": int(x), "y": int(y), "ex": int(ex), "ey": int(ey)}
      jstr = json.dumps(dt)
      #log.info(jstr)
      for tur in settings.turrets: 
        hmqtt.client.publish(tur, jstr)
      if http_active:
        cv2.rectangle(frame,(x,y),(ex,ey),(0,255,210),4)
    
    if debugF:
      debugF.write(frame)
    if http_active:
      # push to end of queue if http thread is active
      if imageQ.full: 
        # make room by removing the first item, try not to block the
        # put call.
        try:
          imageQ.get_nowait()
        except Queue.Empty:
          pass
      imageQ.put(frame)
      
    totfr += 1
    imageHub.send_reply(b'OK')
		
  if debugF:
    debugF.release()
  log.info(f' wrote {cnt} movements out of {totfr}')

  
def end_stream():
  global stream_handle, loop_running, zmq_active
  log.info('end stream')
  zmq_active = False
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
    if args.get('debug', False):
      create_stream(keep=True)
    else:
      create_stream(keep=False)
  elif args.get('end', False):
    
    end_stream()
  else:
    # ignore anything else, since we probably sent the msg,
    # we should not act on it
    pass
  
# http server - starts at program launch 
class CamHandler(BaseHTTPRequestHandler):
  
  def do_GET(self):
    global http_active, zmq_active, log
    log.info(self.path)
    if self.path.endswith('.mjpg'):
      http_active = True
      self.send_response(200)
      self.send_header('Content-type','multipart/x-mixed-replace; boundary=--jpgboundary')
      self.end_headers()
      while http_active:
        # Get a opencv image from the queue
        try:
          img = imageQ.get(timeout=3)
        except Queue.Empty:
          # stream end if no image in 3 secs 
          # if zmq_active == False then it no more images for us
          log.info('http closing because {"end":}')
          self.close_connection = True
          break
        r, buf = cv2.imencode(".jpg",img)
        self.wfile.write(bytes("--jpgboundary\r\n", encoding="utf-8"))
        self.send_header('Content-type','image/jpeg')
        self.send_header('Content-length',str(len(buf)))
        self.end_headers()
        self.wfile.write(buf)
        self.wfile.write(bytes('\r\n', encoding="utf-8"))
        #time.sleep(0.5)
        
      http_active = False
      return
      
    if self.path.endswith('.html') or self.path=="/":
      self.send_response(200)
      self.send_header('Content-type','text/html')
      self.end_headers()
      self.wfile.write(bytes('<html><head></head><body>', encoding="utf-8"))
      self.wfile.write(bytes('<img src="http://192.168.1.2:5000/cam.mjpg"/>', encoding="utf-8"))
      self.wfile.write(bytes('</body></html>', encoding="utf-8"))
      return

def main():
  global settings, hmqtt, log, imageHub, imageQ
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
  imageQ = Queue.Queue(maxsize=60)
  log.info('tracker running')
  server = HTTPServer(('',5000),CamHandler)
  log.info("http server started")
  server.serve_forever()

  #while True:
  #  time.sleep(5)
    
if __name__ == '__main__':
  sys.exit(main())

