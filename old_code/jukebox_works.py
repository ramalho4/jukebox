import cv2
import mediapipe as mp
import time
import subprocess
import numpy as np

BaseOptions = mp.tasks.BaseOptions
GestureRecognizer = mp.tasks.vision.GestureRecognizer
GestureRecognizerOptions = mp.tasks.vision.GestureRecognizerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

latest_result = None

def result_callback(result: mp.tasks.vision.GestureRecognizerResult, output_image: mp.Image, timestamp_ms: int):
    global latest_result
    latest_result = result

options = GestureRecognizerOptions(
    base_options=BaseOptions(model_asset_path='gesture_recognizer.task'),
    running_mode=VisionRunningMode.LIVE_STREAM,
    result_callback=result_callback
)

# Set resolution for the pipe
width, height = 640, 480

# Use rpicam-vid to pipe raw YUV data to stdout
# This is the most stable way to get the Wide Camera feed on Pi 5
command = [
    'rpicam-vid',
    '-t', '0',
    '--width', str(width),
    '--height', str(height),
    '--inline',
    '--nopreview',
    '--codec', 'yuv420',
    '-o', '-'
]

pipe = subprocess.Popen(command, stdout=subprocess.PIPE, bufsize=10**8)

with GestureRecognizer.create_from_options(options) as recognizer:
    print("Gesture recognizer active. Press q in the window to quit.")

    try:
        while True:
            # Read a frame from the pipe (YUV420 format)
            raw_frame = pipe.stdout.read(int(width * height * 1.5))
            
            if not raw_frame:
                break

            # Convert raw YUV420 to a BGR image OpenCV can use
            yuv = np.frombuffer(raw_frame, dtype=np.uint8).reshape((int(height * 1.5), width))
            frame = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

            timestamp = int(time.time() * 1000)
            recognizer.recognize_async(mp_image, timestamp)

            if latest_result and latest_result.gestures:
                for i, gesture in enumerate(latest_result.gestures):
                    name = gesture[0].category_name
                    score = round(gesture[0].score, 2)
                    cv2.putText(frame, f"{name} ({score})", (20, 50 + (i * 40)),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            cv2.imshow('Pi 5 Wide Camera - Direct Pipe', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        pipe.terminate()
        cv2.destroyAllWindows()
