# Groundhog Perception — Intel RealSense D455

Depth-camera server for the Pi. One pyrealsense2 process streams **RGB / colorized depth / IR** over MJPEG with a web control panel, plus:

- **Distance + obstacle** — center + nearest-in-front, obstacle flag inside 0.8 m
- **Near-object box** — depth-blob bounding box (works in the dark; boxes the closest thing)
- **AI person detection** — YOLOv8n (COCO) on the RGB, boxes labeled `person` + confidence, **fused with depth for distance**
- **Accuracy tools** — center crosshair overlay + flat-wall plane-fit (RMS noise, fill %)

Live panel: `http://<pi-ip>:8090/` (LAN only).

## Hardware
Intel RealSense **D455** on the Pi via **USB3** (needs a blue SS port). Runs on the same Pi that hosts the LC29H RTK HAT.

## Setup (Raspberry Pi 4, Debian 13 / aarch64)

### 1. librealsense SDK (from source — no apt pkg / pip wheel for py3.13/aarch64)
```bash
sudo apt-get install -y git cmake build-essential pkg-config libssl-dev libusb-1.0-0-dev libudev-dev python3-dev
git clone --depth 1 https://github.com/realsenseai/librealsense.git   # (IntelRealSense redirects here)
cd librealsense && mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DFORCE_RSUSB_BACKEND=true \
  -DBUILD_PYTHON_BINDINGS=true -DPYTHON_EXECUTABLE=/usr/bin/python3 \
  -DBUILD_EXAMPLES=false -DBUILD_GRAPHICAL_EXAMPLES=false -DBUILD_TOOLS=true
#  ^ BUILD_EXAMPLES=true FAILS at cmake (glfw needs X11 RandR headers, absent on headless Pi)
make -j3 && sudo make install && sudo ldconfig
# udev rules — without these the non-root user gets RS2_USB_STATUS_ACCESS
sudo cp ../config/99-realsense-libusb.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### 2. Python runtime (venv inherits system pyrealsense2/numpy/PIL/scipy)
```bash
python3 -m venv --system-site-packages ~/rsvenv
~/rsvenv/bin/pip install onnxruntime
```

### 3. AI model (COCO YOLOv8n, person = class 0)
```bash
mkdir -p ~/models
curl -sL "https://huggingface.co/kshitijjjjjjjjjjjjjjjj/yolov8n-coco-onnx/resolve/main/yolov8n.onnx?download=true" -o ~/models/yolov8n.onnx
# input [1,3,640,640] -> output [1,84,8400]
```

### 4. Run as a service (root — librealsense needs exclusive USB access)
```bash
sudo systemd-run --unit=mjc --property=Restart=always --property=RestartSec=4 \
  ~/rsvenv/bin/python ~/depthcam.py
```
`depthcam.py` must live **outside `/tmp`** (it gets cleaned). Runs as root because librealsense can't share the device and root bypasses udev.

## HTTP endpoints
| Path | Purpose |
|------|---------|
| `/` | control panel (video + all controls) |
| `/stream` | MJPEG multipart of the selected view |
| `/telemetry` | JSON: center, min, obstacle, fps, view, box, people, ai_ready |
| `/set?k=&v=` | `view` color/depth/ir · `emitter` 0/1 · `laser` 0-360 · `detect` 0/1 · `near` m · `ai` 0/1 |
| `/planefit` | flat-wall accuracy: mean, rms_mm, rms_pct, fill_pct |
| `/snapshot` | current JPEG still |

## Notes / gotchas
- **Exclusive USB access** — pyrealsense2 and any ffmpeg/v4l2 grab can't both hold the D455. This is the sole camera owner.
- **Depth works in the dark** (the IR dot projector provides texture). RGB does not — it's not a night-vision camera.
- **Accuracy** — Intel spec < 2% to 4 m; verified ~4% at 2.9 m (angle/reference-point error, plenty for obstacle use). Fill ~100%.
- **AI is CPU-heavy** — ~3-5 fps detection on the Pi 4, off by default; the 15 fps stream is unaffected (separate thread).
- Model file (`~/models/yolov8n.onnx`, ~13 MB) is **not committed** — fetch via step 3.
