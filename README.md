# Coffee Bean Sorting System
## Color and Size Detection — Raspberry Pi + FastAPI + React

Real-time coffee bean grading system using Raspberry Pi Camera, OpenCV, and a neumorphism React dashboard.

---

## Hardware

| Component | Specification |
|-----------|--------------|
| Raspberry Pi 5 | Quad-core 2.4 GHz, 4–8 GB RAM |
| RPi Camera Module | v2 (8MP) or v3 (12MP), CSI interface |
| Waveshare LCD | 7–10 inch touchscreen (HDMI/DSI) |
| Air Compressor | 0.4–0.8 MPa, 50–100 L/min, 20–50 L tank |
| Solenoid Valves | 5× 2/2-way NC, 24V DC |
| Conveyor Relay | GPIO 25 |
| LED Lighting | White ring/stripe, 10k–50k lux, 5500–6500K |

---

## GPIO Wiring (BCM)

```
GPIO 17 → Solenoid Valve 1  (Defective ejector)
GPIO 27 → Solenoid Valve 2  (Premium gate)
GPIO 22 → Solenoid Valve 3  (Grade 1 gate)
GPIO 23 → Solenoid Valve 4  (Grade 2 gate)
GPIO 24 → Solenoid Valve 5  (Grade 3 gate)
GPIO 25 → Conveyor belt relay
GPIO 18 → Air compressor relay
```

> All valves are Normally Closed — HIGH opens them.

---

## Software Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Vision | OpenCV 4.9, picamera2, NumPy |
| Frontend | React 18, Vite, Recharts |
| Realtime | WebSocket (FastAPI + native browser WS) |
| GPIO | RPi.GPIO |

---

## Grading Logic

| Grade | Size | Color | Defects |
|-------|------|-------|---------|
| **Premium** | ≥ 8.0 mm | Uniform deep brown (HSV H:8–28, S:≥80) | None |
| **Grade 1** | 7.0–8.0 mm | Good brown | Minor only |
| **Grade 2** | 6.0–7.0 mm | Acceptable variation | Surface OK |
| **Grade 3** | 5.0–6.0 mm | Faded / uneven roast | Sour/surface |
| **Defective** | < 5.0 mm | Black/burnt, pale/raw, mold | Severe |

### Detection pipeline

1. Capture BGR frame from picamera2
2. CLAHE contrast normalisation + sharpening
3. HSV colour mask (H:5–35, S:40–255, V:25–220)
4. Morphological open/close to remove noise
5. `findContours` → filter by area (400–8000 px²)
6. `minEnclosingCircle` → diameter in mm (calibrate `PIXELS_PER_MM`)
7. Mean HSV of ROI → colour profile + defect checks
8. Grade classification + confidence score
9. Draw annotated bounding box → JPEG → WebSocket broadcast

---

## Quick Start (Raspberry Pi)

```bash
git clone <repo> coffee_bean_sorting
cd coffee_bean_sorting
chmod +x scripts/setup_rpi.sh
./scripts/setup_rpi.sh
```

After setup, open the Waveshare LCD browser:
```
http://localhost:8000
```

### Manual start

```bash
# Backend only (production — serves built React from /frontend/dist)
./scripts/start.sh

# Development (backend + React hot-reload)
./scripts/start_dev.sh
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/system/command` | `start` / `stop` / `pause` / `resume` / `reset` / `emergency_stop` |
| `GET`  | `/api/stats` | Current system statistics snapshot |
| `GET`  | `/api/beans?limit=50` | Recent bean detection history |
| `GET`  | `/api/alerts?limit=50` | Alert log |
| `POST` | `/api/alerts/{id}/resolve` | Resolve individual alert |
| `GET`  | `/api/settings` | Current settings |
| `POST` | `/api/settings` | Update settings |
| `GET`  | `/stream` | MJPEG stream (raw camera or annotated) |
| `GET`  | `/api/camera/snapshot` | Single JPEG snapshot |
| `POST` | `/api/calibrate/pixels_per_mm` | Set size calibration |
| `WS`   | `/ws` | WebSocket (stats/bean/alert/frame events) |

---

## Calibration

1. Place a known-size object (e.g. 10mm coin) on the conveyor
2. Take a snapshot: `GET /api/camera/snapshot`
3. Measure its pixel diameter in any image editor
4. Calculate: `pixels_per_mm = measured_pixels / 10`
5. Apply: `POST /api/calibrate/pixels_per_mm?pixels_per_mm=<value>`
   or use the Settings page in the UI.

---

## File Structure

```
coffee_bean_sorting/
├── backend/
│   ├── main.py                  # FastAPI app, MJPEG stream, WS route
│   ├── requirements.txt
│   ├── api/
│   │   ├── routes.py            # REST endpoints
│   │   └── websocket.py        # WS manager + detection broadcast loop
│   └── core/
│       ├── models.py            # Pydantic models, AppState
│       ├── camera.py            # picamera2 / OpenCV camera wrapper
│       ├── detector.py          # OpenCV bean detection + grading
│       └── sorting_controller.py# GPIO valve/conveyor/compressor control
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Router + WebSocket wiring
│   │   ├── index.css            # Neumorphism design system
│   │   ├── components/          # Sidebar, Header, CameraFeed, Charts…
│   │   ├── pages/               # Overview, Detection, Assessment…
│   │   ├── hooks/               # useWebSocket, useToast
│   │   └── services/api.js      # REST fetch wrapper
│   └── vite.config.js
└── scripts/
    ├── setup_rpi.sh             # One-time RPi setup
    ├── start.sh                 # Production start
    └── start_dev.sh             # Dev mode (hot reload)
```
