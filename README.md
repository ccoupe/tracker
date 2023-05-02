# tracker
Trumpybear sends images from its camera (as jpg). Tracker finds the 'person' 
shape in the image and the bounding box for the shape. It sends the bounding 
box to the turrets via mqtt so they can follow/aim at the middle of the shape.

Wait, there is more. We can create mjpeg stream of the images with
bounding box drawn and notify an mqtt topic when the stream is available 
(or closed) so different followers could display the stream (kodi for
example or the login panel or both) 

Things to put in requirements.txt:
pip install paho-mqtt
pip install imutils
pip install imagezmq
pip install gputil # so we can detect and use a gpu.

