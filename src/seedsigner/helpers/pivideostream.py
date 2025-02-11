# import the necessary packages
from picamera.array import PiRGBArray
from picamera import PiCamera
from threading import Thread
import time


# Modified from: https://github.com/jrosebr1/imutils
class PiVideoStream:
	def __init__(self, resolution=(320, 240), framerate=32, **kwargs):
		# initialize the camera
		self.camera = PiCamera(resolution=resolution, framerate=framerate, **kwargs)

		# initialize the stream
		self.rawCapture = PiRGBArray(self.camera, size=resolution)
		self.stream = self.camera.capture_continuous(self.rawCapture,
			format="bgr", use_video_port=True)

		# initialize the frame and the variable used to indicate
		# if the thread should be stopped
		self.frame = None
		self.stopped = False

	def start(self):
		# start the thread to read frames from the video stream
		t = Thread(target=self.update, args=())
		t.daemon = True
		t.start()
		return self

	def update(self):
		# keep looping infinitely until the thread is stopped
		for f in self.stream:
			# grab the frame from the stream and clear the stream in
			# preparation for the next frame
			self.frame = f.array
			self.rawCapture.truncate(0)

			# if the thread indicator variable is set, stop the thread
			# and resource camera resources
			if self.stopped:
				print("PiVideoStream: closing everything")
				self.stream.close()
				self.rawCapture.close()
				self.camera.close()
				return

	def read(self):
		# return the frame most recently read
		return self.frame

	def stop(self):
		# indicate that the thread should be stopped
		self.stopped = True

		# while True:
		# 	# Wait for camera to close before letting the thread get destroyed
		# 	if not self.camera.closed:
		# 		time.sleep(0.1)
		# 	else:
		# 		break

