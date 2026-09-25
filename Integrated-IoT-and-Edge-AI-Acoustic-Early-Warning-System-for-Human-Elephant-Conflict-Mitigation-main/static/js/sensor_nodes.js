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
    const isOffline = node.status === 'OFFLINE';
    const statusClass = isAlert ? 'alert' : (isOffline ? 'offline' : (isWarning ? 'alert' : 'safe'));
    
    const card = document.createElement('div');
    card.className = `node-card ${isAlert ? 'status-alert' : ''} ${isOffline ? 'status-offline' : ''}`;
    
    const isNode1 = node.id === 'ESP32-NODE-01';

    card.innerHTML = `
      <div class="node-header">
        <div class="node-title">
          <i class="fa-solid fa-microchip" style="color: ${isAlert ? '#ef4444' : (isOffline ? '#94a3b8' : '#10b981')};"></i>
          ${node.name}
        </div>
        <span class="node-badge ${statusClass}">${isOffline ? 'OFFLINE' : node.status}</span>
      </div>

      <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.6rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.3rem;">
        <div>
          <i class="fa-solid fa-location-dot" style="color: ${isNode1 ? '#38bdf8' : 'var(--text-muted)'};"></i> 
          <span>${node.location}</span> 
          <span style="font-family: monospace; color: ${isOffline ? '#64748b' : '#38bdf8'}; font-weight: 600;">(${node.lat.toFixed(5)}° N, ${node.lng.toFixed(5)}° E)</span>
        </div>
        ${isNode1 
          ? '<span style="font-size: 0.68rem; padding: 1px 6px; background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 10px; font-weight: bold;"><i class="fa-solid fa-satellite-dish"></i> LIVE GPS</span>' 
          : (isOffline ? '<span style="font-size: 0.68rem; padding: 1px 6px; background: rgba(148, 163, 184, 0.12); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.25); border-radius: 10px;"><i class="fa-solid fa-circle-xmark"></i> DISCONNECTED</span>' : '')}
      </div>

      <div class="telemetry-metrics">
        <div class="metric-box">
          <div class="metric-label">PIR</div>
          <div class="metric-value ${node.pir ? 'danger' : ''}">
            ${isOffline 
              ? '<span style="color: #64748b; font-size: 0.85rem;"><i class="fa-solid fa-power-off"></i> OFFLINE</span>' 
              : `<i class="fa-solid ${node.pir ? 'fa-person-walking-arrow-right' : 'fa-check'}"></i> ${node.pir ? 'DETECTED' : 'Clear'}`}
          </div>
        </div>

        <div class="metric-box">
          <div class="metric-label">Sound</div>
          <div class="metric-value ${node.acoustic_db > 75.0 ? 'danger' : ''}">
            ${isOffline 
              ? '<span style="color: #64748b; font-size: 0.85rem;"><i class="fa-solid fa-volume-xmark"></i> OFFLINE</span>' 
              : `<i class="fa-solid fa-volume-high"></i> ${node.acoustic_db} dB`}
          </div>
        </div>
      </div>

      <div class="node-footer">
        ${isOffline 
          ? `<div style="display: flex; align-items: center; gap: 0.4rem; color: #64748b;">
               <i class="fa-solid fa-power-off"></i>
               <span>Power: Disconnected</span>
             </div>`
          : `<div style="display: flex; align-items: center; gap: 0.45rem; color: #10b981; font-weight: 500;">
               <i class="fa-solid fa-plug" style="color: #10b981;"></i>
               <span>Power: 5V DC / USB (Mains Continuous)</span>
             </div>`}
        <div style="display: flex; align-items: center; gap: 0.6rem;">
          <button style="font-size: 0.72rem; padding: 0.25rem 0.5rem; background: ${isAlert ? 'rgba(239, 68, 68, 0.2)' : (isOffline ? 'rgba(100, 116, 139, 0.15)' : 'rgba(16, 185, 129, 0.12)')}; border: 1px solid ${isAlert ? '#ef4444' : (isOffline ? 'rgba(100, 116, 139, 0.3)' : 'rgba(16, 185, 129, 0.3)')}; color: ${isAlert ? '#ef4444' : (isOffline ? '#94a3b8' : '#10b981')}; border-radius: 4px; cursor: pointer;" onclick="toggleNodeAlert('${node.id}', ${isAlert})">
            ${isAlert ? '🔄 Reset to Safe' : (isOffline ? '⚡ Simulate Telemetry Test' : '⚡ Trigger Telemetry Signal')}
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

