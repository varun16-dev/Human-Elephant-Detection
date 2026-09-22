/**
 * Module 1: IoT Field Sensor Nodes Management & Telemetry Stream
 * Integrated IoT and Edge-AI Acoustic Early Warning System
 */

function renderSensorNodes(nodes) {
  const container = document.getElementById('nodes-container');
  if (!container) return;

  container.innerHTML = '';

  nodes.forEach(node => {
    const isAlert = node.status === 'ALERT';
    const isWarning = node.status === 'WARNING';
    const statusClass = isAlert ? 'alert' : (isWarning ? 'alert' : 'safe');
    
    const card = document.createElement('div');
    card.className = `node-card ${isAlert ? 'status-alert' : ''}`;
    
    card.innerHTML = `
      <div class="node-header">
        <div class="node-title">
          <i class="fa-solid fa-microchip" style="color: ${isAlert ? '#ef4444' : '#10b981'};"></i>
          ${node.name}
        </div>
        <span class="node-badge ${statusClass}">${node.status}</span>
      </div>

      <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.6rem;">
        <i class="fa-solid fa-location-dot"></i> ${node.location} (${node.lat.toFixed(4)}°, ${node.lng.toFixed(4)}°)
      </div>

      <div class="telemetry-metrics">
        <div class="metric-box">
          <div class="metric-label">PIR</div>
          <div class="metric-value ${node.pir ? 'danger' : ''}">
            <i class="fa-solid ${node.pir ? 'fa-person-walking-arrow-right' : 'fa-check'}"></i>
            ${node.pir ? 'DETECTED' : 'Clear'}
          </div>
        </div>

        <div class="metric-box">
          <div class="metric-label">Sound</div>
          <div class="metric-value ${node.acoustic_db > 75.0 ? 'danger' : ''}">
            <i class="fa-solid fa-volume-high"></i> ${node.acoustic_db}
          </div>
        </div>

        <div class="metric-box">
          <div class="metric-label">Sound Classification</div>
          <div class="metric-value ${isAlert ? 'danger' : ''}" style="font-size: 0.8rem;">
            ${node.sound_class} (${node.confidence}%)
          </div>
        </div>
      </div>

      <div class="node-footer">
        <div style="display: flex; align-items: center; gap: 0.4rem;">
          <i class="fa-solid fa-solar-panel" style="color: #f59e0b;"></i>
          <span>Solar: ${node.solar_v}V</span>
          <div class="battery-bar" style="margin-left: 0.4rem;">
            <div class="battery-fill" style="width: ${node.battery}%;"></div>
          </div>
        </div>
        <div style="display: flex; align-items: center; gap: 0.6rem;">
          <button style="font-size: 0.72rem; padding: 0.25rem 0.5rem; background: ${isAlert ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.12)'}; border: 1px solid ${isAlert ? '#ef4444' : 'rgba(16, 185, 129, 0.3)'}; color: ${isAlert ? '#ef4444' : '#10b981'}; border-radius: 4px; cursor: pointer;" onclick="toggleNodeAlert('${node.id}', ${isAlert})">
            ${isAlert ? '🔄 Reset to Safe' : '⚡ Trigger Telemetry Signal'}
          </button>
        </div>
      </div>
    `;

    container.appendChild(card);
  });
}

function toggleNodeAlert(nodeId, isCurrentlyAlert) {
  fetch('/api/simulate-node-alert', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_id: nodeId, reset: isCurrentlyAlert })
  })
  .then(res => res.json())
  .then(() => {
    if (typeof fetchStatusAndNodes === 'function') {
      fetchStatusAndNodes();
    }
  });
}

function triggerSelectedNodeAlert(nodeId) {
  if (!nodeId) return;
  const isReset = nodeId === 'RESET';
  fetch('/api/simulate-node-alert', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_id: isReset ? null : nodeId, reset: isReset })
  })
  .then(res => res.json())
  .then(() => {
    if (typeof fetchStatusAndNodes === 'function') {
      fetchStatusAndNodes();
    }
  });
}

