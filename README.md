# tracker
Trumpybear sends images from its camera (as jpg). Tracker finds the 'person' 
shape in the image and the bounding box for the shape. It sends the bounding 
box to the turrets via mqtt so the can follow/aim at the middle of the shape.

Wait, there is more. We can create an udp rtsp stream of the images with bounding box drawn and notify an mqtt topic when the stream is available (or closed) sodifferent followers could display the stream (kodi for example or the login panel)
