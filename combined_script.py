import cv2
import mediapipe as mp
import time
import subprocess
import numpy as np
import sys
import libsonic
import threading
from urllib.parse import urlencode

# ─────────────────────────────────────────────
# Subsonic connection config
# ─────────────────────────────────────────────
SERVER_IP   = "http://10.42.0.1"
SERVER_PORT = 4533
USER        = "christopher"
PASSWORD    = "72555"

conn = libsonic.Connection(
    baseUrl=SERVER_IP,
    username=USER,
    password=PASSWORD,
    port=SERVER_PORT
)

# ─────────────────────────────────────────────
# Playback state
# ─────────────────────────────────────────────
mpv_process   = None          # current mpv subprocess
paused        = False         # pause toggle
volume        = 70            # 0–100
playback_lock = threading.Lock()

# ─────────────────────────────────────────────
# Subsonic helpers
# ─────────────────────────────────────────────
def get_stream_url(song_id):
    query = conn._getBaseQdict()
    query['id'] = song_id
    return f"{conn._baseUrl}:{conn._port}/{conn._serverPath}/stream.view?{urlencode(query)}"


def fetch_random_song():
    """Return (title, artist, stream_url) or None on failure."""
    try:
        response = conn.getRandomSongs(size=1)
        songs = response.get("randomSongs", {}).get("song", [])
        if songs:
            track = songs[0]
            return track.get("title"), track.get("artist"), get_stream_url(track["id"])
    except Exception as e:
        print(f"[Subsonic] Error fetching song: {e}")
    return None

# ─────────────────────────────────────────────
# Playback control helpers
# ─────────────────────────────────────────────
def _kill_mpv():
    global mpv_process, paused
    if mpv_process and mpv_process.poll() is None:
        mpv_process.terminate()
        try:
            mpv_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            mpv_process.kill()
    mpv_process = None
    paused = False


def play_song():
    """Fetch a random song and start streaming it in mpv."""
    global mpv_process, paused, volume
    with playback_lock:
        _kill_mpv()
        info = fetch_random_song()
        if not info:
            print("[Player] Could not fetch a song.")
            return
        title, artist, url = info
        print(f"[Player] ▶  Now playing: {title} by {artist}")
        mpv_process = subprocess.Popen(
            ["mpv", "--no-video", f"--volume={volume}", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        paused = False


def stop_playback():
    global mpv_process
    with playback_lock:
        if mpv_process and mpv_process.poll() is None:
            print("[Player] ⏹  Stopped.")
            _kill_mpv()
        else:
            print("[Player] Nothing is playing.")


def toggle_pause():
    """
    mpv doesn't expose a simple pause socket in this subprocess setup,
    so we simulate pause by killing/restarting. For a real pause you'd
    use mpv's --input-ipc-server; this keeps the script self-contained.
    """
    global paused, mpv_process
    with playback_lock:
        if paused:
            # Resume: start a new random song (simple approach)
            paused = False
            print("[Player] ▶  Resuming (new random track)...")
        else:
            if mpv_process and mpv_process.poll() is None:
                _kill_mpv()
                paused = True
                print("[Player] ⏸  Paused.")
            else:
                print("[Player] Nothing to pause.")


def change_volume(delta):
    """Adjust volume by delta (e.g. +10 or -10). Restarts mpv if playing."""
    global volume, mpv_process
    volume = max(0, min(100, volume + delta))
    print(f"[Player] 🔊  Volume → {volume}")
    with playback_lock:
        if mpv_process and mpv_process.poll() is None:
            # Re-launch current stream with new volume by skipping to next song
            # (simplest stateless approach; swap for IPC if you want exact seek)
            _kill_mpv()
    # Start a new song at updated volume
    threading.Thread(target=play_song, daemon=True).start()


# ─────────────────────────────────────────────
# Gesture → action mapping
# ─────────────────────────────────────────────
# Gesture labels from MediaPipe hand gesture recognizer:
#   Unknown, Closed_Fist, Open_Palm, Pointing_Up,
#   Thumb_Down, Thumb_Up, Victory, ILoveYou

COOLDOWN_SEC = 5.0   # minimum seconds between gesture triggers

last_gesture      = None
last_gesture_time = 0.0


def handle_gesture(name: str):
    global last_gesture, last_gesture_time

    now = time.time()
    # Ignore if same gesture fired too recently
    if name == last_gesture and (now - last_gesture_time) < COOLDOWN_SEC:
        return
    if name == "Unknown":
        return

    last_gesture      = name
    last_gesture_time = now

    print(f"[Gesture] Detected: {name}")

    if name == "Thumb_Up":
        # Next / play a random song
        threading.Thread(target=play_song, daemon=True).start()

    elif name == "Thumb_Down":
        # Stop current song
        threading.Thread(target=stop_playback, daemon=True).start()

    elif name == "Open_Palm":
        # Pause / Resume
        threading.Thread(target=toggle_pause, daemon=True).start()

    elif name == "Closed_Fist":
        # Hard stop
        threading.Thread(target=stop_playback, daemon=True).start()

    elif name == "Pointing_Up":
        # Volume up
        threading.Thread(target=change_volume, args=(+10,), daemon=True).start()

    elif name == "ILoveYou":
        # Volume down
        threading.Thread(target=change_volume, args=(-10,), daemon=True).start()

    elif name == "Victory":
        # Shuffle: skip to a new random song
        threading.Thread(target=play_song, daemon=True).start()

# ─────────────────────────────────────────────
# MediaPipe gesture recognizer setup
# ─────────────────────────────────────────────
BaseOptions          = mp.tasks.BaseOptions
GestureRecognizer   = mp.tasks.vision.GestureRecognizer
GestureRecognizerOptions = mp.tasks.vision.GestureRecognizerOptions
VisionRunningMode   = mp.tasks.vision.RunningMode

latest_result = None

def result_callback(result: mp.tasks.vision.GestureRecognizerResult,
                    output_image: mp.Image,
                    timestamp_ms: int):
    global latest_result
    latest_result = result

options = GestureRecognizerOptions(
    base_options=BaseOptions(model_asset_path='gesture_recognizer.task'),
    running_mode=VisionRunningMode.LIVE_STREAM,
    result_callback=result_callback
)

# ─────────────────────────────────────────────
# Camera (rpicam-vid via pipe)
# ─────────────────────────────────────────────
WIDTH, HEIGHT = 640, 480

camera_cmd = [
    'rpicam-vid',
    '-t', '0',
    '--width',  str(WIDTH),
    '--height', str(HEIGHT),
    '--inline',
    '--nopreview',
    '--codec', 'yuv420',
    '-o', '-'
]

pipe = subprocess.Popen(camera_cmd, stdout=subprocess.PIPE, bufsize=10**8)

# ─────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────
print("=" * 50)
print("  Gesture Jukebox")
print("=" * 50)
print("  👍  Thumb Up    → Play random song")
print("  👎  Thumb Down  → Stop")
print("  ✋  Open Palm   → Pause / Resume")
print("  ✊  Closed Fist → Stop")
print("  ☝️  Pointing Up → Volume +10")
print("  🤘  ILoveYou    → Volume -10")
print("  ✌️  Victory     → Shuffle (next random)")
print("=" * 50)
print("Press Ctrl+C to quit.\n")

with GestureRecognizer.create_from_options(options) as recognizer:
    try:
        while True:
            raw_frame = pipe.stdout.read(int(WIDTH * HEIGHT * 1.5))
            if not raw_frame:
                break

            yuv   = np.frombuffer(raw_frame, dtype=np.uint8).reshape((int(HEIGHT * 1.5), WIDTH))
            frame = cv2.cvtColor(yuv, cv2.COLOR_YUV2RGB_I420)

            mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            timestamp = int(time.time() * 1000)
            recognizer.recognize_async(mp_image, timestamp)

            if latest_result and latest_result.gestures:
                for gesture in latest_result.gestures:
                    name  = gesture[0].category_name
                    score = round(gesture[0].score, 2)
                    if score >= 0.50:          # confidence threshold
                        handle_gesture(name)

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n[Jukebox] Shutting down...")
    finally:
        stop_playback()
        pipe.terminate()
        sys.exit(0)
