// ======================
// KIRTI Live Session Logic
// ======================

const API_BASE = "http://localhost:8000";  // Backend address

// Get all important elements
const cameraFeed = document.getElementById("camera-feed");
const cameraStatus = document.getElementById("camera-status");
const liveScore = document.getElementById("live-score");
const scoreUnit = document.getElementById("score-unit");
const sessionStatus = document.getElementById("session-status");
const testTypeText = document.getElementById("test-type");
const athleteNameText = document.getElementById("athlete-name");

const btnStart = document.getElementById("btn-start");
const btnReset = document.getElementById("btn-reset");
const btnStop = document.getElementById("btn-stop");

const params = new URLSearchParams(window.location.search);

let currentTest = params.get("test") || "situp";
let athleteId = params.get("athlete");

let currentAthlete = "Unknown Athlete";

// Update test information
testTypeText.textContent =
  currentTest === "situp" ? "Sit-ups" : "Vertical Jump";

scoreUnit.textContent =
  currentTest === "situp" ? "reps" : "cm";

// Load the actual athlete name
async function loadAthlete() {
  try {
    const response = await fetch(`${API_BASE}/api/athletes`);

    if (!response.ok) {
      throw new Error("Failed to load athletes");
    }

    const athletes = await response.json();

    const athlete = athletes.find(a => a.id === athleteId);

    if (athlete) {
      currentAthlete = athlete.name;
      athleteNameText.textContent = athlete.name;
    } else {
      athleteNameText.textContent = "Unknown Athlete";
    }

  } catch (error) {
    console.error("Error loading athlete:", error);
    athleteNameText.textContent = "Unable to load athlete";
  }
}

loadAthlete();

// ======================
// Button Events
// ======================

btnStart.addEventListener("click", startSession);
btnReset.addEventListener("click", resetSession);
btnStop.addEventListener("click", stopSession);

// ======================
// Functions
// ======================

async function startSession() {
  try {
    sessionStatus.textContent = "Starting...";
    
    const response = await fetch(`${API_BASE}/api/session/start`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        test_type: currentTest
      })
    });

    if (!response.ok) {
      throw new Error("Failed to start session");
    }

    sessionStatus.textContent = "Session Running";
    cameraStatus.textContent = "Camera is live";
    
    // Start polling for live data
    startPolling();

  } catch (error) {
    console.error(error);
    sessionStatus.textContent = "Error starting session";
    alert("Could not start session. Make sure the backend is running on port 8000.");
  }
}

async function resetSession() {
  try {
    await fetch(`${API_BASE}/api/session/reset`, {
      method: "POST"
    });
    
    liveScore.textContent = "0";
    sessionStatus.textContent = "Reset done";
  } catch (error) {
    console.error(error);
  }
}

async function stopSession() {
  try {
    await fetch(`${API_BASE}/api/session/stop`, {
      method: "POST"
    });

    stopPolling();

    sessionStatus.textContent = "Session Stopped";
    cameraStatus.textContent = "Camera is off";
    cameraFeed.src = "";

    // Go to result page with the selected athlete and test
    window.location.href =
      `result.html?athlete=${athleteId}&test=${currentTest}`;

  } catch (error) {
    console.error(error);
  }
}

// ======================
// Live Polling
// ======================

let pollingInterval = null;

function startPolling() {
  // Clear any existing interval
  if (pollingInterval) clearInterval(pollingInterval);

  pollingInterval = setInterval(async () => {
    try {
      // Get latest frame
      const frameRes = await fetch(`${API_BASE}/api/session/frame`);
      const frameData = await frameRes.json();
      
      if (frameData.frame) {
        cameraFeed.src = `data:image/jpeg;base64,${frameData.frame}`;
      }

      // Get latest status
      const statusRes = await fetch(`${API_BASE}/api/session/status`);
      const statusData = await statusRes.json();

      // Update score
      if (currentTest === "situp") {
        liveScore.textContent = statusData.rep_count || 0;
      } else {
        liveScore.textContent = statusData.height_cm ? statusData.height_cm.toFixed(1) : "0";
      }

      // Update status text
      if (statusData.state) {
        sessionStatus.textContent = statusData.state;
      }

    } catch (error) {
      console.error("Polling error:", error);
    }
  }, 150); // Update every 150ms
}

function stopPolling() {
  if (pollingInterval) {
    clearInterval(pollingInterval);
    pollingInterval = null;
  }
}