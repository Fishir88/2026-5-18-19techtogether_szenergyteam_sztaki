# Real2Sim: Human Motion to Robot Simulation

**Status**: ✅ Pose-to-sim loop working | ✅ Shoulder axis remap applied | ✅ OpenClaw plugin integrated

Real2Sim is a system that captures human arm movements via webcam and mimics them in a simulated Unitree G1 humanoid robot. The agent (via OpenClaw) can learn from and control the simulation.

## Quick Start

### Prerequisites

- **Python 3.12** (MuJoCo + MediaPipe require 3.9+)
- **Terminal shell** (PowerShell, bash, or zsh)
- **Webcam** (for pose detection)
- **OpenClaw** (install it if you want the agent/plugin interface)

### 1) Install OpenClaw

Install OpenClaw first if you want to use the agent interface.

If you already have it installed, `setup.ps1` will detect it and merge the local
Real2Sim plugin into your OpenClaw config automatically.

### 2) Setup Virtual Environment

```sh
cd "<PROJECT_ROOT>/real2sim"
python -m venv venv
<ACTIVATE_VENV_COMMAND>
```

If venv activation is blocked by local shell policy, allow local scripts for your current session/user and retry activation.

### 3) Install Dependencies

You can do this manually:

```powershell
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Or run the bundled setup script, which also installs the local OpenClaw plugin
dependencies and configures OpenClaw when it is installed:

```powershell
.\setup.ps1
```

**Dependencies:**
- `mediapipe==0.10.35` - Pose detection (33 landmarks)
- `opencv-python` - Video capture & rendering
- `numpy` - Math utilities
- `mujoco>=3.0.0` - Physics simulation
- `dm-control>=1.0.0` - Control interface

### 4) Run the System

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

### 5) Controls

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
       ↓ (elbow + shoulder/hip mapping)
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

### Output Angles (current behavior)

- **left_elbow**, **right_elbow**: MediaPipe elbow bend in degrees (0° to 180°)
- **left_shoulder_pitch**, **right_shoulder_pitch**: fixed to `0.0` (radians)
- **left_shoulder_roll**, **right_shoulder_roll**: derived from horizontal shoulder→elbow displacement (`dx * SHOULDER_GAIN`), clipped to `[-2.0, 2.0]` radians
- **left_hip_pitch**, **right_hip_pitch**: derived from hip→knee vertical displacement, clipped to `[-1.2, 1.2]` radians
- **left_shoulder_present**, **right_shoulder_present**: visibility confidence (0.0-1.0)

Behavior note:
- T-pose calibration mode keeps shoulder pitch constant at 0 and changes shoulder roll only.
- Wrist joints are currently locked at zero in the MuJoCo controller to prevent drift.

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

Current command surface:
- `real2sim_command` currently accepts elbow commands (`left_elbow`, `right_elbow`) through the plugin.
- Shoulder and hip values are produced by the local Real2Sim pose pipeline and applied directly in the bridge/controller path.

### Exact OpenClaw config snippet

Add this to your OpenClaw config at `<OPENCLAW_CONFIG_PATH>`
(for example: `~/.openclaw/openclaw.json`):

```json
{
       "plugins": {
              "entries": {
                     "real2sim": {
                            "path": "<PROJECT_ROOT>/real2sim/openclaw-real2sim-plugin",
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

- Ensure your environment has GUI/display access enabled for MuJoCo rendering.
- If running headless, use a virtual display solution (for example, Xvfb).

### Issue: Slow performance (low FPS)

**Solution:**

- Reduce pose detection confidence (faster but less accurate)
- Close other applications
- Use GPU acceleration if available: `pip install tensorflow-gpu`

### Issue: Import errors ("'type' object is not subscriptable")

**Solution:** Ensure Python 3.12:

```sh
py -3.12 --version  # Should be 3.12.x
python --version    # Should also be 3.12.x in venv
```

If not, recreate venv:

```sh
<REMOVE_VENV_COMMAND>
python -m venv venv
<ACTIVATE_VENV_COMMAND>
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

**Last Updated**: 2026-05-14  
**Python**: 3.12  
