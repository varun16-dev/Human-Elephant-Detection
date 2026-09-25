/**
 * Module 5: Decision Support System (DSS) & Actuator Controller
 * Integrated IoT and Edge-AI Acoustic Early Warning System
 */

// ============================================================
// BIO-ACOUSTIC AUDIO PLAYER
// ============================================================
// Persistent audio object for bio-acoustic speaker
// ============================================================

let bioAcousticAudio = null;
let bioAcousticPlaying = false;

// ============================================================
// SIREN AUDIO PLAYER
// ============================================================
// Persistent audio object for high-decibel siren
// ============================================================

let sirenAudio = null;
let sirenPlaying = false;

// Initialize bio-acoustic and siren toggle event listeners
document.addEventListener('DOMContentLoaded', function() {
  const toggleBio = document.getElementById('toggle-bio');
  if (toggleBio) {
    toggleBio.addEventListener('change', function() {
      if (this.checked) {
        playBioAcoustic();
      } else {
        stopBioAcoustic();
      }
    });
  }
  
  const toggleSiren = document.getElementById('toggle-siren');
  if (toggleSiren) {
    toggleSiren.addEventListener('change', function() {
      if (this.checked) {
        playSiren();
      } else {
        stopSiren();
      }
    });
  }

  // Immediately synchronize deterrent states on load
  fetch('/api/status')
    .then(res => res.json())
    .then(data => {
      if (data && data.deterrent_status) {
        updateDeterrentUI(data.deterrent_status);
      }
    })
    .catch(err => console.log('Initial deterrent sync:', err));
});

function initBioAcousticAudio() {
  if (!bioAcousticAudio) {
    bioAcousticAudio = new Audio('/static/audio/bio-acoustic.mp3');
    bioAcousticAudio.loop = true;
    
    // Handle audio errors
    bioAcousticAudio.addEventListener('error', (e) => {
      console.error('[BIO-ACOUSTIC] Audio load error:', e);
      bioAcousticPlaying = false;
      updateBioAcousticUI(false);
    });
    
    // Handle audio ending (shouldn't happen with loop, but as fallback)
    bioAcousticAudio.addEventListener('ended', () => {
      if (bioAcousticPlaying) {
        bioAcousticAudio.currentTime = 0;
        bioAcousticAudio.play().catch(err => {
          console.error('[BIO-ACOUSTIC] Playback error:', err);
          bioAcousticPlaying = false;
          updateBioAcousticUI(false);
        });
      }
    });
  }
}

function playBioAcoustic() {
  initBioAcousticAudio();
  
  if (bioAcousticAudio) {
    bioAcousticAudio.currentTime = 0;
    bioAcousticAudio.play().then(() => {
      bioAcousticPlaying = true;
      updateBioAcousticUI(true);
      console.log('[BIO-ACOUSTIC] Audio started');
    }).catch(err => {
      console.error('[BIO-ACOUSTIC] Playback failed:', err);
      bioAcousticPlaying = false;
      updateBioAcousticUI(false);
      alert('Failed to play bio-acoustic audio');
    });
  }
}

function stopBioAcoustic() {
  if (bioAcousticAudio) {
    bioAcousticAudio.pause();
    bioAcousticAudio.currentTime = 0;
    bioAcousticPlaying = false;
    updateBioAcousticUI(false);
    console.log('[BIO-ACOUSTIC] Audio stopped');
  }
}

function updateBioAcousticUI(isActive) {
  const cardBio = document.getElementById('card-bio');
  const toggleBio = document.getElementById('toggle-bio');
  const statusBio = document.getElementById('status-bio');
  
  if (cardBio && toggleBio) {
    if (isActive) {
      cardBio.classList.add('active');
      toggleBio.checked = true;
      if (statusBio) {
        statusBio.textContent = 'ACTIVE';
        statusBio.className = 'node-badge alert';
      }
    } else {
      cardBio.classList.remove('active');
      toggleBio.checked = false;
      if (statusBio) {
        statusBio.textContent = 'STANDBY';
        statusBio.className = 'node-badge safe';
      }
    }
  }
}

// ============================================================
// SIREN AUDIO FUNCTIONS
// ============================================================

function initSirenAudio() {
  if (!sirenAudio) {
    sirenAudio = new Audio('/static/audio/siren.mp3');
    sirenAudio.loop = true;
    
    // Handle audio errors
    sirenAudio.addEventListener('error', (e) => {
      console.error('[SIREN] Audio load error:', e);
      sirenPlaying = false;
      updateSirenUI(false);
    });
    
    // Handle audio ending (shouldn't happen with loop, but as fallback)
    sirenAudio.addEventListener('ended', () => {
      if (sirenPlaying) {
        sirenAudio.currentTime = 0;
        sirenAudio.play().catch(err => {
          console.error('[SIREN] Playback error:', err);
          sirenPlaying = false;
          updateSirenUI(false);
        });
      }
    });
  }
}

function playSiren() {
  initSirenAudio();
  
  if (sirenAudio) {
    sirenAudio.currentTime = 0;
    sirenAudio.play().then(() => {
      sirenPlaying = true;
      updateSirenUI(true);
      console.log('[SIREN] Audio started');
    }).catch(err => {
      console.error('[SIREN] Playback failed:', err);
      sirenPlaying = false;
      updateSirenUI(false);
      alert('Failed to play siren audio');
    });
  }
}

function stopSiren() {
  if (sirenAudio) {
    sirenAudio.pause();
    sirenAudio.currentTime = 0;
    sirenPlaying = false;
    updateSirenUI(false);
    console.log('[SIREN] Audio stopped');
  }
}

function updateSirenUI(isActive) {
  const cardSiren = document.getElementById('card-siren');
  const toggleSiren = document.getElementById('toggle-siren');
  const statusSiren = document.getElementById('status-siren');
  
  if (cardSiren && toggleSiren) {
    if (isActive) {
      cardSiren.classList.add('active');
      toggleSiren.checked = true;
      if (statusSiren) {
        statusSiren.textContent = 'ACTIVE';
        statusSiren.className = 'node-badge alert';
      }
    } else {
      cardSiren.classList.remove('active');
      toggleSiren.checked = false;
      if (statusSiren) {
        statusSiren.textContent = 'STANDBY';
        statusSiren.className = 'node-badge safe';
      }
    }
  }
}

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
  // Special handling for bio-acoustic speaker (laptop-only feature)
  if (device === 'bio_acoustic') {
    const toggleBio = document.getElementById('toggle-bio');
    if (toggleBio) {
      if (toggleBio.checked) {
        // Turn ON - play audio
        playBioAcoustic();
      } else {
        // Turn OFF - stop audio
        stopBioAcoustic();
      }
    }
    return;
  }
  
  // Special handling for siren (laptop-only feature)
  if (device === 'siren') {
    const toggleSiren = document.getElementById('toggle-siren');
    if (toggleSiren) {
      if (toggleSiren.checked) {
        // Turn ON - play audio
        playSiren();
      } else {
        // Turn OFF - stop audio
        stopSiren();
      }
    }
    return;
  }
  
  if (device === 'strobe_light') {
    const toggleStrobe = document.getElementById('toggle-strobe');
    const isChecked = toggleStrobe ? toggleStrobe.checked : false;
    const action = isChecked ? 'on' : 'off';

    // Immediately update UI for instant visual response (blinking if on, off if off)
    updateDeterrentUI({ strobe_light_active: isChecked });

    fetch('/api/deterrent/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device: 'strobe_light', action: action })
    })
    .then(res => {
      if (!res.ok) {
        return res.json().then(err => {
          throw new Error(err.message || 'Failed to control strobe light');
        });
      }
      return res.json();
    })
    .then(data => {
      if (data.status === 'success') {
        updateDeterrentUI(data.deterrent_state);
        console.log(`[DETERRENT] Strobe light set to ${action}:`, data.message);
      } else {
        console.error(`[DETERRENT] Error toggling strobe light:`, data.message);
        revertDeterrentUI('strobe_light');
        alert(`Error: ${data.message}`);
      }
    })
    .catch(err => {
      console.error("Deterrent trigger error:", err);
      revertDeterrentUI('strobe_light');
      alert(`Failed to control strobe light: ${err.message}`);
    });
    return;
  }
  
  // Other devices send to backend
  fetch('/api/deterrent/trigger', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device: device, action: 'toggle' })
  })
  .then(res => {
    if (!res.ok) {
      return res.json().then(err => {
        throw new Error(err.message || 'Failed to toggle device');
      });
    }
    return res.json();
  })
  .then(data => {
    if (data.status === 'success') {
      updateDeterrentUI(data.deterrent_state);
      console.log(`[DETERRENT] ${device} toggled successfully:`, data.message);
    } else {
      console.error(`[DETERRENT] Error toggling ${device}:`, data.message);
      // Revert UI state on error
      revertDeterrentUI(device);
      alert(`Error: ${data.message}`);
    }
  })
  .catch(err => {
    console.error("Deterrent trigger error:", err);
    // Revert UI state on error
    revertDeterrentUI(device);
    alert(`Failed to control ${device}: ${err.message}`);
  });
}

function revertDeterrentUI(device) {
  // Revert the toggle to its previous state
  // Bio-acoustic is handled locally, no revert needed
  if (device === 'strobe_light') {
    const toggleStrobe = document.getElementById('toggle-strobe');
    if (toggleStrobe) {
      toggleStrobe.checked = !toggleStrobe.checked;
      updateDeterrentUI({ strobe_light_active: toggleStrobe.checked });
    }
  } else if (device === 'siren') {
    const toggleSiren = document.getElementById('toggle-siren');
    if (toggleSiren) {
      toggleSiren.checked = !toggleSiren.checked;
    }
  }
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

  // Bio-acoustic and siren are now controlled locally (laptop-only), skip backend sync
  // UI is updated directly by playBioAcoustic/stopBioAcoustic and playSiren/stopSiren functions
  
  if (cardStrobe && toggleStrobe) {
    if (state.strobe_light_active) {
      cardStrobe.classList.add('active');
      cardStrobe.classList.add('strobe-active'); // Add pulsing animation
      toggleStrobe.checked = true;
      if (statusStrobe) { 
        statusStrobe.textContent = 'ACTIVE (Manual)'; 
        statusStrobe.className = 'node-badge alert'; 
      }
    } else {
      cardStrobe.classList.remove('active');
      cardStrobe.classList.remove('strobe-active'); // Remove pulsing animation
      toggleStrobe.checked = false;
      if (statusStrobe) { 
        statusStrobe.textContent = 'STANDBY'; 
        statusStrobe.className = 'node-badge safe'; 
      }
    }
  }
}

function triggerAllDeterrents() {
  // Turn on bio-acoustic (local laptop playback)
  playBioAcoustic();
  
  // Turn on strobe light (hardware control)
  fetch('/api/deterrent/trigger', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device: 'strobe_light', action: 'on' })
  })
  .then(res => {
    if (!res.ok) {
      return res.json().then(err => {
        throw new Error(err.message || 'Failed to control strobe light');
      });
    }
    return res.json();
  })
  .then(data => {
    if (data.status === 'success') {
      updateDeterrentUI(data.deterrent_state);
      console.log("[EMERGENCY] Strobe light activated:", data.message);
    } else {
      console.error("[EMERGENCY] Strobe light error:", data.message);
    }
  })
  .catch(err => console.error("Strobe light error:", err));
  
  // Turn on siren (local laptop playback)
  playSiren();
  
  // Show emergency alert after all commands
  setTimeout(() => {
    alert("⚡ EMERGENCY OVERRIDE: ALL DETERRENT ACTUATORS (Bio-Acoustic Laptop + Strobe Hardware + Siren Laptop) ACTIVATED FOR SECTOR A!");
  }, 500);
}

async function broadcastSMSAlert() {
  try {
    const response = await fetch('/api/alert/whatsapp', { method: 'POST' });
    const result = await response.json();
    if (result.status === 'success') {
      alert("📱 WhatsApp Alert Dispatched Successfully!");
    } else {
      alert("Failed to send WhatsApp alert: " + (result.message || "Unknown error"));
    }
  } catch (err) {
    console.error("Error sending WhatsApp:", err);
    alert("Error sending WhatsApp alert.");
  }
}

// Periodically sync deterrent state with server to reflect ESP32 hardware state
setInterval(() => {
  fetch('/api/status')
    .then(res => res.json())
    .then(data => {
      if (data.deterrent_status) {
        updateDeterrentUI(data.deterrent_status);
      }
    })
    .catch(err => console.error("Deterrent state sync error:", err));
}, 3000); // Sync every 3 seconds
