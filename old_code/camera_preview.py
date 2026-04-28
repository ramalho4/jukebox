import subprocess, threading, time, signal
from http.server import BaseHTTPRequestHandler, HTTPServer
import numpy as np

WIDTH, HEIGHT = 640, 480
YUV_FRAME_BYTES = WIDTH * HEIGHT * 3 // 2
CROP_X = (WIDTH - HEIGHT) // 2
SQUARE = HEIGHT

latest_jpeg = b""
lock = threading.Lock()

def yuv_to_jpeg(raw):
    import struct
    yuv = np.frombuffer(raw, dtype=np.uint8).reshape((HEIGHT * 3 // 2, WIDTH))
    y = yuv[:HEIGHT].astype(np.float32)
    u = yuv[HEIGHT:HEIGHT+HEIGHT//4].reshape(HEIGHT//2, WIDTH//2).astype(np.float32) - 128
    v = yuv[HEIGHT+HEIGHT//4:].reshape(HEIGHT//2, WIDTH//2).astype(np.float32) - 128
    u = np.repeat(np.repeat(u,2,axis=0),2,axis=1)
    v = np.repeat(np.repeat(v,2,axis=0),2,axis=1)
    r = np.clip(y + 1.402*v,            0, 255).astype(np.uint8)
    g = np.clip(y - 0.344*u - 0.714*v, 0, 255).astype(np.uint8)
    b = np.clip(y + 1.772*u,            0, 255).astype(np.uint8)
    rgb = np.stack([r,g,b], axis=2)[:, CROP_X:CROP_X+SQUARE, :]
    # encode as JPEG using only stdlib + numpy (via PPM → convert)
    import io, struct
    # Write PPM then pipe through cjpeg if available, else return raw PPM
    try:
        import subprocess as sp
        ppm = b"P6\n480 480\n255\n" + rgb.tobytes()
        result = sp.run(["cjpeg", "-quality", "60"], input=ppm, capture_output=True)
        if result.returncode == 0:
            return result.stdout
    except FileNotFoundError:
        pass
    # fallback: try PIL
    try:
        from PIL import Image
        import io
        img = Image.fromarray(rgb)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=60)
        return buf.getvalue()
    except ImportError:
        pass
    return None

def camera_thread():
    global latest_jpeg
    cmd = ["rpicam-vid","--width",str(WIDTH),"--height",str(HEIGHT),
           "--framerate","10","--codec","yuv420","--libav-format","rawvideo",
           "--flush","--output","-","--timeout","0","--nopreview","-n"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=YUV_FRAME_BYTES*4)
    time.sleep(2)
    proc.stdout.read1(YUV_FRAME_BYTES * 3)
    while True:
        raw = proc.stdout.read(YUV_FRAME_BYTES)
        if len(raw) != YUV_FRAME_BYTES:
            break
        jpeg = yuv_to_jpeg(raw)
        if jpeg:
            with lock:
                latest_jpeg = jpeg

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type","text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><img src='/stream' style='width:100%'></body></html>")
        elif self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type","multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                while True:
                    with lock:
                        jpeg = latest_jpeg
                    if jpeg:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
                    time.sleep(0.1)
            except Exception:
                pass

if __name__ == "__main__":
    t = threading.Thread(target=camera_thread, daemon=True)
    t.start()
    ip = subprocess.run(["hostname","-I"], capture_output=True, text=True).stdout.split()[0]
    print(f"[preview] Open http://{ip}:8080 in your browser")
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
