/**
 * Master Application Controller & State Manager
 * Integrated IoT and Edge-AI Acoustic Early Warning System
 */

document.addEventListener('DOMContentLoaded', () => {
  console.log("Master Application Initializing...");

  // Initial Data Fetch & Module Initialization
  fetchStatusAndNodes();
  fetchDSSRecommendations();
  initAudioDSP();

  // Periodic Telemetry Polling (Every 4 seconds)
  setInterval(() => {
    fetchStatusAndNodes();
  }, 4000);
});

function fetchStatusAndNodes() {
  Promise.all([
    fetch('/api/status').then(res => res.json()),
    fetch('/api/nodes').then(res => res.json())
  ])
  .then(([status, nodes]) => {
    // Render Sensor Nodes Grid
    renderSensorNodes(nodes);

    // Update Real-Time Edge-AI Acoustic Display & Geotargeted Alert Trigger
    if (typeof updateEdgeAIDisplayFromNodes === 'function') {
      updateEdgeAIDisplayFromNodes(nodes);
    }

    // Initialize GIS Map if not already initialized
    if (!window.mapInitialized) {
      initGISMap(nodes, status.herd_info);
      window.mapInitialized = true;
    } else if (typeof updateMapNodes === 'function') {
      updateMapNodes(nodes, status.herd_info);
    }

    // Update Header Status Indicator
    const dot = document.getElementById('header-status-dot');
    const text = document.getElementById('header-status-text');

    if (dot && text) {
      if (status.overall_status === 'CRITICAL_ALERT') {
        dot.className = 'dot-indicator alert-pulse';
        text.textContent = 'CRITICAL THREAT DETECTED';
      } else if (status.overall_status === 'WARNING') {
        dot.className = 'dot-indicator active-pulse';
        dot.style.background = '#f59e0b';
        text.textContent = 'WARNING: ELEPHANT NEAR FRINGE';
      } else {
        dot.className = 'dot-indicator active-pulse';
        dot.style.background = '#10b981';
        text.textContent = 'SYSTEM NORMAL - ALL CLEAR';
      }
    }
  })
  .catch(err => console.error("Error fetching telemetry status:", err));
}

function switchTab(tabId) {
  // Update Tab Navigation Active Class
  const tabs = document.querySelectorAll('.nav-tab');
  tabs.forEach(t => t.classList.remove('active'));
  event.currentTarget.classList.add('active');

  // Update Pane Display
  const panes = document.querySelectorAll('.tab-pane');
  panes.forEach(p => p.classList.remove('active'));

  const activePane = document.getElementById(tabId);
  if (activePane) activePane.classList.add('active');
}

function switchRole(role) {
  const btns = document.querySelectorAll('.role-btn');
  btns.forEach(b => b.classList.remove('active'));
  event.currentTarget.classList.add('active');

  const emergencyBanner = document.getElementById('emergency-banner');

  if (role === 'farmer') {
    switchTab('map-tab');
    if (emergencyBanner) {
      emergencyBanner.style.background = 'linear-gradient(135deg, rgba(245, 158, 11, 0.25), rgba(180, 83, 9, 0.15))';
      emergencyBanner.style.borderColor = '#f59e0b';
    }
    alert("👨‍🌾 Switched to FARMER / RESIDENT VIEW: Optimized for simple emergency alerts and safe corridor guidance.");
  } else if (role === 'official') {
    switchTab('map-tab');
    alert("🛡️ Switched to FOREST OFFICIAL CONTROL ROOM VIEW: Full access to deterrent manual overrides and patrol dispatch.");
  } else if (role === 'technician') {
    switchTab('sensor-tab');
    alert("🔧 Switched to FIELD TECHNICIAN DIAGNOSTICS VIEW: Direct telemetry, solar voltage, and LoRa RSSI debugging.");
  }
}
