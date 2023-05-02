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

  def __init__(self, settings, ctlCb, rgrCb):
    self.settings = settings
    self.log = settings.log
    self.ctlCb = ctlCb
    self.rgrCb = rgrCb
    # init server connection
    self.client = mqtt.Client(settings.mqtt_client_name, False)
    self.client.reconnect_delay_set(min_delay=1, max_delay=60)
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
    
    # these belong in settings.
    self.hcmds_sub = f'homie/{hdevice}/track/control/set'
    self.himg_sub = f'homie/{hdevice}/ranger/image/set'
    settings.hdist_pub = f'homie/{hdevice}/ranger/distance/set'
    
    #self.hcmds_pub = f'homie/{hdevice}/track/control'
    # short cuts to stuff we really care about
     
    self.log.debug("Homie_MQTT __init__")
   
    rc,_ = self.client.subscribe(self.hcmds_sub)
    if rc != mqtt.MQTT_ERR_SUCCESS:
      self.log.warn("Subscribe failed: %d" %rc)
    else:
      self.log.debug("Init() Subscribed to %s" % self.hcmds_sub)
      
    rc,_ = self.client.subscribe(self.himg_sub)
    if rc != mqtt.MQTT_ERR_SUCCESS:
      self.log.warn("Subscribe failed: %d" %rc)
    else:
      self.log.debug("Init() Subscribed to %s" % self.himg_sub)
      
    # we publish a 'wakeup' to either of these but not both. 
    # TODO: V2 - both should be allowed. Values should be from settings!!
    self.panel_pub = 'homie/panel_tracker/track/control/set'
    self.kodi_pub = 'homie/kodi_tracker/track/control/set'
      
  def create_top(self, hdevice, hlname):
    self.log.debug("Begin topic creation")
    # create topic structure at server - these are retained! 
    #self.client.publish("homie/"+hdevice+"/$homie", "3.0.1", mqos, retain=True)
    self.publish_structure("homie/"+hdevice+"/$homie", "3.0.1")
    self.publish_structure("homie/"+hdevice+"/$name", hlname)
    self.publish_structure("homie/"+hdevice+"/$status", "ready")
    self.publish_structure("homie/"+hdevice+"/$mac", self.settings.macAddr)
    self.publish_structure("homie/"+hdevice+"/$localip", self.settings.our_IP)
    # has two nodes: track
    self.publish_structure("homie/"+hdevice+"/$nodes", 'track,ranger')
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
    # ranger node
    prefix = f"homie/{hdevice}/ranger"
    self.publish_structure(f"{prefix}/$name", hlname)
    self.publish_structure(f"{prefix}/$type", "json")
    self.publish_structure(f"{prefix}/$properties","image,distance")
    # image Property of 'ranger'
    self.publish_structure(f"{prefix}/image/$name", hlname)
    self.publish_structure(f"{prefix}/image/$datatype", "image")
    self.publish_structure(f"{prefix}/image/$settable", "true")
    self.publish_structure(f"{prefix}/image/$retained", "false")
    # distance Property of 'ranger'
    self.publish_structure(f"{prefix}/distance/$name", hlname)
    self.publish_structure(f"{prefix}/distance/$datatype", "json")
    self.publish_structure(f"{prefix}/distance/$settable", "true")
    self.publish_structure(f"{prefix}/distance/$retained", "false")


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
    try:
      if topic == self.hcmds_sub:
        self.log.info("on_message %s %s" % (topic, payload))
        ctl_thr = Thread(target=self.ctlCb, args=(None, payload))
        ctl_thr.start()
      elif topic == self.himg_sub:
        self.log.info("on_message %s %i" % (topic, len(payload)))
        rgr_thr = Thread(target=self.rgrCb, args=(None, payload))
        rgr_thr.start()
      else:
        self.log.warn('unknown topic/payload')
    except:
      traceback.print_exc()

    
  def isConnected(self):
    return self.mqtt_connected

  def on_connect(self, client, userdata, flags, rc):
    if rc != mqtt.MQTT_ERR_SUCCESS:
      self.log.warn("Connection failed")
      self.mqtt_connected = False
      time.sleep(60)
      self.client.reconnect()
    else:
      self.mqtt_connected = True
       
  def on_disconnect(self, client, userdata, rc):
    self.mqtt_connected = False
    if rc != 0:
      self.log.warn(f"mqtt disconnect: {rc}, attempting reconnect")
      self.client.reconnect()
      
  def seturi_panel (self, jstr):
    self.log.info(f'sending {jstr} to {self.panel_pub}')
    self.client.publish(self.panel_pub, jstr)
    
  def seturi_kodi (self, jstr):
    self.log.info(f'sending {jstr} to {self.kodi_pub}')
    self.client.publish(self.kodi_pub, jstr)

