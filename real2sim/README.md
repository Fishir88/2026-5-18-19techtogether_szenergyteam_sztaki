# Real2Sim: Human Motion to Robot Simulation

**Status**: ✅ MediaPipe baseline working | 🔄 MuJoCo integration in progress | 🔜 OpenClaw agent ready

Real2Sim is a system that captures human arm movements via webcam and mimics them in a simulated Unitree G1 humanoid robot. The agent (via OpenClaw) can learn from and control the simulation.

## Quick Start

### Prerequisites

- **Python 3.12** (MuJoCo + MediaPipe require 3.9+)
- **Windows PowerShell** (or WSL2 for Linux/Mac)
- **Webcam** (for pose detection)

### 1) Setup Virtual Environment

```powershell
cd "d:\Szabi\SZEnergy\TechTogether OpenClaw\real2sim"
py -3.12 -m venv venv
.\venv\Scripts\activate
```

If you get an execution policy error:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 2) Install Dependencies

```powershell
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

**Dependencies:**
- `mediapipe==0.10.35` - Pose detection (33 landmarks)
- `opencv-python` - Video capture & rendering
- `numpy` - Math utilities
- `mujoco>=3.0.0` - Physics simulation
- `dm-control>=1.0.0` - Control interface

### 3) Run the System

**Option A: Basic pose detection only** (no MuJoCo)

```powershell
python pose_test.py
```

Output: Live video with skeleton overlay and joint angles

**Option B: Full Real2Sim with MuJoCo simulation** (recommended)

```powershell
python real2sim.py
```

Output:
- Live video with pose skeleton
- MuJoCo window showing G1 robot mimicking your arm movements
- Console output: joint angles, confidence scores

**Option C: Test G1 robot controller** (no camera)

```powershell
python g1_controller.py
```

Output: MuJoCo simulation of oscillating robot arms (verification test)

### 4) Controls

- **Q** - Exit the program
- **Camera** - Move your arms in front of webcam

Expected output while running:

```
[real2sim] ====== Real2Sim System Starting ======
[real2sim] Initializing G1 MuJoCo simulation...
[real2sim] G1 simulation ready
[real2sim] MediaPipe initialized
[real2sim] Starting webcam capture...
[real2sim] Camera opened. Press Q to exit.
```

Then in the video window:
- Green skeleton overlays your pose
- Console shows: `left_elbow: 132.5°`, `right_elbow: 128.1°`, etc.
- MuJoCo window (if enabled): G1 robot arms mirror your movements

## System Architecture

### Flow

```
Human Pose (Camera)
       ↓ [30 FPS]
MediaPipe Pose Detection
       ↓ (33 landmarks)
Joint Angle Extraction
       ↓ (elbow, shoulder, wrist)
Real2Sim Bridge
       ↓ (angle mapping)
G1 MuJoCo Simulation
       ↓ (visual feedback)
OpenClaw Agent Interface
       ↓ (learning/control)
Agent Actions
```

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| **Pose Detection** | `pose_test.py` | MediaPipe baseline; extract 33 landmarks from camera |
| **Real2Sim Bridge** | `real2sim.py` | Main system; maps human poses to robot joints |
| **G1 Controller** | `g1_controller.py` | MuJoCo simulator; executes robot movements |
| **Integration** | `OPENCLAW_INTEGRATION.md` | OpenClaw agent connection guide |
| **OpenClaw Skill** | `skills/real2sim/SKILL.md` | Agent startup and control workflow |

## Detected Joint Angles

### MediaPipe Landmarks Used

```
Landmark 11  → Left Shoulder  (anchor point)
Landmark 13  → Left Elbow     (joint)
Landmark 15  → Left Wrist     (end effector)

Landmark 12  → Right Shoulder (anchor point)
Landmark 14  → Right Elbow    (joint)
Landmark 16  → Right Wrist    (end effector)
```

### Output Angles (in degrees)

- **left_elbow**: 0° (straight) to 180° (fully bent)
- **right_elbow**: 0° (straight) to 180° (fully bent)
- **left_shoulder_present**: visibility confidence (0.0-1.0)
- **right_shoulder_present**: visibility confidence (0.0-1.0)

### Confidence Scores

- Per-frame average visibility: 0.0 (invisible) to 1.0 (very confident)
- Filters out low-confidence detections
- Logged every 30 frames (~1 second)

## G1 Robot Model

### Current Implementation

Using **simplified humanoid placeholder** (MuJoCo XML):
- 2 arms with 3 DOF each (shoulder ball joint + elbow + wrist)
- Torso with basic inertia
- Gravity compensation for realistic movements
- ~10 DOF total (can be expanded for full G1)

### Real G1 Model

For full Unitree G1 integration:
1. Obtain `g1.mjcf` or `g1.xml` from Unitree
2. Place in `models/` directory
3. Modify `G1Humanoid.__init__()` to load it:

```python
model_path = Path(__file__).parent / "models" / "g1.mjcf"
self.robot = G1Humanoid(model_path=str(model_path))
```

## OpenClaw Integration

See **[OPENCLAW_INTEGRATION.md](OPENCLAW_INTEGRATION.md)** for:
- REST API endpoints
- OpenClaw skill examples
- Agent control interface
- Learning pipeline

The OpenClaw plugin package lives in [openclaw-real2sim-plugin](openclaw-real2sim-plugin). It exposes the first-class tools `real2sim_state` and `real2sim_command`.

### Exact OpenClaw config snippet

Add this to your OpenClaw config (`~/.openclaw/openclaw.json` on Windows at `%USERPROFILE%\\.openclaw\\openclaw.json`):

```json
{
       "plugins": {
              "entries": {
                     "real2sim": {
                            "path": "d:/Szabi/SZEnergy/TechTogether OpenClaw/real2sim/openclaw-real2sim-plugin",
                            "enabled": true,
                            "config": {
                                   "apiBaseUrl": "http://127.0.0.1:8765"
                            }
                     }
              }
       },
       "tools": {
              "allow": ["real2sim_state", "real2sim_command"]
       }
}
```

If your config already has `plugins` or `tools`, merge only the `real2sim` entry and the two tool names.

The bridge also exposes a local JSON API while it is running:

```powershell
curl http://127.0.0.1:8765/state
```

You can override the API port when starting the bridge:

```powershell
python real2sim.py --api-port 8765
```

Quick example:

```bash
# Start Real2Sim in one terminal
python real2sim.py

# In another terminal, connect OpenClaw agent
openclaw agent --message "Control the robot to mimic my arm movements"
```

## File Structure

```
real2sim/
├── pose_test.py                    # ✅ Baseline pose detection
├── real2sim.py                     # 🔄 Main Real2Sim bridge
├── g1_controller.py                # 🔄 MuJoCo G1 controller
├── requirements.txt                # Dependencies
├── README.md                       # This file
├── OPENCLAW_INTEGRATION.md         # 🔜 Agent integration guide
├── models/
│   └── pose_landmarker_heavy.task  # Auto-downloaded (30 MB)
└── venv/                           # Python 3.12 environment
```

## Troubleshooting

### Issue: Camera not found

**Solution**: Try different indices:

```python
# In real2sim.py, modify:
for index in range(0, 5):  # Try indices 0-4
```

Or check available cameras:

```powershell
python -c "import cv2; cap = cv2.VideoCapture(0); print(cap.isOpened())"
```

### Issue: MuJoCo viewer doesn't open

**Solution:**

- Windows: Usually works out-of-the-box
- Linux: May need X11 display: `export DISPLAY=:0`
- WSL2: Use `wslg` (Windows 11+) or `xvfb`

### Issue: Slow performance (low FPS)

**Solution:**

- Reduce pose detection confidence (faster but less accurate)
- Close other applications
- Use GPU acceleration if available: `pip install tensorflow-gpu`

### Issue: Import errors ("'type' object is not subscriptable")

**Solution:** Ensure Python 3.12:

```powershell
py -3.12 --version  # Should be 3.12.x
python --version    # Should also be 3.12.x in venv
```

If not, recreate venv:

```powershell
rm -r venv -Force
py -3.12 -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

## Performance Metrics

| Metric | Expected | Notes |
|--------|----------|-------|
| Pose FPS | 25-30 | Real-time webcam |
| Angle Detection | ~5ms | Per-frame latency |
| MuJoCo FPS | 100+ | Simulation framerate |
| Total Latency | ~50-100ms | Human → Robot |
| Memory | ~500-800MB | With MuJoCo simulation |

## Next Steps

### Phase 1: Baseline ✅
- [x] MediaPipe pose detection
- [x] Joint angle extraction
- [x] Display on video stream

### Phase 2: Simulation 🔄
- [ ] Full G1 MJCF model import
- [ ] Complete joint mapping (all 23 DOF)
- [ ] Gravity compensation
- [ ] Collision detection

### Phase 3: Agent Learning 🔜
- [ ] OpenClaw skill creation
- [ ] Imitation learning (BC)
- [ ] Reinforcement learning (PPO)
- [ ] Policy deployment

### Phase 4: Hardware Transfer 🔮
- [ ] Real G1 robot connection
- [ ] Sim2Real transfer
- [ ] Live robot control

## References

- **MediaPipe**: https://mediapipe.dev/ | Docs: https://developers.google.com/mediapipe
- **MuJoCo**: https://mujoco.org/ | Python API: https://mujoco.readthedocs.io/
- **OpenClaw**: https://github.com/openclaw/openclaw | Docs: https://docs.openclaw.ai/
- **Unitree G1**: https://www.unitree.com/products/g1/ | SDK: https://github.com/unitreerobotics/unitree_sdk2

## License & Attribution

- MediaPipe: Apache 2.0 (Google)
- MuJoCo: Apache 2.0 (Google DeepMind)
- OpenClaw: MIT (Community)
- This project: MIT

---

**Last Updated**: 2026-05-12  
**Python**: 3.12  
**Status**: Ready for agent development
