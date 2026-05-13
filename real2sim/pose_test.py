from pathlib import Path
from urllib.request import urlretrieve
import sys
import time

print(f"[pose_test] Python executable: {sys.executable}", flush=True)
print(f"[pose_test] Python version: {sys.version}", flush=True)

try:
    print("[pose_test] Importing cv2...", flush=True)
    import cv2
    print("[pose_test] cv2 imported successfully", flush=True)
except Exception as e:
    print(f"[pose_test] FAILED to import cv2: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    print("[pose_test] Importing mediapipe...", flush=True)
    import mediapipe as mp
    print("[pose_test] mediapipe imported successfully", flush=True)
except Exception as e:
    print(f"[pose_test] FAILED to import mediapipe: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    print("[pose_test] Importing numpy...", flush=True)
    import numpy as np
    print("[pose_test] numpy imported successfully", flush=True)
except Exception as e:
    print(f"[pose_test] FAILED to import numpy: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    print("[pose_test] Importing mediapipe.tasks.python...", flush=True)
    from mediapipe.tasks import python
    print("[pose_test] mediapipe.tasks.python imported successfully", flush=True)
except Exception as e:
    print(f"[pose_test] FAILED to import mediapipe.tasks.python: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    print("[pose_test] Importing mediapipe.tasks.python.vision...", flush=True)
    from mediapipe.tasks.python import vision
    print("[pose_test] mediapipe.tasks.python.vision imported successfully", flush=True)
except Exception as e:
    print(f"[pose_test] FAILED to import mediapipe.tasks.python.vision: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("[pose_test] All imports successful", flush=True)

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task"
MODEL_PATH = Path(__file__).resolve().parent / "models" / "pose_landmarker_heavy.task"


def ensure_model() -> Path:
    try:
        print(f"[pose_test] Ensuring model directory: {MODEL_PATH.parent}", flush=True)
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"[pose_test] Model directory ready", flush=True)
        
        if not MODEL_PATH.exists():
            print(f"[pose_test] Model not found, downloading from {MODEL_URL}", flush=True)
            urlretrieve(MODEL_URL, MODEL_PATH)
            print(f"[pose_test] Model downloaded successfully to {MODEL_PATH}", flush=True)
        else:
            size_mb = MODEL_PATH.stat().st_size / 1024 / 1024
            print(f"[pose_test] Model already exists ({size_mb:.1f} MB): {MODEL_PATH}", flush=True)
        return MODEL_PATH
    except Exception as e:
        print(f"[pose_test] ERROR in ensure_model: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise


def angle(a, b, c):
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)
    radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
    ang = np.abs(radians * 180.0 / np.pi)
    if ang > 180:
        ang = 360 - ang
    return ang


def open_camera():
    print("[pose_test] Attempting to open camera...", flush=True)
    for index in range(0, 5):
        try:
            print(f"[pose_test]   Trying camera index {index}...", flush=True)
            capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if capture.isOpened():
                print(f"[pose_test] ✓ Camera opened (index {index})", flush=True)
                return capture
            else:
                print(f"[pose_test]   Camera index {index} not available", flush=True)
            capture.release()
        except Exception as e:
            print(f"[pose_test]   Error trying index {index}: {e}", flush=True)
    return None


def main():
    try:
        print("[pose_test] ====== STARTING MAIN ======", flush=True)
        
        print("[pose_test] Step 1: Ensuring model...", flush=True)
        model_path = ensure_model()
        print(f"[pose_test] Model path confirmed: {model_path}", flush=True)
        
        print("[pose_test] Step 2: Creating BaseOptions...", flush=True)
        base_options = python.BaseOptions(model_asset_path=str(model_path))
        print("[pose_test] BaseOptions created", flush=True)
        
        print("[pose_test] Step 3: Creating PoseLandmarkerOptions...", flush=True)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        print("[pose_test] PoseLandmarkerOptions created", flush=True)

        print("[pose_test] Step 4: Opening camera...", flush=True)
        capture = open_camera()
        if capture is None:
            print("[pose_test] ERROR: Could not open any camera. Exiting.", flush=True)
            return 1
        print("[pose_test] Camera opened successfully", flush=True)

        print("[pose_test] Step 5: Configuring camera buffer...", flush=True)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        print("[pose_test] Camera buffer configured", flush=True)

        print("[pose_test] Step 6: Creating PoseLandmarker...", flush=True)
        landmarker = vision.PoseLandmarker.create_from_options(options)
        print("[pose_test] PoseLandmarker created successfully", flush=True)
        
        print("[pose_test] Step 7: Entering main loop (press Q to exit)...", flush=True)
        frame_count = 0
        while True:
            try:
                success, frame = capture.read()
                if not success:
                    print("[pose_test] Frame read failed. Exiting loop.", flush=True)
                    break

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                timestamp_ms = int(time.time() * 1000)
                result = landmarker.detect_for_video(mp_image, timestamp_ms)

                if result.pose_landmarks:
                    landmarks = result.pose_landmarks[0]
                    h, w, _ = frame.shape
                    ls = landmarks[11]
                    le = landmarks[13]
                    lw = landmarks[15]
                    shoulder = [ls.x * w, ls.y * h]
                    elbow = [le.x * w, le.y * h]
                    wrist = [lw.x * w, lw.y * h]
                    elbow_angle = angle(shoulder, elbow, wrist)
                    cv2.putText(
                        frame,
                        f"Left Elbow: {int(elbow_angle)}",
                        (50, 50),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1,
                        (0, 255, 0),
                        2,
                    )

                    for landmark in landmarks:
                        cx = int(landmark.x * w)
                        cy = int(landmark.y * h)
                        cv2.circle(frame, (cx, cy), 4, (255, 0, 0), -1)

                cv2.imshow("Pose Tracking", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("[pose_test] User pressed Q, exiting.", flush=True)
                    break
                    
                frame_count += 1
                if frame_count % 30 == 0:
                    print(f"[pose_test] Processed {frame_count} frames", flush=True)
                    
            except Exception as e:
                print(f"[pose_test] ERROR in frame loop: {e}", flush=True)
                import traceback
                traceback.print_exc()
                break

        print("[pose_test] Cleaning up...", flush=True)
        landmarker.close()
        capture.release()
        cv2.destroyAllWindows()
        print("[pose_test] ====== DEMO FINISHED SUCCESSFULLY ======", flush=True)
        return 0
        
    except Exception as e:
        print(f"[pose_test] FATAL ERROR in main: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    print(f"[pose_test] Exiting with code {exit_code}", flush=True)
    sys.exit(exit_code)
