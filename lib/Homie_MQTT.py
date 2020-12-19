#!/usr/bin/env python3
import paho.mqtt.client as mqtt
import sys, traceback
import json
from datetime import datetime
from threading import Thread
import time

import time

# Deal with multiple turrets but we only have ONE mqtt instance.
class Homie_MQTT:

  def __init__(self, settings, ctlCb):
    self.settings = settings
    self.log = settings.log
    self.ctlCb = ctlCb
    # init server connection
    self.client = mqtt.Client(settings.mqtt_client_name, False)
    #self.client.max_queued_messages_set(3)
    hdevice = self.hdevice = self.settings.homie_device  # "device_name"
    hlname = self.hlname = self.settings.homie_name     # "Display Name"
    self.client.on_message = self.on_message
    self.client.on_disconnect = self.on_disconnect
    rc = self.client.connect(settings.mqtt_server, settings.mqtt_port)
    if rc != mqtt.MQTT_ERR_SUCCESS:
        self.log.warn("network missing?")
        exit()
    self.client.loop_start()
    self.create_top(hdevice, hlname)
    
    self.hcmds_sub = f'homie/{hdevice}/track/control/set'
    #self.hcmds_pub = f'homie/{hdevice}/track/control'
    # short cuts to stuff we really care about
     
    self.log.debug("Homie_MQTT __init__")
   
    rc,_ = self.client.subscribe(self.hcmds_sub)
    if rc != mqtt.MQTT_ERR_SUCCESS:
      self.log.warn("Subscribe failed: %d" %rc)
    else:
      self.log.debug("Init() Subscribed to %s" % self.hcmds_sub)
      
  def create_top(self, hdevice, hlname):
    self.log.debug("Begin topic creation")
    # create topic structure at server - these are retained! 
    #self.client.publish("homie/"+hdevice+"/$homie", "3.0.1", mqos, retain=True)
    self.publish_structure("homie/"+hdevice+"/$homie", "3.0.1")
    self.publish_structure("homie/"+hdevice+"/$name", hlname)
    self.publish_structure("homie/"+hdevice+"/$status", "ready")
    self.publish_structure("homie/"+hdevice+"/$mac", self.settings.macAddr)
    self.publish_structure("homie/"+hdevice+"/$localip", self.settings.our_IP)
    # has one node: track
    self.publish_structure("homie/"+hdevice+"/$nodes", 'track')
    self.create_topics, hdevice, hlname
    
  def create_topics(self, hdevice, hlname):
    # track node
    prefix = f"homie/{hdevice}/track"
    self.publish_structure(f"{prefix}/$name", hlname)
    self.publish_structure(f"{prefix}/$type", "rurret")
    self.publish_structure(f"{prefix}/$properties","control")
    # control Property of 'track'
    self.publish_structure(f"{prefix}/control/$name", hlname)
    self.publish_structure(f"{prefix}/control/$datatype", "string")
    self.publish_structure(f"{prefix}/control/$settable", "false")
    self.publish_structure(f"{prefix}/control/$retained", "true")

   # Done with structure. 

    self.log.debug(f"{prefix} topics created")
    # nothing else to publish 
    
  def publish_structure(self, topic, payload):
    self.client.publish(topic, payload, qos=1, retain=True)
    
  def on_subscribe(self, client, userdata, mid, granted_qos):
    self.log.debug("Subscribed to %s" % self.hurl_sub)

  def on_message(self, client, userdata, message):
    settings = self.settings
    topic = message.topic
    payload = str(message.payload.decode("utf-8"))
    self.log.info("on_message %s %s" % (topic, payload))
    try:
      if topic == self.hcmds_sub:
        ctl_thr = Thread(target=self.ctlCb, args=(None, payload))
        ctl_thr.start()
      else:
        self.log.warn('unknown topic/payload')
    except:
      traceback.print_exc()

    
  def isConnected(self):
    return self.mqtt_connected

  def on_connect(self, client, userdata, flags, rc):
    self.log.debug("Subscribing: %s %d" (type(rc), rc))
    if rc == 0:
      self.log.debug("Connecting to %s" % self.mqtt_server_ip)
      rc,_ = self.client.subscribe(self.hurl_sub)
      if rc != mqtt.MQTT_ERR_SUCCESS:
        self.log.debug("Subscribe failed: ", rc)
      else:
        self.log.debug("Subscribed to %s" % self.hurl_sub)
        self.mqtt_connected = True
    else:
      self.log.debug("Failed to connect: %d" %rc)
    self.log.debug("leaving on_connect")
       
  def on_disconnect(self, client, userdata, rc):
    self.mqtt_connected = False
    self.log.info("mqtt reconnecting")
    self.client.reconnect()
      
  def seturi (self, jstr):
    self.client.publish(self.hcmds_sub, jstr)

