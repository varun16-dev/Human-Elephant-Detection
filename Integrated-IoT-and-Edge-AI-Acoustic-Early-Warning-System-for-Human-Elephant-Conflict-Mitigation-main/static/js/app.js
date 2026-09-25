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

  // Initialize Supabase Realtime if configured
  initSupabaseRealtime();
});

function initSupabaseRealtime() {
  if (!window.SUPABASE_CONFIG || !window.SUPABASE_CONFIG.url || !window.SUPABASE_CONFIG.anonKey) {
    console.warn("Supabase not configured, falling back to 4-second polling.");
    setInterval(fetchStatusAndNodes, 4000);
    return;
  }

  try {
    const supabaseUrl = window.SUPABASE_CONFIG.url;
    const supabaseKey = window.SUPABASE_CONFIG.anonKey;
    const supabase = window.supabase.createClient(supabaseUrl, supabaseKey);

    console.log("[SUPABASE] Initializing Realtime Subscriptions...");

    // Subscribe to raw_sensor_data inserts (Telemetry pushes)
    const telemetryChannel = supabase.channel('telemetry-updates')
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'raw_sensor_data' }, payload => {
        console.log("[SUPABASE REALTIME] New telemetry received:", payload.new);
        fetchStatusAndNodes();
      })
      .subscribe();

    // Subscribe to device status updates (Online/Offline)
    const deviceChannel = supabase.channel('device-updates')
      .on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'devices' }, payload => {
        console.log("[SUPABASE REALTIME] Device status updated:", payload.new);
        fetchStatusAndNodes();
      })
      .subscribe();
      
    // Subscribe to detections
    const detectionChannel = supabase.channel('detection-updates')
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'detections' }, payload => {
        console.log("[SUPABASE REALTIME] New detection received:", payload.new);
        fetchStatusAndNodes();
        
        // Trigger alerts UI if it's an elephant
        if (payload.new.detection === 'ELEPHANT_DETECTED' && payload.new.confidence >= 75) {
            if (typeof fetchDetectionHistory === 'function') {
                fetchDetectionHistory();
            }
        }
      })
      .subscribe();

    console.log("[SUPABASE] Realtime channels subscribed.");
    
    // Safety fallback polling (every 30 seconds) in case of WebSocket disconnects
    setInterval(fetchStatusAndNodes, 30000);

  } catch (err) {
    console.error("[SUPABASE] Failed to initialize Realtime:", err);
    setInterval(fetchStatusAndNodes, 4000);
  }
}

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

    const onlineCount = nodes ? nodes.filter(n => n.status !== 'OFFLINE').length : 0;
    const totalCount = nodes ? nodes.length : 0;

    const meshCount = document.getElementById('mesh-node-count');
    if (meshCount && nodes) {
      meshCount.textContent = `LoRa Mesh: ${onlineCount}/${totalCount} Online`;
    }

    const activeMeshNodes = document.getElementById('active-mesh-nodes');
    if (activeMeshNodes && nodes) {
      activeMeshNodes.innerHTML = `<i class="fa-solid fa-tower-broadcast"></i> ${onlineCount}/${totalCount} Nodes Online (LoRa)`;
    }
  })
  .catch(err => console.error("Error fetching telemetry status:", err));
}

function switchTab(tabId, updateUrl = true) {
  // Update Tab Navigation Active Class
  const tabs = document.querySelectorAll('.nav-tab');
  tabs.forEach(t => {
    t.classList.remove('active');
    const onclickAttr = t.getAttribute('onclick') || '';
    if (onclickAttr.includes(`'${tabId}'`) || onclickAttr.includes(`"${tabId}"`)) {
      t.classList.add('active');
    }
  });

  if (window.event && window.event.currentTarget && window.event.currentTarget.classList && window.event.currentTarget.classList.contains('nav-tab')) {
    tabs.forEach(t => t.classList.remove('active'));
    window.event.currentTarget.classList.add('active');
  }

  // Update Pane Display
  const panes = document.querySelectorAll('.tab-pane');
  panes.forEach(p => p.classList.remove('active'));

  const activePane = document.getElementById(tabId);
  if (activePane) activePane.classList.add('active');

  // Trigger User Management initialization if switching to user management tab
  if (tabId === 'user-mgmt-tab' && typeof initUserManagement === 'function') {
    initUserManagement();
  }

  // Update Browser URL for correct routing and refresh persistence
  if (updateUrl) {
    const tabRoutes = {
      'map-tab': '/dashboard',
      'sensor-tab': '/devices',
      'sensor-monitoring-tab': '/raw-data',
      'camera-tab': '/detections',
      'alerts-tab': '/alerts',
      'user-mgmt-tab': '/users'
    };
    
    if (tabRoutes[tabId]) {
      const currentUrl = new URL(window.location);
      // Preserve query params like ?filter=... by only updating the pathname
      if (currentUrl.pathname !== tabRoutes[tabId]) {
        currentUrl.pathname = tabRoutes[tabId];
        window.history.pushState({ tabId: tabId }, "", currentUrl.toString());
      }
    }
  }
}

// Handle browser back/forward buttons
window.addEventListener('popstate', (event) => {
  if (event.state && event.state.tabId) {
    switchTab(event.state.tabId, false);
  } else {
    // Fallback if no state
    const path = window.location.pathname;
    const routeMap = {
      '/dashboard': 'map-tab',
      '/devices': 'sensor-tab',
      '/raw-data': 'sensor-monitoring-tab',
      '/detections': 'camera-tab',
      '/elephant-images': 'camera-tab',
      '/alerts': 'alerts-tab',
      '/users': 'user-mgmt-tab'
    };
    if (routeMap[path]) {
      switchTab(routeMap[path], false);
    }
  }
});

// Auto-check for active_tab from server template on load
document.addEventListener('DOMContentLoaded', () => {
  const bodyTab = document.body ? document.body.dataset.activeTab : null;
  const targetTab = bodyTab || 'map-tab';

  if (targetTab) {
    switchTab(targetTab);
  } else if (window.location.pathname.includes('/user-management') || window.location.pathname.includes('/admin') || window.location.pathname.includes('/forest-officer/users')) {
    switchTab('user-mgmt-tab');
  }
});

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
    alert("🔧 Switched to FIELD TECHNICIAN DIAGNOSTICS VIEW: Direct telemetry and LoRa RSSI debugging.");
  }
}
