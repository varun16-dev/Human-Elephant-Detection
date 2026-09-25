// Sensor Monitoring Module - Exact Reference Design Implementation

let selectedMonitoringNode = 'ESP32-NODE-01';
const smUrlParams = new URLSearchParams(window.location.search);
if (smUrlParams.has('device')) {
    selectedMonitoringNode = smUrlParams.get('device');
}

window.switchMonitoringNode = function(nodeId) {
    if (selectedMonitoringNode === nodeId) return;
    selectedMonitoringNode = nodeId;
    console.log(`[MONITORING] Switched target node to: ${nodeId}`);
    
    // Update URL parameter
    const url = new URL(window.location);
    url.searchParams.set('device', nodeId);
    window.history.replaceState(window.history.state, '', url);
    
    // Update button states
    const btn1 = document.getElementById('mon-btn-node-1');
    const btn2 = document.getElementById('mon-btn-node-2');
    const badge = document.getElementById('selected-node-indicator');
    const testBtn = document.getElementById('node-test-transmit-btn');
    
    if (nodeId === 'ESP32-NODE-01') {
        if (btn1) {
            btn1.style.background = 'rgba(16, 185, 129, 0.2)';
            btn1.style.borderColor = '#10b981';
            btn1.style.color = '#10b981';
        }
        if (btn2) {
            btn2.style.background = 'rgba(148, 163, 184, 0.08)';
            btn2.style.borderColor = 'rgba(148, 163, 184, 0.25)';
            btn2.style.color = '#94a3b8';
        }
        if (badge) {
            badge.innerHTML = '<i class="fa-solid fa-satellite-dish"></i> ESP32-NODE-01 (Buthanahalli)';
            badge.style.color = '#10b981';
            badge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
            badge.style.background = 'rgba(16, 185, 129, 0.15)';
        }
        if (testBtn) testBtn.style.display = 'none';
    } else {
        if (btn2) {
            btn2.style.background = 'rgba(56, 189, 248, 0.2)';
            btn2.style.borderColor = '#38bdf8';
            btn2.style.color = '#38bdf8';
        }
        if (btn1) {
            btn1.style.background = 'rgba(148, 163, 184, 0.08)';
            btn1.style.borderColor = 'rgba(148, 163, 184, 0.25)';
            btn1.style.color = '#94a3b8';
        }
        if (badge) {
            badge.innerHTML = '<i class="fa-solid fa-satellite-dish"></i> ESP32-NODE-02 (Begihalli)';
            badge.style.color = '#38bdf8';
            badge.style.borderColor = 'rgba(56, 189, 248, 0.3)';
            badge.style.background = 'rgba(56, 189, 248, 0.15)';
        }
        if (testBtn) testBtn.style.display = 'inline-flex';
    }
    
    updateSensorStatus();
    loadChartData();
    loadRawData();
};

let sensorChart = null;
let currentSensorType = 'pir';
let updateInterval = null;
let esp32Online = true;
let autoRefreshEnabled = true;
let lastUpdateTime = null;
const AUTO_REFRESH_INTERVAL = 2000; // 2 seconds

// Raw Data Pagination
let rawDataCurrentPage = 1;
let rawDataPerPage = 20;
let rawDataFiltered = [];
let rawDataDateFilter = null;

let lastSuspiciousAlertTime = 0;

function triggerSuspiciousPopup(pirVal, soundVal) {
    const now = Date.now();
    if (now - lastSuspiciousAlertTime < 15000) return; // 15s cooldown
    lastSuspiciousAlertTime = now;
    
    if (document.getElementById('suspicious-activity-popup')) {
        document.getElementById('suspicious-activity-popup').remove();
    }
    
    const popup = document.createElement('div');
    popup.id = 'suspicious-activity-popup';
    popup.style.position = 'fixed';
    popup.style.top = '25px';
    popup.style.right = '25px';
    popup.style.background = 'rgba(239, 68, 68, 0.92)';
    popup.style.color = '#fff';
    popup.style.padding = '1.2rem 1.5rem';
    popup.style.borderRadius = '10px';
    popup.style.boxShadow = '0 15px 30px rgba(239, 68, 68, 0.35)';
    popup.style.zIndex = '999999';
    popup.style.display = 'flex';
    popup.style.alignItems = 'center';
    popup.style.gap = '1.2rem';
    popup.style.border = '1px solid #fca5a5';
    popup.style.backdropFilter = 'blur(10px)';
    popup.style.transition = 'all 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275)';
    popup.style.transform = 'translateY(-30px)';
    popup.style.opacity = '0';
    
    const pVal = typeof pirVal === 'number' ? pirVal.toFixed(2) : 'DETECTED';
    const sVal = typeof soundVal === 'number' ? soundVal.toFixed(1) + ' dB' : 'DETECTED';
    
    popup.innerHTML = `
        <div style="font-size: 2.2rem; color: #fff;">
            <i class="fa-solid fa-triangle-exclamation fa-beat"></i>
        </div>
        <div>
            <h4 style="margin: 0 0 0.3rem 0; font-family: var(--font-title); font-size: 1.15rem; text-transform: uppercase; letter-spacing: 0.5px;">Suspicious Activity Detected</h4>
            <p style="margin: 0; font-size: 0.88rem; opacity: 0.95;">Both sensors triggered simultaneously.</p>
            <div style="display: flex; gap: 0.6rem; margin-top: 0.7rem;">
                <span style="background: rgba(0,0,0,0.25); padding: 0.25rem 0.6rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; display: inline-flex; align-items: center; gap: 0.3rem;"><i class="fa-solid fa-person-walking"></i> PIR: ${pVal}</span>
                <span style="background: rgba(0,0,0,0.25); padding: 0.25rem 0.6rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; display: inline-flex; align-items: center; gap: 0.3rem;"><i class="fa-solid fa-volume-high"></i> SOUND: ${sVal}</span>
            </div>
        </div>
    `;
    
    document.body.appendChild(popup);
    
    // Animate in
    setTimeout(() => {
        popup.style.transform = 'translateY(0)';
        popup.style.opacity = '1';
    }, 10);
    
    // Auto-remove after 7 seconds
    setTimeout(() => {
        popup.style.opacity = '0';
        popup.style.transform = 'translateY(-30px)';
        setTimeout(() => popup.remove(), 500);
    }, 7000);
}

// Supabase Client & Realtime Subscription
let supabaseClient = null;
let rawSensorChannel = null;

async function getSupabaseClient() {
    if (supabaseClient) return supabaseClient;
    let config = window.SUPABASE_CONFIG || {};
    if (!config.url || !config.anonKey) {
        try {
            const resp = await fetch('/api/config/supabase');
            if (resp.ok) {
                const confData = await resp.json();
                config = { url: confData.url, anonKey: confData.anon_key };
                window.SUPABASE_CONFIG = config;
            }
        } catch (e) {
            console.warn('[SUPABASE] Could not fetch config from API:', e);
        }
    }
    
    if (config.url && config.anonKey && window.supabase && window.supabase.createClient) {
        try {
            supabaseClient = window.supabase.createClient(config.url, config.anonKey);
            console.log('[SUPABASE] Realtime client initialized successfully');
        } catch (e) {
            console.error('[SUPABASE] Error initializing Supabase client:', e);
        }
    }
    return supabaseClient;
}

async function initSupabaseRealtime() {
    const client = await getSupabaseClient();
    if (!client) {
        console.warn('[SUPABASE] Realtime client not ready yet');
        return;
    }
    
    if (rawSensorChannel) {
        return; // Already subscribed
    }

    try {
        rawSensorChannel = client
            .channel('realtime:raw_sensor_data')
            .on(
                'postgres_changes',
                {
                    event: 'INSERT',
                    schema: 'public',
                    table: 'raw_sensor_data'
                },
                (payload) => {
                    console.log('[SUPABASE REALTIME] New raw_sensor_data row:', payload.new);
                    const record = payload.new;
                    if (record.device_id && record.device_id !== selectedMonitoringNode) {
                        return; // Ignore updates for non-selected node
                    }
                    const pir_bool = Boolean(record.pir_detected);
                    const sound_bool = Boolean(record.sound_detected);
                    
                    const transformed = {
                        id: record.id,
                        timestamp: record.timestamp,
                        pir: pir_bool ? 'DETECTED' : 'SAFE',
                        pir_val: pir_bool ? 1.0 : 0.0,
                        sound: sound_bool ? 'DETECTED' : 'SAFE',
                        sound_val: parseFloat(record.sound_level || (sound_bool ? 85.0 : 35.0)),
                        sound_level: record.sound_level,
                        latitude: record.latitude,
                        longitude: record.longitude,
                        device_id: record.device_id
                    };

                    if (pir_bool && sound_bool) {
                        triggerSuspiciousPopup(transformed.pir_val, transformed.sound_val);
                    }

                    // Check if date filter applies
                    if (rawDataDateFilter) {
                        const recDate = new Date(transformed.timestamp).toLocaleDateString('en-CA');
                        if (recDate !== rawDataDateFilter) {
                            return;
                        }
                    }

                    // Check for duplicate
                    const exists = rawDataFiltered.some(r => r.id && r.id === transformed.id);
                    if (!exists) {
                        rawDataFiltered.unshift(transformed);
                        renderRawDataTable();
                    }
                }
            )
            .subscribe((status) => {
                console.log('[SUPABASE REALTIME] raw_sensor_data channel status:', status);
            });
    } catch (err) {
        console.error('[SUPABASE REALTIME] Setup failed:', err);
    }
}

// Initialize sensor monitoring
function initSensorMonitoring() {
    console.log("[ESP32] Initializing Sensor Monitoring...");
    
    // Set initial auto-refresh status
    updateAutoRefreshStatus(true);
    
    // Set initial device status to offline until we get real data
    updateDeviceStatusHeader(false);
    updateLastUpdateTime(null);
    
    // Connect to Supabase Realtime
    initSupabaseRealtime();
    
    // Load current sensor data (this will check connection and update status)
    updateSensorStatus();
    
    // Start real-time updates
    startSensorUpdates();
    
    // Initialize chart
    initSensorChart();
    
    // Load initial chart data
    loadChartData();
    
    // Load initial raw data
    loadRawData();
}

// Update sensor status cards
async function updateSensorStatus() {
    try {
        console.log(`[ESP32] Fetching current sensor data for ${selectedMonitoringNode}...`);
        const response = await fetch(`/api/sensor/current?node_id=${selectedMonitoringNode}`);
        const data = await response.json();
        
        if (data.error) {
            console.error('[ESP32] Error fetching sensor data:', data.error);
            esp32Online = false;
            updateESP32Status(false);
            displayOfflineState();
            return;
        }
        
        // Check ESP32 connection status from API
        if (!data.esp32_connected) {
            console.log('[ESP32] Device is offline according to API');
            esp32Online = false;
            updateESP32Status(false);
            displayOfflineState();
            // Preserve last update time when offline (don't update it)
            console.log('[ESP32] Device offline, preserving last update timestamp');
            return;
        }
        
        console.log('[ESP32] Device is online, processing real data');
        esp32Online = true;
        updateESP32Status(true);
        
        // Update last update timestamp with new data
        if (data.last_update) {
            updateLastUpdateTime(data.last_update);
            console.log('[ESP32] Last update updated with new data:', data.last_update);
        }
        
        // Update PIR card with real data
        console.log('[ESP32] PIR value:', data.pir);
        document.getElementById('pir-current-value').textContent = data.pir.toFixed(2);
        document.getElementById('pir-min').textContent = data.pir_min.toFixed(1);
        document.getElementById('pir-max').textContent = data.pir_max.toFixed(1);
        document.getElementById('pir-limit').textContent = data.pir_limit.toFixed(1);
        
        const pirStatusIndicator = document.getElementById('pir-status-indicator');
        const pirStatusDot = pirStatusIndicator.querySelector('.status-dot');
        const pirStatusText = document.getElementById('pir-status-text');
        const pirStatusTag = document.getElementById('pir-status-tag');
        
        if (data.pir_status === 'ALERT') {
            pirStatusIndicator.classList.add('alert');
            pirStatusDot.classList.remove('normal');
            pirStatusDot.classList.add('alert');
            pirStatusText.textContent = 'PIR ALERT';
            pirStatusTag.textContent = 'Alert';
            pirStatusTag.classList.add('alert');
            pirStatusTag.classList.remove('normal');
            console.log('[ESP32] PIR ALERT triggered');
        } else {
            pirStatusIndicator.classList.remove('alert');
            pirStatusDot.classList.remove('alert');
            pirStatusDot.classList.add('normal');
            pirStatusText.textContent = 'Normal';
            pirStatusTag.textContent = 'Normal';
            pirStatusTag.classList.add('normal');
            pirStatusTag.classList.remove('alert');
        }
        
        // Update Sound card with real data
        console.log('[ESP32] Sound value:', data.sound);
        document.getElementById('sound-current-value').textContent = data.sound.toFixed(2);
        document.getElementById('sound-min').textContent = data.sound_min.toFixed(1);
        document.getElementById('sound-max').textContent = data.sound_max.toFixed(1);
        document.getElementById('sound-limit').textContent = data.sound_limit.toFixed(1);
        
        const soundStatusIndicator = document.getElementById('sound-status-indicator');
        const soundStatusDot = soundStatusIndicator.querySelector('.status-dot');
        const soundStatusText = document.getElementById('sound-status-text');
        const soundStatusTag = document.getElementById('sound-status-tag');
        
        if (data.sound_status === 'ALERT') {
            soundStatusIndicator.classList.add('alert');
            soundStatusDot.classList.remove('normal');
            soundStatusDot.classList.add('alert');
            soundStatusText.textContent = 'SOUND ALERT';
            soundStatusTag.textContent = 'Alert';
            soundStatusTag.classList.add('alert');
            soundStatusTag.classList.remove('normal');
            console.log('[ESP32] SOUND ALERT triggered');
        } else {
            soundStatusIndicator.classList.remove('alert');
            soundStatusDot.classList.remove('alert');
            soundStatusDot.classList.add('normal');
            soundStatusText.textContent = 'Normal';
            soundStatusTag.textContent = 'Normal';
            soundStatusTag.classList.add('normal');
            soundStatusTag.classList.remove('alert');
        }
        
        // Trigger Suspicious Activity Popup if both are ALERT
        if (data.pir_status === 'ALERT' && data.sound_status === 'ALERT') {
            triggerSuspiciousPopup(data.pir, data.sound);
        }
        
    } catch (error) {
        console.error('[ESP32] Error updating sensor status:', error);
        esp32Online = false;
        updateESP32Status(false);
        displayOfflineState();
    }
}

// Display offline state for sensor cards
function displayOfflineState() {
    const nodeLabel = selectedMonitoringNode === 'ESP32-NODE-01' ? 'Node 1' : 'Node 2';
    // PIR card offline state
    document.getElementById('pir-current-value').textContent = '—';
    
    const pirStatusIndicator = document.getElementById('pir-status-indicator');
    const pirStatusDot = pirStatusIndicator.querySelector('.status-dot');
    const pirStatusText = document.getElementById('pir-status-text');
    const pirStatusTag = document.getElementById('pir-status-tag');
    
    pirStatusIndicator.classList.remove('alert');
    pirStatusDot.classList.remove('alert');
    pirStatusDot.classList.remove('normal');
    pirStatusDot.classList.add('offline');
    pirStatusText.textContent = `${nodeLabel} Offline`;
    pirStatusTag.textContent = 'Offline';
    pirStatusTag.classList.remove('alert');
    pirStatusTag.classList.remove('normal');
    pirStatusTag.classList.add('offline');
    
    // Sound card offline state
    document.getElementById('sound-current-value').textContent = '—';
    
    const soundStatusIndicator = document.getElementById('sound-status-indicator');
    const soundStatusDot = soundStatusIndicator.querySelector('.status-dot');
    const soundStatusText = document.getElementById('sound-status-text');
    const soundStatusTag = document.getElementById('sound-status-tag');
    
    soundStatusIndicator.classList.remove('alert');
    soundStatusDot.classList.remove('alert');
    soundStatusDot.classList.remove('normal');
    soundStatusDot.classList.add('offline');
    soundStatusText.textContent = `${nodeLabel} Offline`;
    soundStatusTag.textContent = 'Offline';
    soundStatusTag.classList.remove('alert');
    soundStatusTag.classList.remove('normal');
    soundStatusTag.classList.add('offline');
}

// Update ESP32 connection status display
function updateESP32Status(online) {
    const statusElement = document.getElementById('esp32-status');
    const statusText = document.getElementById('esp32-status-text');
    const nodeLabel = selectedMonitoringNode === 'ESP32-NODE-01' ? 'ESP32 (Node 1)' : 'ESP32 (Node 2)';
    
    if (online) {
        statusElement.classList.remove('offline');
        statusElement.classList.add('online');
        statusText.textContent = `${nodeLabel}: ONLINE`;
    } else {
        statusElement.classList.remove('online');
        statusElement.classList.add('offline');
        statusText.textContent = `${nodeLabel}: OFFLINE`;
    }
    
    // Update device status header
    updateDeviceStatusHeader(online);
}

// Update device status header
function updateDeviceStatusHeader(online) {
    const deviceStatusPill = document.getElementById('device-status-pill');
    const deviceStatusDot = document.getElementById('device-status-dot');
    const deviceStatusText = document.getElementById('device-status-text');
    const nodeLabel = selectedMonitoringNode === 'ESP32-NODE-01' ? 'Node 1' : 'Node 2';
    
    if (online) {
        deviceStatusPill.classList.remove('offline');
        deviceStatusText.textContent = `${nodeLabel}: Online`;
    } else {
        deviceStatusPill.classList.add('offline');
        deviceStatusText.textContent = `${nodeLabel}: Offline`;
    }
}

// Update last update timestamp
function updateLastUpdateTime(timestamp) {
    const lastUpdateText = document.getElementById('last-update-text');
    
    if (timestamp) {
        const date = new Date(timestamp);
        const formattedDate = date.toLocaleDateString('en-US', { 
            day: 'numeric', 
            month: 'short' 
        });
        const formattedTime = date.toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit',
            hour12: false 
        });
        lastUpdateText.textContent = `Last update: ${formattedDate}, ${formattedTime}`;
        lastUpdateTime = timestamp;
        console.log("[ESP32] Last update set to:", `${formattedDate}, ${formattedTime}`);
    } else {
        // Only set to "--" if we've never received any data
        if (!lastUpdateTime) {
            lastUpdateText.textContent = 'Last update: --';
            console.log("[ESP32] No data received yet, Last update: --");
        } else {
            console.log("[ESP32] Preserving existing last update:", lastUpdateTime);
        }
    }
}

// Update auto-refresh status
function updateAutoRefreshStatus(enabled) {
    const autoRefreshText = document.getElementById('auto-refresh-text');
    const autoRefreshPill = document.getElementById('auto-refresh-pill');
    const autoRefreshIcon = document.getElementById('auto-refresh-icon');
    
    autoRefreshText.textContent = enabled ? 'Auto-Refresh: ON' : 'Auto-Refresh: OFF';
    autoRefreshEnabled = enabled;
    
    if (enabled) {
        autoRefreshPill.classList.remove('disabled');
        autoRefreshIcon.classList.add('fa-spin');
    } else {
        autoRefreshPill.classList.add('disabled');
        autoRefreshIcon.classList.remove('fa-spin');
    }
    
    console.log(`[ESP32] Auto-Refresh ${enabled ? 'ENABLED' : 'DISABLED'}`);
}

// Toggle auto-refresh
function toggleAutoRefresh() {
    autoRefreshEnabled = !autoRefreshEnabled;
    updateAutoRefreshStatus(autoRefreshEnabled);
    
    if (autoRefreshEnabled) {
        // Restart the interval
        startSensorUpdates();
    } else {
        // Stop the interval
        if (updateInterval) {
            clearInterval(updateInterval);
            updateInterval = null;
        }
    }
}

// Manual refresh
function manualRefresh() {
    console.log("[ESP32] Manual refresh triggered");
    updateSensorStatus();
    loadChartData();
    loadRawData();
}

// Check ESP32 connection status using the dedicated API
async function checkESP32Connection() {
    try {
        console.log(`[ESP32] Checking connection status for ${selectedMonitoringNode}...`);
        const response = await fetch(`/api/esp32/status?node_id=${selectedMonitoringNode}`);
        const data = await response.json();
        
        console.log("[ESP32] Connection status response:", data);
        
        if (data.connected) {
            esp32Online = true;
            updateESP32Status(true);
            // Update last update time from API
            if (data.last_seen && data.last_seen !== 'Never') {
                updateLastUpdateTime(data.last_seen);
                console.log("[ESP32] Connection: Online, Last update:", data.last_seen);
            }
        } else {
            esp32Online = false;
            updateESP32Status(false);
            // Keep last update time when offline (don't clear it)
            console.log("[ESP32] Connection: Offline, preserving last update");
        }
    } catch (error) {
        console.error("[ESP32] Error checking connection:", error);
        esp32Online = false;
        updateESP32Status(false);
    }
}

// Start real-time sensor updates
function startSensorUpdates() {
    // Clear existing interval if any
    if (updateInterval) {
        clearInterval(updateInterval);
    }
    
    // Hook into existing polling mechanism from app.js
    hookIntoExistingPolling();
    
    // Standalone polling as backup
    if (autoRefreshEnabled) {
        console.log(`[ESP32] Starting standalone auto-refresh with ${AUTO_REFRESH_INTERVAL}ms interval`);
        updateInterval = setInterval(() => {
            console.log("[ESP32] Standalone auto-refresh cycle starting...");
            updateSensorStatus();
            // Auto-update chart and raw data regardless of live ESP32 status
            // so historical data is always visible.
            loadChartData();
            loadRawData();
        }, AUTO_REFRESH_INTERVAL);
    } else {
        console.log("[ESP32] Auto-refresh is disabled, not starting interval");
    }
}

// Hook into existing app.js polling mechanism
function hookIntoExistingPolling() {
    // Override the existing fetchStatusAndNodes to also update sensor monitoring
    if (typeof window.fetchStatusAndNodes === 'function') {
        const originalFetchStatusAndNodes = window.fetchStatusAndNodes;
        window.fetchStatusAndNodes = function() {
            // Call original function
            const result = originalFetchStatusAndNodes.apply(this, arguments);
            
            // Then update sensor monitoring when sensor tab is active
            if (document.getElementById('sensor-monitoring-tab') && 
                document.getElementById('sensor-monitoring-tab').classList.contains('active')) {
                console.log("[ESP32] Hooked into existing polling - updating sensor monitoring");
                updateSensorStatus();
                loadChartData();
                loadRawData();
            }
            
            return result;
        };
        console.log("[ESP32] Successfully hooked into existing polling mechanism");
    } else {
        console.log("[ESP32] Could not find existing polling function, will use standalone polling");
    }
}

// Raw Data Functions
async function loadRawData() {
    try {
        console.log(`[ESP32] Loading raw data from Supabase for ${selectedMonitoringNode}...`);
        
        // Build query parameters
        const params = new URLSearchParams({
            limit: 50,
            device_id: selectedMonitoringNode
        });
        
        if (rawDataDateFilter) {
            params.append('from_date', rawDataDateFilter);
            params.append('to_date', rawDataDateFilter);
        }
        
        const response = await fetch(`/api/supabase/raw-sensor-data?${params}`);
        const data = await response.json();
        
        if (data.error) {
            console.error('[ESP32] Error loading raw data:', data.error);
            const tableBody = document.getElementById('raw-data-table-body');
            if (tableBody) {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="3" style="text-align: center; padding: 2rem; color: var(--status-danger);">
                            <i class="fa-solid fa-triangle-exclamation" style="font-size: 1.5rem; margin-bottom: 0.5rem;"></i>
                            <p style="font-weight:600;">Unable to load ESP32 records</p>
                            <p style="font-size: 0.75rem;">${data.error}</p>
                        </td>
                    </tr>
                `;
            }
            return;
        }
        
        rawDataFiltered = data;
        console.log(`[ESP32] Loaded ${rawDataFiltered.length} raw data records from Supabase`);
        
        // Reset to first page
        rawDataCurrentPage = 1;
        
        // Render table
        renderRawDataTable();
        
    } catch (error) {
        console.error('[ESP32] Error loading raw data:', error);
        const tableBody = document.getElementById('raw-data-table-body');
        if (tableBody) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="3" style="text-align: center; padding: 2rem; color: var(--status-danger);">
                        <i class="fa-solid fa-triangle-exclamation" style="font-size: 1.5rem; margin-bottom: 0.5rem;"></i>
                        <p style="font-weight:600;">Unable to load ESP32 records</p>
                        <p style="font-size: 0.75rem;">${error.message}</p>
                    </td>
                </tr>
            `;
        }
    }
}

function renderRawDataTable() {
    const tableBody = document.getElementById('raw-data-table-body');
    
    if (!rawDataFiltered || rawDataFiltered.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="3" style="text-align: center; padding: 2rem; color: var(--text-muted);">
                    <i class="fa-solid fa-circle-info" style="font-size: 1.5rem; margin-bottom: 0.5rem; color: var(--text-dim);"></i>
                    <p style="font-weight: 600;">No sensor data available</p>
                </td>
            </tr>
        `;
        updatePaginationInfo(0, 0, 0);
        return;
    }
    
    // Calculate pagination
    const startIndex = (rawDataCurrentPage - 1) * rawDataPerPage;
    const endIndex = startIndex + rawDataPerPage;
    const pageData = rawDataFiltered.slice(startIndex, endIndex);
    
    // Generate table rows
    let html = '';
    pageData.forEach(record => {
        const date = new Date(record.timestamp);
        const formattedDate = !isNaN(date.getTime()) ? date.toLocaleDateString('en-US', { 
            month: 'short', 
            day: 'numeric', 
            year: 'numeric' 
        }) : 'Recent';
        const formattedTime = !isNaN(date.getTime()) ? date.toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit',
            hour12: false 
        }) : '--:--:--';
        
        // Determine PIR status
        let isPirAlert = false;
        if (typeof record.pir === 'number') {
            isPirAlert = record.pir > 0.5;
        } else if (typeof record.pir === 'string') {
            isPirAlert = record.pir.toUpperCase().includes('DETECT');
        } else if (typeof record.pir === 'boolean') {
            isPirAlert = record.pir;
        }

        // Determine Sound status
        let isSoundAlert = false;
        if (typeof record.sound === 'number') {
            isSoundAlert = record.sound > 0.3;
        } else if (typeof record.sound === 'string') {
            isSoundAlert = record.sound.toUpperCase().includes('DETECT');
        } else if (typeof record.sound === 'boolean') {
            isSoundAlert = record.sound;
        }

        const pirBadge = isPirAlert 
            ? `<span class="node-badge alert" style="font-size:0.75rem; padding: 0.2rem 0.5rem;"><i class="fa-solid fa-person-walking"></i> DETECTED</span>`
            : `<span class="node-badge safe" style="font-size:0.75rem; padding: 0.2rem 0.5rem;"><i class="fa-solid fa-shield-check"></i> SAFE</span>`;

        const soundBadge = isSoundAlert 
            ? `<span class="node-badge alert" style="font-size:0.75rem; padding: 0.2rem 0.5rem;"><i class="fa-solid fa-volume-high"></i> DETECTED</span>`
            : `<span class="node-badge safe" style="font-size:0.75rem; padding: 0.2rem 0.5rem;"><i class="fa-solid fa-volume-xmark"></i> SAFE</span>`;
        
        html += `
            <tr>
                <td>
                    <div style="font-weight: 600;">${formattedDate}</div>
                    <div style="font-size: 0.8rem; color: var(--text-muted);">${formattedTime}</div>
                </td>
                <td>${pirBadge}</td>
                <td>${soundBadge}</td>
            </tr>
        `;
    });
    
    tableBody.innerHTML = html;
    
    // Update pagination info
    updatePaginationInfo(startIndex + 1, Math.min(endIndex, rawDataFiltered.length), rawDataFiltered.length);
    
    // Update button states
    document.getElementById('raw-data-prev-btn').disabled = rawDataCurrentPage === 1;
    document.getElementById('raw-data-next-btn').disabled = endIndex >= rawDataFiltered.length;
}

function updatePaginationInfo(start, end, total) {
    const info = document.getElementById('raw-data-pagination-info');
    if (total === 0) {
        info.textContent = 'Showing 0 to 0 of 0 records';
    } else {
        info.textContent = `Showing ${start} to ${end} of ${total} records`;
    }
}

function searchRawData() {
    const dateInput = document.getElementById('raw-data-date');
    if (dateInput.value) {
        rawDataDateFilter = dateInput.value;
        console.log(`[ESP32] Applying date filter: ${rawDataDateFilter}`);
        loadRawData();
    } else {
        console.log('[ESP32] No date selected for search');
    }
}

function resetRawData() {
    document.getElementById('raw-data-date').value = '';
    rawDataDateFilter = null;
    rawDataCurrentPage = 1;
    console.log('[ESP32] Resetting raw data filters');
    loadRawData();
}

function prevRawDataPage() {
    if (rawDataCurrentPage > 1) {
        rawDataCurrentPage--;
        renderRawDataTable();
    }
}

function nextRawDataPage() {
    const maxPage = Math.ceil(rawDataFiltered.length / rawDataPerPage);
    if (rawDataCurrentPage < maxPage) {
        rawDataCurrentPage++;
        renderRawDataTable();
    }
}

// Show offline state on chart
function showChartOfflineState() {
    if (!sensorChart) return;
    
    const nodeLabel = selectedMonitoringNode === 'ESP32-NODE-01' ? 'Node 1' : 'Node 2';
    
    // Clear chart data and show offline message
    sensorChart.data.labels = [];
    sensorChart.data.datasets = [];
    sensorChart.options.plugins.title = {
        display: true,
        text: `No live sensor data - ${nodeLabel} is offline`,
        color: '#ef4444',
        font: {
            size: 16,
            weight: 'bold',
            family: 'Inter'
        },
        padding: {
            top: 20,
            bottom: 20
        }
    };
    sensorChart.update();
}

// Initialize sensor chart - Matching Reference Design
function initSensorChart() {
    const ctx = document.getElementById('sensor-chart').getContext('2d');
    
    const chartConfig = {
        type: 'line',
        data: {
            labels: [],
            datasets: []
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#ffffff',
                        font: {
                            family: 'Inter',
                            size: 12,
                            weight: '600'
                        },
                        usePointStyle: true,
                        padding: 15
                    }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    backgroundColor: 'rgba(0, 0, 0, 0.9)',
                    titleColor: '#ffffff',
                    bodyColor: '#ffffff',
                    borderColor: 'rgba(16, 185, 129, 0.5)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${context.parsed.y.toFixed(2)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    display: true,
                    title: {
                        display: true,
                        text: 'Time →',
                        color: '#ffffff',
                        font: {
                            family: 'Inter',
                            size: 12,
                            weight: '600'
                        },
                        padding: {
                            top: 10
                        }
                    },
                    ticks: {
                        color: '#ffffff',
                        font: {
                            family: 'Inter',
                            size: 10
                        },
                        maxRotation: 45,
                        minRotation: 45,
                        maxTicksLimit: 10,
                        autoSkip: true
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)',
                        drawBorder: false
                    }
                },
                y: {
                    display: true,
                    title: {
                        display: true,
                        text: 'Value',
                        color: '#ffffff',
                        font: {
                            family: 'Inter',
                            size: 12,
                            weight: '600'
                        }
                    },
                    ticks: {
                        color: '#ffffff',
                        font: {
                            family: 'Inter',
                            size: 10
                        },
                        stepSize: 0.2
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)',
                        drawBorder: false
                    },
                    min: 0,
                    max: 1.0
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            },
            elements: {
                line: {
                    tension: 0.4,
                    borderWidth: 2
                },
                point: {
                    radius: 2,
                    hoverRadius: 6,
                    borderWidth: 2
                }
            }
        }
    };
    
    sensorChart = new Chart(ctx, chartConfig);
}

// Load chart data based on current filters
async function loadChartData() {
    try {
        const statusResponse = await fetch(`/api/esp32/status?node_id=${selectedMonitoringNode}`);
        const statusData = await statusResponse.json();
        
        if (!statusData.connected) {
            esp32Online = false;
            updateESP32Status(false);
            // Node is OFFLINE - show empty state, do NOT load historical data
            console.log(`[CHART] Node ${selectedMonitoringNode} is offline - showing empty state`);
            showChartOfflineState();
            return;
        }
        
        const dataPoints = document.getElementById('data-points').value;
        const stepInput = document.getElementById('step-input').value;
        const fromDate = document.getElementById('from-date').value;
        const toDate = document.getElementById('to-date').value;
        
        let url = `/api/sensor/history?sensor=${currentSensorType}&limit=${dataPoints}&step=${stepInput}&node_id=${selectedMonitoringNode}`;
        
        if (fromDate) {
            url += `&from_date=${fromDate}`;
        }
        if (toDate) {
            url += `&to_date=${toDate}`;
        }
        
        const response = await fetch(url);
        const result = await response.json();
        
        if (result.error) {
            console.error('Error fetching sensor history:', result.error);
            showChartOfflineState();
            return;
        }
        
        if (result.data && result.data.length > 0) {
            updateChart(result.data, result.sensor_type);
        } else {
            console.log('No sensor data available for selected period');
            // Show offline state if no data
            showChartOfflineState();
        }
        
    } catch (error) {
        console.error('Error loading chart data:', error);
        showChartOfflineState();
    }
}

// Update chart with new data - Matching Reference Design
function updateChart(data, sensorType) {
    if (!sensorChart) return;
    
    // Remove offline title if it exists
    sensorChart.options.plugins.title = {
        display: false
    };
    
    // Prepare labels and datasets with exact time format from reference
    const labels = data.map(d => {
        // Format timestamp for display - exact HH:MM:SS format as in reference
        const date = new Date(d.timestamp);
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');
        return `${hours}:${minutes}:${seconds}`;
    });
    
    let datasets = [];
    
    if (sensorType === 'Combined') {
        datasets = [
            {
                label: 'PIR',
                data: data.map(d => d.pir),
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 2,
                pointHoverRadius: 6,
                pointBackgroundColor: '#10b981',
                pointBorderColor: '#10b981'
            },
            {
                label: 'sound',
                data: data.map(d => d.sound),
                borderColor: '#06b6d4',
                backgroundColor: 'rgba(6, 182, 212, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 2,
                pointHoverRadius: 6,
                pointBackgroundColor: '#06b6d4',
                pointBorderColor: '#06b6d4'
            }
        ];
    } else if (sensorType === 'PIR') {
        datasets = [
            {
                label: 'PIR',
                data: data.map(d => d.value),
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 2,
                pointHoverRadius: 6,
                pointBackgroundColor: '#10b981',
                pointBorderColor: '#10b981'
            }
        ];
    } else if (sensorType === 'Sound') {
        datasets = [
            {
                label: 'sound',
                data: data.map(d => d.value),
                borderColor: '#06b6d4',
                backgroundColor: 'rgba(6, 182, 212, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 2,
                pointHoverRadius: 6,
                pointBackgroundColor: '#06b6d4',
                pointBorderColor: '#06b6d4'
            }
        ];
    }
    
    // Calculate optimal tick interval based on data points
    const totalPoints = labels.length;
    let maxTicksLimit = 10; // Default max ticks
    
    if (totalPoints > 50) {
        maxTicksLimit = 8;
    } else if (totalPoints > 100) {
        maxTicksLimit = 6;
    } else if (totalPoints > 200) {
        maxTicksLimit = 4;
    }
    
    // Update chart with improved time axis
    sensorChart.data.labels = labels;
    sensorChart.data.datasets = datasets;
    
    // Update X-axis configuration for exact reference appearance
    sensorChart.options.scales.x.ticks.maxTicksLimit = maxTicksLimit;
    sensorChart.options.scales.x.ticks.maxRotation = 45;
    sensorChart.options.scales.x.ticks.minRotation = 45;
    
    sensorChart.update('none'); // Update without animation for real-time performance
}

// Set sensor type
function setSensorType(type) {
    currentSensorType = type;
    
    // Update tab buttons
    document.querySelectorAll('.sensor-tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    if (type === 'pir') {
        document.getElementById('pir-tab-btn').classList.add('active');
    } else if (type === 'sound') {
        document.getElementById('sound-tab-btn').classList.add('active');
    } else if (type === 'combined') {
        document.getElementById('combined-tab-btn').classList.add('active');
    }
    
    // Reload chart data
    loadChartData();
}

// Apply filters
function applyFilters() {
    loadChartData();
}

// Reset filters - Exact Reference Design
function resetFilters() {
    // Reset date inputs
    document.getElementById('from-date').value = '';
    document.getElementById('to-date').value = '';
    
    // Reset data points to default
    document.getElementById('data-points').value = '100';
    
    // Reset step to default
    document.getElementById('step-input').value = '1';
    
    // Reset sensor type to PIR
    setSensorType('pir');
    
    // Reload chart data
    loadChartData();
}

// Export sensor data
function exportSensorData() {
    const dataPoints = document.getElementById('data-points').value;
    const stepInput = document.getElementById('step-input').value;
    const fromDate = document.getElementById('from-date').value;
    const toDate = document.getElementById('to-date').value;
    
    let url = `/api/sensor/export?sensor=${currentSensorType}&limit=${dataPoints}&step=${stepInput}&node_id=${selectedMonitoringNode}`;
    
    if (fromDate) {
        url += `&from_date=${fromDate}`;
    }
    if (toDate) {
        url += `&to_date=${toDate}`;
    }
    
    // Create download link
    const link = document.createElement('a');
    link.href = url;
    link.download = `sensor_data_${currentSensorType}_${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Force update UI for the selected node from URL if present
    const tempNode = selectedMonitoringNode;
    selectedMonitoringNode = null;
    switchMonitoringNode(tempNode);

    // Check if sensor monitoring tab exists
    if (document.getElementById('sensor-monitoring-tab')) {
        // Initialize when tab is first opened
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.target.id === 'sensor-monitoring-tab' && 
                    mutation.target.classList.contains('active')) {
                    initSensorMonitoring();
                    observer.disconnect();
                }
            });
        });
        
        observer.observe(document.getElementById('sensor-monitoring-tab'), {
            attributes: true,
            attributeFilter: ['class']
        });
    }

    // Auto-open calendar picker when clicking anywhere on date or datetime-local inputs
    document.addEventListener('click', function(e) {
        if (e.target && (e.target.matches('input[type="date"]') || e.target.matches('input[type="datetime-local"]'))) {
            try {
                if (typeof e.target.showPicker === 'function') {
                    e.target.showPicker();
                }
            } catch (err) {
                // Ignore if browser restricts showPicker
            }
        }
    });
});