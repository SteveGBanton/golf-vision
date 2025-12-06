# Task archive



# Task 1

- [x] Implement the initial repository for golf-vision.
  - Created directory structure: /scripts, /services/backend, /services/frontend
  - Backend: FastAPI app with OpenCV ArUco marker detection, WebSocket streaming
  - Frontend: Vite + React + TailwindCSS with custom useMarkerWebSocket hook
  - Orchestration: Makefile with install, backend-dev, frontend-dev targets
  - Shell scripts: setup-backend.sh, run-backend.sh, run-frontend.sh
  - To run: `make install` then `make backend-dev` and `make frontend-dev` in separate terminals
This is a comprehensive guide. Since you are new to Python/FastAPI but experienced elsewhere, I have broken this into two parts.

**Part 1** is what **you** need to do manually to prepare your machine.
**Part 2** is the specific prompt you can copy-paste to an AI Agent (like Cursor, Copilot, or ChatGPT) to generate the entire codebase structure and files for you.

**Role:** You are a Staff+ Full Stack Engineer specializing in Computer Vision and Real-time Systems plus React frontends.

**Task:** Scaffold a new repository for a Golf Swing Analyzer MVP.

**Tech Stack:**

  * **Backend:** Python 3.10+, FastAPI, OpenCV (cv2), Websockets.
  * **Frontend:** React (Vite), TailwindCSS.
  * **Orchestration:** Makefile + Bash Scripts.

**Requirements:**

1.  **Directory Structure:**
    Please create the following folder structure:

    ```text
    /golf-analyzer
      /scripts
      /services
        /backend
        /frontend
      Makefile
    ```

2.  **Backend Logic (`services/backend`):**

      * Initialize a Python FastAPI app.
      * Create a `requirements.txt` with: `fastapi`, `uvicorn[standard]`, `opencv-contrib-python`, `numpy`, `websockets`.
      * Create a `main.py`.
      * **CV Logic:** In `main.py`, create a background thread or loop that captures video from the default webcam (`cv2.VideoCapture(0)`).
      * **ArUco Detection:** Implement basic ArUco marker detection (Dictionary: `DICT_4X4_50` or `DICT_ARUCO_ORIGINAL`).
      * **Visualization:** Use `cv2.imshow` to open a local window showing the video feed with markers drawn on it.
      * **Data Transport:** If a marker is found, send a JSON payload via WebSocket to `ws://localhost:8000/ws` containing: `{"marker_id": int, "corners": list}`.
      * **Webcam Support:** Ensure the camera initializes with standard auto-exposure (do not force manual exposure yet, as the user is testing with a webcam initially).

3.  **Frontend Logic (`services/frontend`):**

      * Scaffold a Vite + React app.
      * Install `react-use-websocket` for easy connectivity.
      * Create a simple Dashboard component that connects to `ws://localhost:8000/ws`.
      * **UI:** Display a large "Status" indicator.
          * If no marker data received: Show "Searching..." (Yellow).
          * If marker data received: Show "Tracking Active" (Green) and display the raw JSON data on screen.

4.  **Orchestration (`/scripts` and `Makefile`):**

      * **`scripts/setup-backend.sh`**: Create a Python virtual environment (`venv`) inside `services/backend/venv` and install requirements.
      * **`scripts/run-backend.sh`**: Activate the venv and run the FastAPI server using `uvicorn`.
      * **`scripts/run-frontend.sh`**: Run the generic `npm run dev` command.
      * **`Makefile`**:
          * `install`: Calls the backend setup script and runs `npm install` in frontend.
          * `backend-dev`: Calls `scripts/run-backend.sh`.
          * `frontend-dev`: Calls `scripts/run-frontend.sh`.

**Output:**
Please generate the code for all necessary files, including the shell scripts, Makefile, Python backend, and React frontend components.

-----

### Implementation Details for the Agent (Reference)

Here is a guide on how the agent should generate the specific Python logic for you.

#### `services/backend/main.py`

```python
import cv2
import cv2.aruco as aruco
import asyncio
import json
import numpy as np
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

# Global flag to control the video loop
running = True

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connected")
    
    # Initialize Camera (0 is usually default webcam)
    cap = cv2.VideoCapture(0)
    
    # Setup ArUco
    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    parameters = aruco.DetectorParameters()
    detector = aruco.ArucoDetector(aruco_dict, parameters)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # 1. Process Image
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            corners, ids, rejected = detector.detectMarkers(gray)
            
            data_payload = {"status": "searching"}

            # 2. If Marker Found
            if ids is not None:
                aruco.drawDetectedMarkers(frame, corners, ids)
                
                # Simple math for MVP: Get center of first marker
                c = corners[0][0]
                center_x = float(np.mean(c[:, 0]))
                center_y = float(np.mean(c[:, 1]))
                
                data_payload = {
                    "status": "tracking",
                    "id": int(ids[0]),
                    "x": center_x,
                    "y": center_y
                }

            # 3. Show Local Video Window (For Debugging)
            cv2.imshow('Golf Analyzer Backend', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
            # 4. Send Data to React
            await websocket.send_text(json.dumps(data_payload))
            
            # Yield control to allow WebSocket to flush
            await asyncio.sleep(0.01)
            
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cap.release()
        cv2.destroyAllWindows()
```

#### `Makefile`

```makefile
.PHONY: install backend-dev frontend-dev

install:
	chmod +x scripts/*.sh
	./scripts/setup-backend.sh
	cd services/frontend && npm install

backend-dev:
	./scripts/run-backend.sh

frontend-dev:
	./scripts/run-frontend.sh
```

#### `scripts/setup-backend.sh`

```bash
#!/bin/bash
cd services/backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Virtual environment created."
fi
source venv/bin/activate
pip install -r requirements.txt
echo "Backend dependencies installed."
```

#### `scripts/run-backend.sh`

```bash
#!/bin/bash
cd services/backend
source venv/bin/activate
# Reload allows code changes without restarting
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```