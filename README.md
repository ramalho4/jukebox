# jukebox
Hand gesture controlled jukebox using a Raspberry Pi 5 with Raspberry Pi Camera using a navidrome music server. 

System Packages: 
    
    sudo apt install mpv ffmpeg python3-pip python3-venv


Python Packages: 

    pip install mediapipe opencv-python numpy py-sonic

If you have issues with installing pip packages, use a python environment with python version Python 3.12.8

The gesture recognizer model is incuded in this github as gesture_recognizer.task

You will have to configure your own navidrome and navidrome.toml files for the server

You will have to change the subsonic connection config at the top of gesture_jukebox.py to match the toml file

Usage: 

    python gesture_jukebox.py

Thumbs Up: Play a random song
Thumbs Down: Stop Playback
Open Palm: Pause/Resume
Closed Fist: Stop Playback
Point Up: Volume +10
ILoveYou: Volume -10 (pointer + pinky + thumb up)
Peace Sign: Shuffle Song


