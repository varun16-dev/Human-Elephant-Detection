// Sensor Monitoring Module - Exact Reference Design Implementation

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

// Initialize sensor monitoring
function initSensorMonitoring() {
    console.log("[ESP32] Initializing Sensor Monitoring...");
    
    // Set initial auto-refresh status
    updateAutoRefreshStatus(true);
    
    // Set initial device status to offline until we get real data
    updateDeviceStatusHeader(false);
    updateLastUpdateTime(null);
    
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
        console.log("[ESP32] Fetching current sensor data...");
        const response = await fetch('/api/sensor/current');
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
        
    } catch (error) {
        console.error('[ESP32] Error updating sensor status:', error);
        esp32Online = false;
        updateESP32Status(false);
        displayOfflineState();
    }
}

// Display offline state for sensor cards
function displayOfflineState() {
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
    pirStatusText.textContent = 'ESP32 Offline';
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
    soundStatusText.textContent = 'ESP32 Offline';
    soundStatusTag.textContent = 'Offline';
    soundStatusTag.classList.remove('alert');
    soundStatusTag.classList.remove('normal');
    soundStatusTag.classList.add('offline');
}

// Update ESP32 connection status display
function updateESP32Status(online) {
    const statusElement = document.getElementById('esp32-status');
    const statusText = document.getElementById('esp32-status-text');
    
    if (online) {
        statusElement.classList.remove('offline');
        statusElement.classList.add('online');
        statusText.textContent = 'ESP32: ONLINE';
    } else {
        statusElement.classList.remove('online');
        statusElement.classList.add('offline');
        statusText.textContent = 'ESP32: OFFLINE';
    }
    
    // Update device status header
    updateDeviceStatusHeader(online);
}

// Update device status header
function updateDeviceStatusHeader(online) {
    const deviceStatusPill = document.getElementById('device-status-pill');
    const deviceStatusDot = document.getElementById('device-status-dot');
    const deviceStatusText = document.getElementById('device-status-text');
    
    if (online) {
        deviceStatusPill.classList.remove('offline');
        deviceStatusText.textContent = 'Device: Online';
    } else {
        deviceStatusPill.classList.add('offline');
        deviceStatusText.textContent = 'Device: Offline';
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
        console.log("[ESP32] Checking connection status...");
        const response = await fetch('/api/esp32/status');
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
            // Auto-update chart and raw data if ESP32 is online
            if (esp32Online) {
                loadChartData();
                loadRawData();
            } else {
                // If ESP32 is offline, show offline message on chart
                showChartOfflineState();
            }
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
                if (esp32Online) {
                    loadChartData();
                    loadRawData();
                }
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
        console.log("[ESP32] Loading raw data...");
        const response = await fetch('/api/sensor/history');
        const data = await response.json();
        
        if (data.error) {
            console.error('[ESP32] Error loading raw data:', data.error);
            return;
        }
        
        // Apply date filter if set
        if (rawDataDateFilter) {
            const filterDate = new Date(rawDataDateFilter);
            rawDataFiltered = data.filter(record => {
                const recordDate = new Date(record.timestamp);
                return recordDate.toDateString() === filterDate.toDateString();
            });
            console.log(`[ESP32] Applied date filter: ${rawDataDateFilter}, records: ${rawDataFiltered.length}`);
        } else {
            rawDataFiltered = data;
            console.log(`[ESP32] Loaded ${rawDataFiltered.length} raw data records`);
        }
        
        // Sort by timestamp descending (newest first)
        rawDataFiltered.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        
        // Reset to first page
        rawDataCurrentPage = 1;
        
        // Render table
        renderRawDataTable();
        
    } catch (error) {
        console.error('[ESP32] Error loading raw data:', error);
    }
}

function renderRawDataTable() {
    const tableBody = document.getElementById('raw-data-table-body');
    
    if (!rawDataFiltered || rawDataFiltered.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="3" style="text-align: center; padding: 2rem; color: var(--text-muted);">
                    <i class="fa-solid fa-circle-info" style="font-size: 1.5rem; margin-bottom: 0.5rem; color: var(--text-dim);"></i>
                    <p style="font-weight: 600;">${esp32Online ? 'No data available for selected period' : 'Waiting for ESP32 data...'}</p>
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
        const formattedDate = date.toLocaleDateString('en-US', { 
            month: 'short', 
            day: 'numeric', 
            year: 'numeric' 
        });
        const formattedTime = date.toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit',
            hour12: false 
        });
        
        html += `
            <tr>
                <td>
                    <div style="font-weight: 600;">${formattedDate}</div>
                    <div style="font-size: 0.8rem; color: var(--text-muted);">${formattedTime}</div>
                </td>
                <td style="font-weight: 600; color: ${record.pir > 0.5 ? '#10b981' : '#6b7280'};">${record.pir.toFixed(2)}</td>
                <td style="font-weight: 600; color: ${record.sound > 0.3 ? '#06b6d4' : '#6b7280'};">${record.sound.toFixed(2)}</td>
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
    
    // Clear chart data and show offline message
    sensorChart.data.labels = [];
    sensorChart.data.datasets = [];
    sensorChart.options.plugins.title = {
        display: true,
        text: 'ESP32 Offline - Waiting for sensor data...',
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
        // First check ESP32 connection status
        const statusResponse = await fetch('/api/esp32/status');
        const statusData = await statusResponse.json();
        
        if (!statusData.connected) {
            esp32Online = false;
            updateESP32Status(false);
            showChartOfflineState();
            return;
        }
        
        const dataPoints = document.getElementById('data-points').value;
        const stepInput = document.getElementById('step-input').value;
        const fromDate = document.getElementById('from-date').value;
        const toDate = document.getElementById('to-date').value;
        
        let url = `/api/sensor/history?sensor=${currentSensorType}&limit=${dataPoints}&step=${stepInput}`;
        
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
    
    let url = `/api/sensor/export?sensor=${currentSensorType}&limit=${dataPoints}&step=${stepInput}`;
    
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
});