"""
Real2Sim: Human Pose to Robot Simulation Bridge

System Flow:
  Human Movement → Camera → MediaPipe → Joint Angles → G1 Simulation → OpenClaw Interface
  
This script:
1. Captures human pose using MediaPipe
2. Extracts joint angles (shoulder, elbow, hip)
3. Maps them to G1 robot joints
4. Simulates in MuJoCo
5. Exposes interface for OpenClaw agent
"""

import sys
import time
import json
import argparse
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse
import numpy as np

print(f"[real2sim] Python: {sys.executable}", flush=True)

try:
    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    print("[real2sim] MediaPipe imports successful", flush=True)
except Exception as e:
    print(f"[real2sim] FAILED to import MediaPipe: {e}", flush=True)
    sys.exit(1)

try:
    from g1_controller import G1Humanoid
    print("[real2sim] G1 controller imported successfully", flush=True)
except Exception as e:
    print(f"[real2sim] WARNING: Could not import G1 controller: {e}", flush=True)
    print("[real2sim] Running in pose-detection-only mode (no MuJoCo simulation)", flush=True)


class PoseExtractor:
    """Extract shoulder, elbow, and hip angles from MediaPipe pose landmarks."""

    SHOULDER_GAIN = 12.0
    
    # MediaPipe landmark indices
    LANDMARK_INDICES = {
        "left_shoulder": 11,
        "left_elbow": 13,
        "left_wrist": 15,
        "right_shoulder": 12,
        "right_elbow": 14,
        "right_wrist": 16,
        "left_hip": 23,
        "right_hip": 24,
        "left_knee": 25,
        "right_knee": 26,
    }
    
    @staticmethod
    def angle_between_points(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
        """
        Calculate angle at p2 between p1-p2-p3 (in degrees).
        Uses atan2 for robust angle calculation.
        """
        a = np.array(p1)
        b = np.array(p2)
        c = np.array(p3)
        
        radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
        ang = np.abs(radians * 180.0 / np.pi)
        
        return 360 - ang if ang > 180 else ang
    
    @staticmethod
    def extract_angles(landmarks) -> Dict[str, Optional[float]]:
        """
        Extract joint angles from MediaPipe landmarks.
        
        Returns:
            Dict with keys: left_elbow, right_elbow, left_shoulder, right_shoulder, etc.
        """
        if not landmarks or len(landmarks) < 27:
            return {}
        
        angles = {}
        
        try:
            # Get 2D positions (x, y)
            ls = landmarks[PoseExtractor.LANDMARK_INDICES["left_shoulder"]]
            le = landmarks[PoseExtractor.LANDMARK_INDICES["left_elbow"]]
            lw = landmarks[PoseExtractor.LANDMARK_INDICES["left_wrist"]]
            
            rs = landmarks[PoseExtractor.LANDMARK_INDICES["right_shoulder"]]
            re = landmarks[PoseExtractor.LANDMARK_INDICES["right_elbow"]]
            rw = landmarks[PoseExtractor.LANDMARK_INDICES["right_wrist"]]
            
            # Calculate angles
            angles["left_elbow"] = PoseExtractor.angle_between_points(
                [ls.x, ls.y], [le.x, le.y], [lw.x, lw.y]
            )
            angles["right_elbow"] = PoseExtractor.angle_between_points(
                [rs.x, rs.y], [re.x, re.y], [rw.x, rw.y]
            )

            # Shoulder mapping from shoulder->elbow vector (radians, heuristic).
            # Right shoulder signs are intentionally mirrored to match G1 joint axes.
            left_dx = le.x - ls.x
            left_dy = le.y - ls.y
            right_dx = re.x - rs.x
            right_dy = re.y - rs.y
            gain = PoseExtractor.SHOULDER_GAIN
            # New mapping: keep pitch constant (0) and map horizontal displacement to roll.
            # This makes neutral pitch = 0 and T-pose changes affect roll only.
            angles["left_shoulder_pitch"] = 0.0
            angles["left_shoulder_roll"] = float(np.clip(left_dx * gain, -2.0, 2.0))
            angles["right_shoulder_pitch"] = 0.0
            angles["right_shoulder_roll"] = float(np.clip(right_dx * gain, -2.0, 2.0))

            # Optional hip pitch from hip->knee vector; used when model has hip joints.
            lh = landmarks[PoseExtractor.LANDMARK_INDICES["left_hip"]]
            rh = landmarks[PoseExtractor.LANDMARK_INDICES["right_hip"]]
            lk = landmarks[PoseExtractor.LANDMARK_INDICES["left_knee"]]
            rk = landmarks[PoseExtractor.LANDMARK_INDICES["right_knee"]]
            angles["left_hip_pitch"] = float(np.clip(-(lk.y - lh.y) * 2.5, -1.2, 1.2))
            angles["right_hip_pitch"] = float(np.clip(-(rk.y - rh.y) * 2.5, -1.2, 1.2))
            
            # Optional: shoulder angles (more complex, requires 3D)
            # For now, just track presence
            angles["left_shoulder_present"] = ls.visibility > 0.5
            angles["right_shoulder_present"] = rs.visibility > 0.5
            
        except Exception as e:
            print(f"[real2sim] Error extracting angles: {e}", flush=True)
        
        return angles


class Real2SimSystem:
    """Unified Real2Sim system: Pose → Simulation → Output."""
    
    def __init__(self, use_mujoco: bool = True):
        """
        Initialize Real2Sim system.
        
        Args:
            use_mujoco: If True, initialize G1 simulation; if False, pose detection only
        """
        print("[real2sim] Initializing Real2Sim system...", flush=True)
        
        self.use_mujoco = use_mujoco
        self.robot = None
        self.pose_extractor = PoseExtractor()
        self.current_angles = {}
        self.last_command = {}
        self.frame_count = 0
        self.lock = threading.Lock()
        self.api_server = None
        self.api_thread = None
        
        # Initialize MuJoCo if requested
        if use_mujoco:
            try:
                print("[real2sim] Initializing G1 MuJoCo simulation...", flush=True)
                self.robot = G1Humanoid()
                print("[real2sim] G1 simulation ready", flush=True)
            except Exception as e:
                print(f"[real2sim] WARNING: MuJoCo init failed: {e}", flush=True)
                print("[real2sim] Continuing with pose-only mode", flush=True)
                self.use_mujoco = False
        
        # Initialize MediaPipe
        self._init_mediapipe()

    def _snapshot_state(self) -> Dict:
        with self.lock:
            return {
                "frame_id": self.frame_count,
                "angles": dict(self.current_angles),
                "last_command": dict(self.last_command),
                "robot_active": self.use_mujoco and self.robot is not None,
                "timestamp": int(time.time() * 1000),
            }

    def start_api_server(self, port: int = 8765):
        """Start a small JSON API for OpenClaw or local tooling."""
        if self.api_server is not None:
            return

        system = self

        class ApiHandler(BaseHTTPRequestHandler):
            def _write_json(self, status: int, payload: Dict):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

            def do_GET(self):
                route = urlparse(self.path).path
                if route == "/health":
                    self._write_json(200, {"ok": True, **system._snapshot_state()})
                    return
                if route == "/state":
                    self._write_json(200, system._snapshot_state())
                    return
                self._write_json(404, {"ok": False, "error": "not found"})

            def do_POST(self):
                route = urlparse(self.path).path
                if route != "/command":
                    self._write_json(404, {"ok": False, "error": "not found"})
                    return

                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(length) if length > 0 else b"{}"
                    payload = json.loads(raw.decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError("command body must be a JSON object")
                except Exception as exc:
                    self._write_json(400, {"ok": False, "error": str(exc)})
                    return

                system.apply_command(payload)
                self._write_json(200, {"ok": True, **system._snapshot_state()})

        self.api_server = ThreadingHTTPServer(("127.0.0.1", port), ApiHandler)
        self.api_thread = threading.Thread(target=self.api_server.serve_forever, daemon=True)
        self.api_thread.start()
        print(f"[real2sim] OpenClaw API listening on http://127.0.0.1:{port}", flush=True)

    def apply_command(self, command: Dict):
        """Apply a robot command received from the OpenClaw API."""
        with self.lock:
            self.last_command = dict(command)

        if self.use_mujoco and self.robot:
            try:
                self.robot.set_arm_pose(
                    left_shoulder_pitch=command.get("left_shoulder_pitch"),
                    left_shoulder_roll=command.get("left_shoulder_roll"),
                    left_elbow=command.get("left_elbow"),
                    right_elbow=command.get("right_elbow"),
                    right_shoulder_pitch=command.get("right_shoulder_pitch"),
                    right_shoulder_roll=command.get("right_shoulder_roll"),
                    left_hip_pitch=command.get("left_hip_pitch"),
                    right_hip_pitch=command.get("right_hip_pitch"),
                )
            except Exception as e:
                print(f"[real2sim] Error applying command: {e}", flush=True)
    
    def _init_mediapipe(self):
        """Initialize MediaPipe pose detector."""
        try:
            print("[real2sim] Initializing MediaPipe pose detection...", flush=True)
            
            MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task"
            MODEL_PATH = Path(__file__).resolve().parent / "models" / "pose_landmarker_heavy.task"
            
            # Download model if needed
            MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            if not MODEL_PATH.exists():
                print(f"[real2sim] Downloading model from {MODEL_URL}...", flush=True)
                from urllib.request import urlretrieve
                urlretrieve(MODEL_URL, MODEL_PATH)
            
            # Create PoseLandmarker
            base_options = python.BaseOptions(model_asset_path=str(MODEL_PATH))
            options = vision.PoseLandmarkerOptions(
                base_options=base_options,
                running_mode=vision.RunningMode.VIDEO,
                num_poses=1,
            )
            self.landmarker = vision.PoseLandmarker.create_from_options(options)
            print("[real2sim] MediaPipe initialized", flush=True)
        
        except Exception as e:
            print(f"[real2sim] ERROR: Failed to initialize MediaPipe: {e}", flush=True)
            raise
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Process a single video frame.
        
        Args:
            frame: BGR frame from camera
        
        Returns:
            Dict with detected angles and visualization data
        """
        try:
            # Convert BGR → RGB
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            
            # Detect pose
            timestamp_ms = int(time.time() * 1000)
            result = self.landmarker.detect_for_video(mp_image, timestamp_ms)
            
            output = {
                "frame_id": self.frame_count,
                "timestamp": timestamp_ms,
                "pose_detected": False,
                "angles": {},
                "confidence": 0,
            }
            
            if result.pose_landmarks:
                landmarks = result.pose_landmarks[0]
                
                # Extract angles
                angles = self.pose_extractor.extract_angles(landmarks)
                
                with self.lock:
                    self.current_angles = angles
                
                output["pose_detected"] = True
                output["angles"] = angles
                output["confidence"] = np.mean([lm.visibility for lm in landmarks])
                
                # Send to robot if available
                if self.use_mujoco and self.robot:
                    try:
                        self.robot.set_arm_pose(
                            left_shoulder_pitch=angles.get("left_shoulder_pitch"),
                            left_shoulder_roll=angles.get("left_shoulder_roll"),
                            left_elbow=angles.get("left_elbow"),
                            right_shoulder_pitch=angles.get("right_shoulder_pitch"),
                            right_shoulder_roll=angles.get("right_shoulder_roll"),
                            right_elbow=angles.get("right_elbow"),
                            left_hip_pitch=angles.get("left_hip_pitch"),
                            right_hip_pitch=angles.get("right_hip_pitch"),
                        )
                        self.robot.step()
                        self.robot.render(show_viewer=True)
                    except Exception as e:
                        print(f"[real2sim] Error updating robot: {e}", flush=True)
                
                # Draw skeleton on frame
                output["frame"] = self._draw_skeleton(frame, landmarks)
            else:
                output["frame"] = frame
            
            self.frame_count += 1
            return output
        
        except Exception as e:
            print(f"[real2sim] Error processing frame: {e}", flush=True)
            return {"frame": frame, "error": str(e)}
    
    @staticmethod
    def _draw_skeleton(frame: np.ndarray, landmarks) -> np.ndarray:
        """Draw pose skeleton on frame."""
        try:
            h, w, _ = frame.shape
            
            # Draw landmarks
            for landmark in landmarks:
                x = int(landmark.x * w)
                y = int(landmark.y * h)
                if 0 <= x < w and 0 <= y < h:
                    cv2.circle(frame, (x, y), 4, (0, 255, 0), -1)
            
            # Draw connections (mediapipe standard pose connections)
            connections = [
                (11, 13), (13, 15),  # Left arm
                (12, 14), (14, 16),  # Right arm
                (11, 12),            # Shoulders
            ]
            
            for start, end in connections:
                if start < len(landmarks) and end < len(landmarks):
                    p1 = landmarks[start]
                    p2 = landmarks[end]
                    x1, y1 = int(p1.x * w), int(p1.y * h)
                    x2, y2 = int(p2.x * w), int(p2.y * h)
                    if all(0 <= c < (w if i % 2 == 0 else h) for i, c in enumerate([x1, y1, x2, y2])):
                        cv2.line(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        except Exception as e:
            print(f"[real2sim] Error drawing skeleton: {e}", flush=True)
        
        return frame
    
    def run_webcam(self):
        """Run real-time webcam capture and processing."""
        print("[real2sim] Starting webcam capture...", flush=True)
        
        # Open camera
        capture = cv2.VideoCapture(0)
        if not capture.isOpened():
            print("[real2sim] ERROR: Could not open camera", flush=True)
            return 1
        
        print("[real2sim] Camera opened. Press Q to exit.", flush=True)
        
        try:
            while True:
                success, frame = capture.read()
                if not success:
                    break
                
                # Process frame
                result = self.process_frame(frame)
                
                # Display results
                if "frame" in result:
                    display_frame = result["frame"].copy()
                    
                    # Add angle text
                    y_offset = 30
                    if result.get("angles"):
                        for angle_name, angle_val in result["angles"].items():
                            if isinstance(angle_val, (int, float)):
                                cv2.putText(display_frame, f"{angle_name}: {angle_val:.1f}°",
                                          (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                                y_offset += 25
                    
                    cv2.imshow("Real2Sim - Pose Tracking", display_frame)
                
                # Check for exit
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("[real2sim] User pressed Q, exiting...", flush=True)
                    break
                
                # Log every 30 frames
                if self.frame_count % 30 == 0:
                    angles_str = json.dumps(self.current_angles, default=str, indent=2)
                    print(f"[real2sim] Frame {self.frame_count}: {angles_str[:100]}...", flush=True)
        
        except Exception as e:
            print(f"[real2sim] Error in webcam loop: {e}", flush=True)
            return 1
        
        finally:
            capture.release()
            cv2.destroyAllWindows()
            if self.robot:
                self.robot.close()
            if self.api_server is not None:
                self.api_server.shutdown()
                self.api_server.server_close()
        
        return 0
    
    def get_state_json(self) -> str:
        """Get current system state as JSON (for OpenClaw integration)."""
        with self.lock:
            state = {
                "frame_id": self.frame_count,
                "angles": self.current_angles,
                "robot_active": self.use_mujoco and self.robot is not None,
            }
        return json.dumps(state)


def main():
    """Main entry point."""
    print("[real2sim] ====== Real2Sim System Starting ======", flush=True)
    
    try:
        parser = argparse.ArgumentParser(description="Real2Sim human pose to robot bridge")
        parser.add_argument("--no-mujoco", action="store_true", help="Run pose detection without MuJoCo")
        parser.add_argument("--api-port", type=int, default=8765, help="Local JSON API port")
        args = parser.parse_args()

        # Initialize system (with MuJoCo if available)
        system = Real2SimSystem(use_mujoco=not args.no_mujoco)
        system.start_api_server(args.api_port)
        
        # Run webcam capture and processing
        exit_code = system.run_webcam()
        
        print("[real2sim] ====== Real2Sim System Shutdown ======", flush=True)
        return exit_code
    
    except Exception as e:
        print(f"[real2sim] FATAL ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    print(f"[real2sim] Exiting with code {exit_code}", flush=True)
    sys.exit(exit_code)
