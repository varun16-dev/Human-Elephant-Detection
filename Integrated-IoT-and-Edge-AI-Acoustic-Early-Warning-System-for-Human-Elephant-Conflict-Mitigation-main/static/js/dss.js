/**
 * Module 5: Decision Support System (DSS) & Actuator Controller
 * Integrated IoT and Edge-AI Acoustic Early Warning System
 */

function fetchDSSRecommendations() {
  fetch('/api/dss/recommendations')
    .then(res => res.json())
    .then(data => {
      renderRecommendations(data.recommended_actions);
    })
    .catch(err => console.error("DSS fetch error:", err));
}

function renderRecommendations(actions) {
  const container = document.getElementById('dss-recommendations-list');
  if (!container) return;

  container.innerHTML = '';

  actions.forEach(item => {
    const isCritical = item.priority === 'HIGH';
    const div = document.createElement('div');
    div.className = `recommendation-item ${isCritical ? 'critical' : ''}`;

    div.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
        <span style="font-weight: 700; font-size: 0.75rem; color: ${isCritical ? '#ef4444' : '#10b981'};">
          PRIORITY: ${item.priority}
        </span>
        <span class="header-tag" style="background: rgba(255,255,255,0.06); font-size: 0.7rem;">${item.status}</span>
      </div>
      <div style="font-weight: 500; color: var(--text-main);">${item.action}</div>
    `;

    container.appendChild(div);
  });
}

function toggleDeterrent(device) {
  fetch('/api/deterrent/trigger', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device: device, action: 'toggle' })
  })
  .then(res => res.json())
  .then(data => {
    updateDeterrentUI(data.deterrent_state);
  })
  .catch(err => console.error("Deterrent trigger error:", err));
}

function updateDeterrentUI(state) {
  // Update Cards & Status Tags
  const cardBio = document.getElementById('card-bio');
  const cardStrobe = document.getElementById('card-strobe');
  const cardSiren = document.getElementById('card-siren');

  const toggleBio = document.getElementById('toggle-bio');
  const toggleStrobe = document.getElementById('toggle-strobe');
  const toggleSiren = document.getElementById('toggle-siren');

  const statusBio = document.getElementById('status-bio');
  const statusStrobe = document.getElementById('status-strobe');
  const statusSiren = document.getElementById('status-siren');

  const strobeOverlay = document.getElementById('strobe-overlay');

  if (cardBio && toggleBio) {
    if (state.bio_acoustic_active) {
      cardBio.classList.add('active');
      toggleBio.checked = true;
      if (statusBio) { statusBio.textContent = 'ACTIVE (Tiger Roar)'; statusBio.className = 'node-badge alert'; }
    } else {
      cardBio.classList.remove('active');
      toggleBio.checked = false;
      if (statusBio) { statusBio.textContent = 'STANDBY'; statusBio.className = 'node-badge safe'; }
    }
  }

  if (cardStrobe && toggleStrobe) {
    if (state.strobe_light_active) {
      cardStrobe.classList.add('active');
      toggleStrobe.checked = true;
      if (statusStrobe) { statusStrobe.textContent = 'ACTIVE'; statusStrobe.className = 'node-badge alert'; }
    } else {
      cardStrobe.classList.remove('active');
      toggleStrobe.checked = false;
      if (statusStrobe) { statusStrobe.textContent = 'STANDBY'; statusStrobe.className = 'node-badge safe'; }
    }
  }

  if (cardSiren && toggleSiren) {
    if (state.siren_active) {
      cardSiren.classList.add('active');
      toggleSiren.checked = true;
      if (statusSiren) { statusSiren.textContent = 'SIREN ALARM ACTIVE'; statusSiren.className = 'node-badge alert'; }
    } else {
      cardSiren.classList.remove('active');
      toggleSiren.checked = false;
      if (statusSiren) { statusSiren.textContent = 'STANDBY'; statusSiren.className = 'node-badge safe'; }
    }
  }
}

function triggerAllDeterrents() {
  fetch('/api/deterrent/trigger', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device: 'bio_acoustic', action: 'on' })
  });
  fetch('/api/deterrent/trigger', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device: 'strobe_light', action: 'on' })
  });
  fetch('/api/deterrent/trigger', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device: 'siren', action: 'on' })
  })
  .then(res => res.json())
  .then(data => {
    updateDeterrentUI(data.deterrent_state);
    alert("⚡ EMERGENCY OVERRIDE: ALL DETERRENT ACTUATORS (Bio-Acoustic + Strobe + Siren) ACTIVATED FOR SECTOR A!");
  });
}

function broadcastSMSAlert() {
  alert("📱 SMS ALERT DISPATCHED: 'EMERGENCY WARNING - Elephant herd detected near Jigani-Anekal boundary. Stay indoors & avoid farm roads.' Sent to 342 residents.");
}
