import cv2
import mediapipe as mp
import time
import subprocess
import numpy as np
import sys

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

# rpicam-vid setup for raw YUV data
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
    print("Gesture recognizer active. Printing results to terminal...")
    print("Press Ctrl+C to quit.")

    try:
        while True:
            # Read a frame from the pipe
            raw_frame = pipe.stdout.read(int(width * height * 1.5))
            
            if not raw_frame:
                break

            # Process the raw buffer into an RGB image for MediaPipe
            yuv = np.frombuffer(raw_frame, dtype=np.uint8).reshape((int(height * 1.5), width))
            frame = cv2.cvtColor(yuv, cv2.COLOR_YUV2RGB_I420)
            
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)

            # Send to MediaPipe
            timestamp = int(time.time() * 1000)
            recognizer.recognize_async(mp_image, timestamp)

            # Print results to terminal
            if latest_result and latest_result.gestures:
                for gesture in latest_result.gestures:
                    name = gesture[0].category_name
                    score = round(gesture[0].score, 2)
                    print(f"Detected: {name} (Confidence: {score})")
            
            # Small sleep to prevent terminal flooding
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nStopping jukebox control...")
    finally:
        pipe.terminate()
        sys.exit()
