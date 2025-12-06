import cv2
import cv2.aruco as aruco
import asyncio
import json
import numpy as np
from enum import Enum
from collections import deque
from dataclasses import dataclass, asdict
from typing import Optional, List, Tuple
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Allow CORS for local React dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Camera resolution
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# ArUco marker configuration
MARKER_SIZE_M = 0.030  # 30mm in meters
MARKER_SEPARATION_M = 0.005  # 5mm gap between markers

# Expected marker IDs (hardcoded)
LEFT_MARKER_ID = 18   # Left marker on the club
RIGHT_MARKER_ID = 42  # Right marker on the club

# Camera yaw angle relative to target line
CAMERA_YAW_DEGREES = 45.0

# Calibration settings
CALIBRATION_FRAMES = 10

# Impact detection settings
IMPACT_LINE_X = 0.0  # X coordinate in world space (meters)
IMPACT_VELOCITY_THRESHOLD = 0.5  # m/s

# Data buffer settings
BUFFER_SIZE = 20
FRAMES_BEFORE_IMPACT = 10
FRAMES_AFTER_IMPACT = 5

# Pose smoothing settings
SMOOTHING_ALPHA = 0.2  # EMA alpha (0.1 = very smooth, 0.5 = responsive) - lowered for stability
OUTLIER_THRESHOLD_TRANSLATION = 0.08  # 8cm jump = outlier (increased tolerance)
OUTLIER_THRESHOLD_ROTATION = 20.0  # 20 degree jump = outlier (increased tolerance)

# Marker persistence settings (prevent flickering)
MARKER_PERSISTENCE_TIME = 0.5  # Keep marker "alive" for 0.5 seconds after last seen
POSE_PERSISTENCE_TIME = 0.3   # Keep using last pose for 0.3 seconds after detection loss


# =============================================================================
# MARKER TRACKER - Persistent tracking with hysteresis
# =============================================================================

import time as time_module

class MarkerTracker:
    """
    Tracks individual markers with time-based persistence.
    Keeps markers "alive" for a period after they disappear to prevent flickering.
    """
    
    def __init__(self, persistence_time: float = MARKER_PERSISTENCE_TIME):
        self.persistence_time = persistence_time
        self.markers = {}  # marker_id -> {"corners": ..., "last_seen": timestamp}
        
    def update(self, corners: List[np.ndarray], ids: np.ndarray, current_time: float):
        """
        Update tracker with newly detected markers.
        Returns dict of all currently valid markers (detected + persisted).
        """
        # Update markers that were detected this frame
        if ids is not None:
            for i, marker_id in enumerate(ids.flatten()):
                self.markers[marker_id] = {
                    "corners": corners[i].copy(),
                    "last_seen": current_time,
                    "fresh": True  # Detected this frame
                }
        
        # Mark all as not fresh, then check persistence
        valid_markers = {}
        expired_ids = []
        
        for marker_id, data in self.markers.items():
            time_since_seen = current_time - data["last_seen"]
            
            if time_since_seen <= self.persistence_time:
                # Marker is still valid (either fresh or within persistence window)
                valid_markers[marker_id] = data
                # Mark as not fresh if it wasn't detected this frame
                if ids is None or marker_id not in ids.flatten():
                    data["fresh"] = False
            else:
                # Marker has expired
                expired_ids.append(marker_id)
        
        # Remove expired markers
        for marker_id in expired_ids:
            del self.markers[marker_id]
            
        return valid_markers
    
    def get_specific_markers(self, left_id: int, right_id: int) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], bool, bool]:
        """
        Get corners for specific marker IDs.
        Returns (left_corners, right_corners, left_fresh, right_fresh)
        """
        left_corners = None
        right_corners = None
        left_fresh = False
        right_fresh = False
        
        if left_id in self.markers:
            left_corners = self.markers[left_id]["corners"]
            left_fresh = self.markers[left_id]["fresh"]
            
        if right_id in self.markers:
            right_corners = self.markers[right_id]["corners"]
            right_fresh = self.markers[right_id]["fresh"]
            
        return left_corners, right_corners, left_fresh, right_fresh
    
    def reset(self):
        """Clear all tracked markers."""
        self.markers = {}


# =============================================================================
# POSE SMOOTHER - Stabilizes noisy detections
# =============================================================================

class PoseSmoother:
    """
    Smooths pose estimation using Exponential Moving Average (EMA) with outlier rejection.
    Uses time-based persistence to maintain stable tracking.
    """
    
    def __init__(self, alpha: float = SMOOTHING_ALPHA):
        self.alpha = alpha
        self.smoothed_tvec: Optional[np.ndarray] = None
        self.smoothed_rvec: Optional[np.ndarray] = None
        self.smoothed_euler: Optional[Tuple[float, float, float]] = None
        self.last_update_time: float = 0.0
        self.initialized = False
        
    def reset(self):
        """Reset smoother state."""
        self.smoothed_tvec = None
        self.smoothed_rvec = None
        self.smoothed_euler = None
        self.last_update_time = 0.0
        self.initialized = False
        
    def _is_outlier(self, new_tvec: np.ndarray, new_euler: Tuple[float, float, float]) -> bool:
        """Check if new measurement is an outlier (sudden jump)."""
        if not self.initialized:
            return False
            
        tvec_diff = np.linalg.norm(new_tvec - self.smoothed_tvec)
        if tvec_diff > OUTLIER_THRESHOLD_TRANSLATION:
            return True
            
        if self.smoothed_euler is not None:
            euler_diff = max(
                abs(new_euler[0] - self.smoothed_euler[0]),
                abs(new_euler[1] - self.smoothed_euler[1]),
                abs(new_euler[2] - self.smoothed_euler[2])
            )
            if euler_diff > OUTLIER_THRESHOLD_ROTATION:
                return True
                
        return False
        
    def update(self, tvec: np.ndarray, rvec: np.ndarray, current_time: float) -> Tuple[np.ndarray, np.ndarray, Tuple[float, float, float]]:
        """
        Update smoother with new pose measurement.
        Returns smoothed (tvec, rvec, euler).
        """
        self.last_update_time = current_time
        new_euler = rodrigues_to_euler(rvec)
        
        # First measurement - initialize
        if not self.initialized:
            self.smoothed_tvec = tvec.flatten().copy()
            self.smoothed_rvec = rvec.flatten().copy()
            self.smoothed_euler = new_euler
            self.initialized = True
            return self.smoothed_tvec, self.smoothed_rvec, self.smoothed_euler
            
        # Check for outliers - use higher alpha if potential real movement
        if self._is_outlier(tvec.flatten(), new_euler):
            effective_alpha = min(self.alpha * 1.5, 0.6)
        else:
            effective_alpha = self.alpha
            
        # Apply EMA smoothing
        flat_tvec = tvec.flatten()
        flat_rvec = rvec.flatten()
        
        self.smoothed_tvec = effective_alpha * flat_tvec + (1 - effective_alpha) * self.smoothed_tvec
        self.smoothed_rvec = effective_alpha * flat_rvec + (1 - effective_alpha) * self.smoothed_rvec
        
        self.smoothed_euler = (
            effective_alpha * new_euler[0] + (1 - effective_alpha) * self.smoothed_euler[0],
            effective_alpha * new_euler[1] + (1 - effective_alpha) * self.smoothed_euler[1],
            effective_alpha * new_euler[2] + (1 - effective_alpha) * self.smoothed_euler[2],
        )
        
        return self.smoothed_tvec.copy(), self.smoothed_rvec.copy(), self.smoothed_euler
        
    def get_last_pose(self, current_time: float) -> Optional[Tuple[np.ndarray, np.ndarray, Tuple[float, float, float]]]:
        """
        Return last smoothed pose if still within persistence window.
        """
        if not self.initialized:
            return None
            
        time_since_update = current_time - self.last_update_time
        if time_since_update <= POSE_PERSISTENCE_TIME:
            return self.smoothed_tvec.copy(), self.smoothed_rvec.copy(), self.smoothed_euler
        return None
    
    def is_valid(self, current_time: float) -> bool:
        """Check if smoother has valid data within persistence window."""
        if not self.initialized:
            return False
        return (current_time - self.last_update_time) <= POSE_PERSISTENCE_TIME


# =============================================================================
# PHASE 1: CAMERA INTRINSICS & 3D POSE ESTIMATION
# =============================================================================

def get_camera_intrinsics(width: int = FRAME_WIDTH, height: int = FRAME_HEIGHT) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate approximate camera matrix and distortion coefficients.
    Assumes a typical wide-angle M12 lens with center principal point.
    
    For a proper calibration, use cv2.calibrateCamera with a checkerboard.
    This is an approximation for initial testing.
    """
    # Approximate focal length for a wide-angle lens (~90 degree FOV)
    # focal_length ≈ width / (2 * tan(FOV/2))
    # For ~90 degree FOV: focal_length ≈ width / 2
    focal_length = width * 0.8  # Slightly longer for typical webcam
    
    # Principal point at image center
    cx = width / 2.0
    cy = height / 2.0
    
    # Camera matrix
    camera_matrix = np.array([
        [focal_length, 0, cx],
        [0, focal_length, cy],
        [0, 0, 1]
    ], dtype=np.float64)
    
    # Assume minimal distortion for approximation
    dist_coeffs = np.zeros((5, 1), dtype=np.float64)
    
    return camera_matrix, dist_coeffs


def estimate_pose_from_two_markers(
    left_corners: np.ndarray,
    right_corners: np.ndarray,
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    marker_size: float = MARKER_SIZE_M,
    marker_separation: float = MARKER_SEPARATION_M
) -> Tuple[bool, Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Estimate 3D pose from exactly two markers (left=18, right=42).
    Treats them as a 2x1 board layout (side by side).
    """
    if left_corners is None or right_corners is None:
        return False, None, None
    
    # Define 3D object points for a 2x1 board layout
    # Left marker at origin, right marker offset by marker_size + separation
    half_size = marker_size / 2.0
    
    # Object points for marker 18 (left, at origin)
    obj_points_left = np.array([
        [-half_size, half_size, 0],
        [half_size, half_size, 0],
        [half_size, -half_size, 0],
        [-half_size, -half_size, 0]
    ], dtype=np.float32)
    
    # Object points for marker 42 (right, offset)
    offset = marker_size + marker_separation
    obj_points_right = np.array([
        [offset - half_size, half_size, 0],
        [offset + half_size, half_size, 0],
        [offset + half_size, -half_size, 0],
        [offset - half_size, -half_size, 0]
    ], dtype=np.float32)
    
    # Combine object and image points
    obj_points = np.vstack([obj_points_left, obj_points_right])
    img_points = np.vstack([left_corners[0], right_corners[0]]).astype(np.float32)
    
    # Solve PnP
    success, rvec, tvec = cv2.solvePnP(
        obj_points, img_points, camera_matrix, dist_coeffs
    )
    
    return success, rvec, tvec


def estimate_pose_from_single_marker(
    corners: np.ndarray,
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    marker_size: float = MARKER_SIZE_M,
    is_left_marker: bool = True
) -> Tuple[bool, Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Estimate 3D pose from a single ArUco marker.
    Adjusts origin based on which marker it is.
    """
    if corners is None:
        return False, None, None
    
    half_size = marker_size / 2.0
    
    # If it's the right marker, offset the origin
    if is_left_marker:
        offset = 0.0
    else:
        offset = marker_size + MARKER_SEPARATION_M
    
    obj_points = np.array([
        [offset - half_size, half_size, 0],
        [offset + half_size, half_size, 0],
        [offset + half_size, -half_size, 0],
        [offset - half_size, -half_size, 0]
    ], dtype=np.float32)
    
    img_points = corners[0].astype(np.float32)
    
    success, rvec, tvec = cv2.solvePnP(
        obj_points, img_points, camera_matrix, dist_coeffs
    )
    
    return success, rvec, tvec


# =============================================================================
# PHASE 2: COORDINATE SYSTEM TRANSFORMATION
# =============================================================================

def get_camera_to_world_rotation() -> np.ndarray:
    """
    Create rotation matrix to transform from camera coordinates to world coordinates.
    Applies a -45 degree rotation around the Y-axis (Yaw) to align with target line.
    """
    angle_rad = np.radians(-CAMERA_YAW_DEGREES)
    
    # Rotation around Y-axis
    rotation_matrix = np.array([
        [np.cos(angle_rad), 0, np.sin(angle_rad)],
        [0, 1, 0],
        [-np.sin(angle_rad), 0, np.cos(angle_rad)]
    ], dtype=np.float64)
    
    return rotation_matrix


def rodrigues_to_euler(rvec: np.ndarray) -> Tuple[float, float, float]:
    """
    Convert Rodrigues rotation vector to Euler angles (degrees).
    Returns (pitch, yaw, roll) - also known as (X, Y, Z) rotations.
    
    Yaw = Face Angle (Open/Closed)
    Pitch = Lie Angle / Dynamic Loft
    Roll = Club rotation around shaft
    """
    # Convert Rodrigues to rotation matrix
    rotation_matrix, _ = cv2.Rodrigues(rvec)
    
    # Extract Euler angles (assuming XYZ order)
    # Using the convention: R = Rz * Ry * Rx
    sy = np.sqrt(rotation_matrix[0, 0] ** 2 + rotation_matrix[1, 0] ** 2)
    
    singular = sy < 1e-6
    
    if not singular:
        pitch = np.arctan2(rotation_matrix[2, 1], rotation_matrix[2, 2])
        yaw = np.arctan2(-rotation_matrix[2, 0], sy)
        roll = np.arctan2(rotation_matrix[1, 0], rotation_matrix[0, 0])
    else:
        pitch = np.arctan2(-rotation_matrix[1, 2], rotation_matrix[1, 1])
        yaw = np.arctan2(-rotation_matrix[2, 0], sy)
        roll = 0
    
    # Convert to degrees
    return (np.degrees(pitch), np.degrees(yaw), np.degrees(roll))


def transform_to_world_coordinates(tvec: np.ndarray, rvec: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Transform camera-relative pose to world coordinates.
    Applies the camera yaw correction.
    """
    world_rotation = get_camera_to_world_rotation()
    
    # Transform translation vector
    tvec_world = world_rotation @ tvec.flatten()
    
    # Transform rotation: combine camera-to-world rotation with marker rotation
    marker_rotation, _ = cv2.Rodrigues(rvec)
    combined_rotation = world_rotation @ marker_rotation
    rvec_world, _ = cv2.Rodrigues(combined_rotation)
    
    return tvec_world, rvec_world.flatten()


# =============================================================================
# PHASE 3: STATE MANAGEMENT & CALIBRATION
# =============================================================================

class SwingState(Enum):
    IDLE = "idle"
    CALIBRATING = "calibrating"
    READY = "ready"
    SWING_DETECTED = "swing_detected"


@dataclass
class ReferencePose:
    """Stores the calibrated reference pose (address position)."""
    tvec: np.ndarray
    rvec: np.ndarray
    euler: Tuple[float, float, float]  # pitch, yaw, roll


@dataclass
class FrameData:
    """Data for a single frame."""
    timestamp: float
    tvec: np.ndarray
    rvec: np.ndarray
    euler: Tuple[float, float, float]
    # Delta from reference (if calibrated)
    delta_x: float = 0.0
    delta_y: float = 0.0
    delta_z: float = 0.0
    face_angle: float = 0.0  # Yaw delta
    lie_angle: float = 0.0   # Pitch delta
    roll: float = 0.0        # Roll delta


class SwingAnalyzer:
    """
    Main analyzer class managing state, calibration, and swing detection.
    """
    
    def __init__(self):
        self.state = SwingState.IDLE
        self.reference_pose: Optional[ReferencePose] = None
        self.calibration_buffer: List[Tuple[np.ndarray, np.ndarray]] = []
        self.frame_buffer: deque = deque(maxlen=BUFFER_SIZE)
        self.impact_data: Optional[dict] = None
        self.last_tvec: Optional[np.ndarray] = None
        self.last_timestamp: float = 0.0
        
    def start_calibration(self):
        """Begin calibration sequence."""
        self.state = SwingState.CALIBRATING
        self.calibration_buffer = []
        self.reference_pose = None
        
    def add_calibration_frame(self, tvec: np.ndarray, rvec: np.ndarray) -> bool:
        """
        Add a frame to calibration buffer.
        Returns True if calibration is complete.
        """
        if self.state != SwingState.CALIBRATING:
            return False
            
        self.calibration_buffer.append((tvec.copy(), rvec.copy()))
        
        if len(self.calibration_buffer) >= CALIBRATION_FRAMES:
            self._finalize_calibration()
            return True
        return False
    
    def _finalize_calibration(self):
        """Average calibration frames and set reference pose."""
        tvecs = np.array([t for t, r in self.calibration_buffer])
        rvecs = np.array([r for t, r in self.calibration_buffer])
        
        avg_tvec = np.mean(tvecs, axis=0)
        avg_rvec = np.mean(rvecs, axis=0)
        
        euler = rodrigues_to_euler(avg_rvec)
        
        self.reference_pose = ReferencePose(
            tvec=avg_tvec,
            rvec=avg_rvec,
            euler=euler
        )
        self.state = SwingState.READY
        self.calibration_buffer = []
        
    def reset(self):
        """Reset to idle state."""
        self.state = SwingState.IDLE
        self.reference_pose = None
        self.calibration_buffer = []
        self.frame_buffer.clear()
        self.impact_data = None
        self.last_tvec = None
        
    def process_frame(self, tvec: np.ndarray, rvec: np.ndarray, timestamp: float) -> Optional[FrameData]:
        """
        Process a single frame and return frame data with deltas.
        """
        # Transform to world coordinates
        tvec_world, rvec_world = transform_to_world_coordinates(tvec, rvec)
        euler = rodrigues_to_euler(rvec_world)
        
        frame_data = FrameData(
            timestamp=timestamp,
            tvec=tvec_world,
            rvec=rvec_world,
            euler=euler
        )
        
        # Calculate deltas if calibrated
        if self.reference_pose is not None:
            ref_tvec_world, ref_rvec_world = transform_to_world_coordinates(
                self.reference_pose.tvec, 
                self.reference_pose.rvec
            )
            ref_euler = rodrigues_to_euler(ref_rvec_world)
            
            frame_data.delta_x = float(tvec_world[0] - ref_tvec_world[0])
            frame_data.delta_y = float(tvec_world[1] - ref_tvec_world[1])
            frame_data.delta_z = float(tvec_world[2] - ref_tvec_world[2])
            frame_data.face_angle = euler[1] - ref_euler[1]  # Yaw
            frame_data.lie_angle = euler[0] - ref_euler[0]   # Pitch
            frame_data.roll = euler[2] - ref_euler[2]        # Roll
        
        # Add to buffer
        self.frame_buffer.append(frame_data)
        
        # Check for impact (Phase 4)
        if self.state == SwingState.READY:
            if self._check_impact(tvec_world, timestamp):
                self.state = SwingState.SWING_DETECTED
                self._capture_impact_data()
        
        self.last_tvec = tvec_world
        self.last_timestamp = timestamp
        
        return frame_data
    
    # =========================================================================
    # PHASE 4: SWING TRIGGER & IMPACT DETECTION
    # =========================================================================
    
    def _check_impact(self, tvec: np.ndarray, timestamp: float) -> bool:
        """
        Check if the club has crossed the impact line with sufficient velocity.
        """
        if self.last_tvec is None:
            return False
            
        # Check if crossed impact line (X coordinate)
        crossed = (self.last_tvec[0] > IMPACT_LINE_X and tvec[0] <= IMPACT_LINE_X) or \
                  (self.last_tvec[0] < IMPACT_LINE_X and tvec[0] >= IMPACT_LINE_X)
        
        if not crossed:
            return False
            
        # Calculate velocity
        dt = timestamp - self.last_timestamp
        if dt <= 0:
            return False
            
        velocity = np.linalg.norm(tvec - self.last_tvec) / dt
        
        return velocity > IMPACT_VELOCITY_THRESHOLD
    
    def _capture_impact_data(self):
        """
        Capture frames around impact and interpolate exact impact values.
        """
        buffer_list = list(self.frame_buffer)
        
        if len(buffer_list) < 2:
            return
            
        # Find frames straddling impact line
        impact_idx = None
        for i in range(len(buffer_list) - 1):
            x1 = buffer_list[i].tvec[0]
            x2 = buffer_list[i + 1].tvec[0]
            if (x1 > IMPACT_LINE_X and x2 <= IMPACT_LINE_X) or \
               (x1 < IMPACT_LINE_X and x2 >= IMPACT_LINE_X):
                impact_idx = i
                break
        
        if impact_idx is None:
            return
            
        # Get frames before and after impact
        start_idx = max(0, impact_idx - FRAMES_BEFORE_IMPACT)
        end_idx = min(len(buffer_list), impact_idx + FRAMES_AFTER_IMPACT + 1)
        
        impact_frames = buffer_list[start_idx:end_idx]
        
        # Interpolate impact values
        frame_before = buffer_list[impact_idx]
        frame_after = buffer_list[impact_idx + 1]
        
        interpolated = self._interpolate_impact(frame_before, frame_after)
        
        self.impact_data = {
            "frames": [self._frame_to_dict(f) for f in impact_frames],
            "impact": interpolated,
            "timestamp": frame_before.timestamp
        }
    
    def _interpolate_impact(self, frame1: FrameData, frame2: FrameData) -> dict:
        """
        Linearly interpolate values at the exact impact point (X=0).
        """
        x1 = frame1.tvec[0]
        x2 = frame2.tvec[0]
        
        # Avoid division by zero
        if abs(x2 - x1) < 1e-9:
            t = 0.5
        else:
            t = (IMPACT_LINE_X - x1) / (x2 - x1)
        
        # Clamp t to [0, 1]
        t = max(0.0, min(1.0, t))
        
        return {
            "face_angle": frame1.face_angle + t * (frame2.face_angle - frame1.face_angle),
            "club_path": frame1.delta_z + t * (frame2.delta_z - frame1.delta_z),
            "attack_angle": frame1.delta_y + t * (frame2.delta_y - frame1.delta_y),
            "lie_angle": frame1.lie_angle + t * (frame2.lie_angle - frame1.lie_angle),
        }
    
    def _frame_to_dict(self, frame: FrameData) -> dict:
        """Convert FrameData to dictionary for JSON serialization."""
        return {
            "timestamp": frame.timestamp,
            "x": float(frame.tvec[0]),
            "y": float(frame.tvec[1]),
            "z": float(frame.tvec[2]),
            "face_angle": frame.face_angle,
            "lie_angle": frame.lie_angle,
            "roll": frame.roll,
            "delta_x": frame.delta_x,
            "delta_y": frame.delta_y,
            "delta_z": frame.delta_z,
        }
    
    def get_impact_data(self) -> Optional[dict]:
        """Get captured impact data and reset for next swing."""
        data = self.impact_data
        if data is not None:
            self.impact_data = None
            self.state = SwingState.READY
        return data
    
    def clear_impact(self):
        """Clear impact data and return to ready state."""
        self.impact_data = None
        if self.reference_pose is not None:
            self.state = SwingState.READY


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connected")
    print(f"Expecting markers: LEFT={LEFT_MARKER_ID}, RIGHT={RIGHT_MARKER_ID}")

    # Initialize Camera
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    # Setup ArUco
    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    parameters = aruco.DetectorParameters()
    detector = aruco.ArucoDetector(aruco_dict, parameters)
    
    # Camera intrinsics
    camera_matrix, dist_coeffs = get_camera_intrinsics()
    
    # Swing analyzer
    analyzer = SwingAnalyzer()
    
    # Marker tracker with persistence
    tracker = MarkerTracker(persistence_time=MARKER_PERSISTENCE_TIME)
    
    # Pose smoother for stable tracking
    smoother = PoseSmoother(alpha=SMOOTHING_ALPHA)
    
    # Rendering options stored in a dict so we can modify inside loop
    options = {"show_axes": True}
    
    start_time = time_module.time()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            current_time = time_module.time()
            timestamp = current_time - start_time
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Detect markers
            corners, ids, rejected = detector.detectMarkers(gray)
            
            # Update tracker with detected markers (handles persistence)
            valid_markers = tracker.update(corners, ids, current_time)
            
            # Get our specific markers (18 and 42)
            left_corners, right_corners, left_fresh, right_fresh = tracker.get_specific_markers(
                LEFT_MARKER_ID, RIGHT_MARKER_ID
            )
            
            # Count how many of our expected markers are valid
            has_left = left_corners is not None
            has_right = right_corners is not None
            num_valid = (1 if has_left else 0) + (1 if has_right else 0)
            
            # Build debug info
            raw_detected = ids.flatten().tolist() if ids is not None else []
            
            data_payload = {
                "status": "searching",
                "state": analyzer.state.value,
                "calibration_progress": len(analyzer.calibration_buffer) / CALIBRATION_FRAMES if analyzer.state == SwingState.CALIBRATING else 0,
                "show_axes": options["show_axes"],
                "debug": {
                    "markers_found": raw_detected,
                    "num_markers": num_valid,
                    "left_marker": {"id": LEFT_MARKER_ID, "detected": has_left, "fresh": left_fresh},
                    "right_marker": {"id": RIGHT_MARKER_ID, "detected": has_right, "fresh": right_fresh},
                    "pose_estimated": False,
                    "message": f"Looking for markers {LEFT_MARKER_ID} and {RIGHT_MARKER_ID}"
                }
            }

            # Draw all detected markers (raw detection)
            if ids is not None and len(ids) > 0:
                aruco.drawDetectedMarkers(frame, corners, ids)
                for i, corner in enumerate(corners):
                    c = corner[0]
                    center = (int(c[:, 0].mean()), int(c[:, 1].mean()))
                    marker_id = ids[i][0]
                    color = (0, 255, 0) if marker_id in [LEFT_MARKER_ID, RIGHT_MARKER_ID] else (0, 128, 255)
                    cv2.putText(frame, f"ID:{marker_id}", (center[0] - 20, center[1] - 20),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
            # Try to estimate pose using our tracked markers
            rvec = None
            tvec = None
            success = False
            
            try:
                if has_left and has_right:
                    # Best case: both markers available
                    success, rvec, tvec = estimate_pose_from_two_markers(
                        left_corners, right_corners, camera_matrix, dist_coeffs
                    )
                    if success:
                        status = "FRESH" if (left_fresh and right_fresh) else "PERSISTED"
                        data_payload["debug"]["message"] = f"Pose from both markers ({status})"
                elif has_left:
                    # Only left marker
                    success, rvec, tvec = estimate_pose_from_single_marker(
                        left_corners, camera_matrix, dist_coeffs, is_left_marker=True
                    )
                    if success:
                        status = "FRESH" if left_fresh else "PERSISTED"
                        data_payload["debug"]["message"] = f"Pose from marker {LEFT_MARKER_ID} only ({status})"
                elif has_right:
                    # Only right marker
                    success, rvec, tvec = estimate_pose_from_single_marker(
                        right_corners, camera_matrix, dist_coeffs, is_left_marker=False
                    )
                    if success:
                        status = "FRESH" if right_fresh else "PERSISTED"
                        data_payload["debug"]["message"] = f"Pose from marker {RIGHT_MARKER_ID} only ({status})"
                else:
                    # No markers - try to use persisted pose
                    last_pose = smoother.get_last_pose(current_time)
                    if last_pose is not None:
                        smoothed_tvec, smoothed_rvec, smoothed_euler = last_pose
                        tvec = smoothed_tvec.reshape(3, 1)
                        rvec = smoothed_rvec.reshape(3, 1)
                        success = True
                        data_payload["debug"]["message"] = "Using persisted pose (no markers visible)"
                    else:
                        data_payload["debug"]["message"] = f"No markers - show {LEFT_MARKER_ID} and {RIGHT_MARKER_ID}"
                        
            except Exception as e:
                data_payload["debug"]["message"] = f"Pose error: {str(e)}"
                success = False
            
            if success and rvec is not None and tvec is not None:
                data_payload["debug"]["pose_estimated"] = True
                
                # Apply pose smoothing (unless we're using persisted pose)
                if has_left or has_right:
                    smoothed_tvec, smoothed_rvec, smoothed_euler = smoother.update(tvec, rvec, current_time)
                    tvec = smoothed_tvec.reshape(3, 1)
                    rvec = smoothed_rvec.reshape(3, 1)
                
                # Draw 3D axes at the center of each visible marker
                if options["show_axes"]:
                    # For visualization, we need poses centered on each marker (no offset)
                    half_size = MARKER_SIZE_M / 2.0
                    obj_points_centered = np.array([
                        [-half_size, half_size, 0],
                        [half_size, half_size, 0],
                        [half_size, -half_size, 0],
                        [-half_size, -half_size, 0]
                    ], dtype=np.float32)
                    
                    # Draw axes on left marker (ID 18)
                    if has_left and left_corners is not None:
                        try:
                            img_points = left_corners[0].astype(np.float32)
                            success_l, rvec_left, tvec_left = cv2.solvePnP(
                                obj_points_centered, img_points, camera_matrix, dist_coeffs
                            )
                            if success_l:
                                cv2.drawFrameAxes(frame, camera_matrix, dist_coeffs, rvec_left, tvec_left, MARKER_SIZE_M * 0.5)
                        except:
                            pass
                    
                    # Draw axes on right marker (ID 42)
                    if has_right and right_corners is not None:
                        try:
                            img_points = right_corners[0].astype(np.float32)
                            success_r, rvec_right, tvec_right = cv2.solvePnP(
                                obj_points_centered, img_points, camera_matrix, dist_coeffs
                            )
                            if success_r:
                                cv2.drawFrameAxes(frame, camera_matrix, dist_coeffs, rvec_right, tvec_right, MARKER_SIZE_M * 0.5)
                        except:
                            pass
                
                # Handle calibration
                if analyzer.state == SwingState.CALIBRATING:
                    calibration_complete = analyzer.add_calibration_frame(tvec, rvec)
                    data_payload["calibration_progress"] = len(analyzer.calibration_buffer) / CALIBRATION_FRAMES
                    if calibration_complete:
                        data_payload["calibration_complete"] = True
                        data_payload["debug"]["message"] = "Calibration complete!"
                    else:
                        data_payload["debug"]["message"] = f"Calibrating: {len(analyzer.calibration_buffer)}/{CALIBRATION_FRAMES} frames"
                
                # Process frame
                frame_data = analyzer.process_frame(tvec, rvec, timestamp)
                
                if frame_data:
                    data_payload["status"] = "tracking"
                    data_payload["state"] = analyzer.state.value
                    data_payload["position"] = {
                        "x": float(frame_data.tvec[0]),
                        "y": float(frame_data.tvec[1]),
                        "z": float(frame_data.tvec[2]),
                    }
                    data_payload["rotation"] = {
                        "pitch": frame_data.euler[0],
                        "yaw": frame_data.euler[1],
                        "roll": frame_data.euler[2],
                    }
                    data_payload["metrics"] = {
                        "face_angle": round(frame_data.face_angle, 2),
                        "club_path": round(frame_data.delta_z * 100, 2),
                        "attack_angle": round(frame_data.delta_y * 100, 2),
                        "lie_angle": round(frame_data.lie_angle, 2),
                    }
                
                # Check for impact data
                impact = analyzer.get_impact_data()
                if impact:
                    data_payload["impact"] = impact

            # Draw state overlay
            state_color = (128, 128, 128)  # Gray for IDLE
            if analyzer.state == SwingState.CALIBRATING:
                state_color = (0, 255, 255)  # Yellow
            elif analyzer.state == SwingState.READY:
                state_color = (0, 255, 0)  # Green
            elif analyzer.state == SwingState.SWING_DETECTED:
                state_color = (255, 0, 255)  # Magenta
                
            cv2.putText(frame, f"State: {analyzer.state.value.upper()}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, state_color, 2)
            
            if analyzer.state == SwingState.CALIBRATING:
                progress = len(analyzer.calibration_buffer) / CALIBRATION_FRAMES * 100
                cv2.putText(frame, f"Calibrating: {progress:.0f}%", (10, 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            
            # Draw marker status info
            left_status = "✓" if has_left else "✗"
            right_status = "✓" if has_right else "✗"
            cv2.putText(frame, f"M{LEFT_MARKER_ID}:{left_status} M{RIGHT_MARKER_ID}:{right_status} | Raw:{raw_detected}", 
                       (10, FRAME_HEIGHT - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, data_payload["debug"]["message"], (10, FRAME_HEIGHT - 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

            # Show Local Video Window
            cv2.imshow("Golf Analyzer Backend", frame)
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord("q"):
                break
            elif key == ord("c"):
                # Manual calibration trigger (for testing without frontend)
                analyzer.start_calibration()
            elif key == ord("r"):
                # Manual reset
                analyzer.reset()

            # Handle WebSocket commands - check for pending messages
            try:
                # Use select-style check with very short timeout
                message = await asyncio.wait_for(websocket.receive_text(), timeout=0.005)
                command = json.loads(message)
                print(f"Received command: {command}")
                
                if command.get("action") == "calibrate":
                    analyzer.start_calibration()
                    smoother.reset()
                    tracker.reset()
                    print("Calibration started")
                elif command.get("action") == "reset":
                    analyzer.reset()
                    smoother.reset()
                    tracker.reset()
                    print("Reset")
                elif command.get("action") == "clear_impact":
                    analyzer.clear_impact()
                elif command.get("action") == "toggle_axes":
                    options["show_axes"] = not options["show_axes"]
                    print(f"Axes toggled: {options['show_axes']}")
                elif command.get("action") == "set_axes":
                    options["show_axes"] = command.get("value", True)
                    
            except asyncio.TimeoutError:
                pass
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")

            # Send Data to React
            await websocket.send_text(json.dumps(data_payload))
            
            # Yield control
            await asyncio.sleep(0.005)

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cap.release()
        cv2.destroyAllWindows()


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
