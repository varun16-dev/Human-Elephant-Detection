/**
 * Camera Elephant Detection Integration Module
 * Department of AI & ML, Sri Sairam College of Engineering
 */

// Global State for Camera Detection and History Table
let historyData = [];
let filteredData = [];
let galleryImages = [];
let lastRealDetectionId = null; // Track last real detection to avoid duplicate popups
let lastHistoryDataJson = ''; // Cache to avoid table flickering
let lastGalleryDataJson = ''; // Cache to avoid gallery flickering

// Pagination state
let currentPage = 1;
const rowsPerPage = 10;

// Sorting state
let sortColumn = 'timestamp';
let sortAscending = false; // default latest first

document.addEventListener('DOMContentLoaded', () => {
  console.log("Camera Detection Integration Initializing...");

  // Initialize camera configuration and active source badge
  syncCameraConfiguration();

  // Initialize and start live camera status polling (every 2 seconds)
  pollCameraStatus();
  setInterval(pollCameraStatus, 2000);

  // Initialize data load when switching tabs or loading page
  loadHistoryData();
  loadGalleryImages();

  // Start live polling for history data and gallery (every 3 seconds)
  setInterval(loadHistoryData, 3000);
  setInterval(loadGalleryImages, 5000);
  
  // Start monitoring for real elephant detections
  startRealDetectionMonitoring();
  
  // Check for real detection immediately on load
  checkForRealDetection();

  // Set up search and filter event listeners
  const searchInput = document.getElementById('camera-search');
  if (searchInput) {
    searchInput.addEventListener('input', handleSearchAndFilter);
  }

  const filterSelect = document.getElementById('camera-filter');
  if (filterSelect) {
    const urlParams = new URLSearchParams(window.location.search);
    const filterVal = urlParams.get('filter');
    if (filterVal) filterSelect.value = filterVal;

    filterSelect.addEventListener('change', (e) => {
      const url = new URL(window.location);
      if (e.target.value === 'all') {
        url.searchParams.delete('filter');
      } else {
        url.searchParams.set('filter', e.target.value);
      }
      window.history.replaceState(window.history.state, '', url);
      handleSearchAndFilter();
    });
  }

  // Set up Modal Close Listener
  const modal = document.getElementById('image-modal');
  const modalClose = document.getElementById('modal-close-btn');
  if (modalClose && modal) {
    modalClose.addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });
  }
});

// ==========================================
// 1. LIVE CAMERA STATUS & DETECTION FEED
// ==========================================
function pollCameraStatus() {
  if (!document.getElementById('camera-tab')?.classList.contains('active')) return;
  fetch('/api/camera/status')
    .then(res => {
      if (!res.ok) throw new Error('API server unavailable');
      return res.json();
    })
    .then(data => {
      updateLiveStatusUI(data);
    })
    .catch(err => {
      console.warn("Error polling camera status:", err);
      // Graceful degradation / offline fallback
      updateLiveStatusUI({
        camera_status: "OFFLINE",
        detection_status: "Flask API or Detector offline",
        elephant_count: 0,
        confidence: "0.0%",
        last_detection_time: "N/A",
        latest_detection_image: "N/A"
      });
    });
}

// Active camera view mode ('live' or 'bbox')
let currentCameraViewMode = 'live';

window.switchCameraView = function(mode) {
  currentCameraViewMode = mode;
  const livePanel = document.getElementById('panel-live-stream');
  const bboxPanel = document.getElementById('panel-bbox-view');
  const btnLive = document.getElementById('btn-stream-mode');
  const btnBbox = document.getElementById('btn-bbox-mode');
  
  if (mode === 'live') {
    if (livePanel) livePanel.style.display = 'flex';
    if (bboxPanel) bboxPanel.style.display = 'none';
    if (btnLive) {
      btnLive.style.background = 'rgba(6, 182, 212, 0.25)';
      btnLive.style.borderColor = '#06b6d4';
      btnLive.style.color = '#fff';
    }
    if (btnBbox) {
      btnBbox.style.background = '';
      btnBbox.style.borderColor = '';
      btnBbox.style.color = '';
    }
  } else {
    if (livePanel) livePanel.style.display = 'none';
    if (bboxPanel) bboxPanel.style.display = 'block';
    if (btnBbox) {
      btnBbox.style.background = 'rgba(6, 182, 212, 0.25)';
      btnBbox.style.borderColor = '#06b6d4';
      btnBbox.style.color = '#fff';
    }
    if (btnLive) {
      btnLive.style.background = '';
      btnLive.style.borderColor = '';
      btnLive.style.color = '';
    }
  }
};

// Global set of broken image URLs to prevent recurring 404 image loads
const brokenImageUrls = new Set();

window.handleThumbError = function(img, url) {
  if (url) brokenImageUrls.add(url);
  img.style.display = 'none';
  const parent = img.parentElement;
  if (parent) {
    let fallback = parent.querySelector('.no-image-text');
    if (!fallback) {
      fallback = document.createElement('span');
      fallback.className = 'no-image-text';
      fallback.textContent = '—';
      parent.appendChild(fallback);
    } else {
      fallback.style.display = 'inline';
    }
  }
};

let streamRetryTimeout = null;
window.fallbackToProxyStream = function(img) {
  if (streamRetryTimeout) return;
  console.warn("[STREAM] Video stream connection interrupted; retrying in 2 seconds...");
  streamRetryTimeout = setTimeout(() => {
    if (img) img.src = '/api/camera/stream?t=' + Date.now();
    streamRetryTimeout = null;
  }, 2000);
};

window.reloadLiveStream = function() {
  const streamImg = document.getElementById('live-stream-player');
  if (streamImg) {
    fetch('/api/camera/config')
      .then(r => r.json())
      .then(cfg => {
        updateActiveCameraUI(cfg);
        streamImg.src = '/api/camera/stream?t=' + Date.now();
      })
      .catch(() => {
        streamImg.src = '/api/camera/stream?t=' + Date.now();
      });
  }
};

function syncCameraConfiguration() {
  fetch('/api/camera/config')
    .then(r => r.json())
    .then(cfg => {
      updateActiveCameraUI(cfg);
    })
    .catch(e => console.warn('Camera config sync notice:', e));
}

window.quickSwitchCamera = function(idx) {
  updateCameraSwitchPillUI(idx);
  fetch('/api/camera/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ camera_source: idx })
  })
  .then(r => r.json())
  .then(res => {
    console.log('[CAMERA] Switched to:', res);
    syncCameraConfiguration();
    const streamImg = document.getElementById('live-stream-player');
    if (streamImg) {
      streamImg.src = '/api/camera/stream?t=' + Date.now();
    }
  })
  .catch(err => {
    console.error('Error switching camera:', err);
  });
};

function updateCameraSwitchPillUI(src) {
  const btn0 = document.getElementById('btn-quick-cam-0');
  const btn1 = document.getElementById('btn-quick-cam-1');
  const btnCustom = document.getElementById('btn-quick-cam-custom');
  const sub0 = document.getElementById('sub-btn-cam-0');
  const sub1 = document.getElementById('sub-btn-cam-1');
  const subCustom = document.getElementById('sub-btn-cam-custom');

  const isCustom = (src !== 0 && src !== 1 && src !== '0' && src !== '1');

  if (btn0) {
    if (src == 0) {
      btn0.style.background = '#06b6d4';
      btn0.style.color = '#020617';
      btn0.style.fontWeight = '700';
    } else {
      btn0.style.background = 'transparent';
      btn0.style.color = '#94a3b8';
      btn0.style.fontWeight = 'normal';
    }
  }

  if (btn1) {
    if (src == 1) {
      btn1.style.background = '#06b6d4';
      btn1.style.color = '#020617';
      btn1.style.fontWeight = '700';
    } else {
      btn1.style.background = 'transparent';
      btn1.style.color = '#94a3b8';
      btn1.style.fontWeight = 'normal';
    }
  }

  if (btnCustom) {
    if (isCustom) {
      btnCustom.style.background = '#06b6d4';
      btnCustom.style.color = '#020617';
      btnCustom.style.fontWeight = '700';
    } else {
      btnCustom.style.background = 'transparent';
      btnCustom.style.color = '#94a3b8';
      btnCustom.style.fontWeight = 'normal';
    }
  }

  if (sub0) {
    sub0.style.borderColor = (src == 0 ? '#06b6d4' : '');
    sub0.style.color = (src == 0 ? '#06b6d4' : '');
  }
  if (sub1) {
    sub1.style.borderColor = (src == 1 ? '#06b6d4' : '');
    sub1.style.color = (src == 1 ? '#06b6d4' : '');
  }
  if (subCustom) {
    subCustom.style.borderColor = (isCustom ? '#06b6d4' : 'rgba(6,182,212,0.3)');
    subCustom.style.color = (isCustom ? '#38bdf8' : 'var(--accent-cyan)');
    subCustom.style.background = (isCustom ? 'rgba(6,182,212,0.2)' : '');
  }
}

function updateActiveCameraUI(cfg) {
  if (!cfg) return;
  const badgeEl = document.getElementById('active-cam-badge');
  const typeEl = document.getElementById('active-cam-type');
  const noteEl = document.getElementById('cam-hardware-note');
  
  const isUsb = cfg.is_usb || typeof cfg.camera_source === 'number' || (typeof cfg.camera_source === 'string' && /^\d+$/.test(cfg.camera_source));
  const src = cfg.camera_source;
  const isLaptop = (src === 0 || src === '0');
  const isExternal = (src === 1 || src === '1');
  const camTitle = isLaptop ? 'Laptop Webcam (Cam 0)' : (isExternal ? 'External HD Webcam (Cam 1)' : (cfg.camera_name || `Camera ${src}`));

  updateCameraSwitchPillUI(src);

  if (badgeEl) {
    badgeEl.innerHTML = `<i class="fa-solid ${isUsb ? (isLaptop ? 'fa-laptop' : 'fa-camera') : 'fa-wifi'}"></i> ${isLaptop ? 'Laptop Cam 0' : (isExternal ? 'External Cam 1' : `IP Camera`)}`;
  }
  if (typeEl) {
    typeEl.textContent = isLaptop ? 'Laptop Webcam' : (isExternal ? 'External USB' : (isUsb ? `Camera ${src}` : 'ESP32-CAM / IP Stream'));
  }
  if (noteEl) {
    noteEl.innerHTML = `<strong>Active Camera:</strong> <span style="color: #06b6d4; font-weight: 700;">${camTitle}</span> &bull; Frames from this camera are actively processed by AI Elephant Detection.`;
  }
}

let savedCustomIPAddress = '';

window.openCameraModal = function() {
  openCustomIPModal();
};

window.openCustomIPModal = function() {
  const modal = document.getElementById('camera-modal');
  if (modal) {
    modal.style.display = 'flex';
    switchCameraModalTab('custom');
    
    // Clear test feedback
    const feedback = document.getElementById('custom-ip-test-feedback');
    if (feedback) feedback.style.display = 'none';

    fetch('/api/camera/config')
      .then(r => r.json())
      .then(data => {
        const customInput = document.getElementById('custom-cam-input');
        if (customInput) {
          const isNetwork = (data.camera_source !== 0 && data.camera_source !== 1 && data.camera_source !== '0' && data.camera_source !== '1');
          if (isNetwork && data.camera_source) {
            customInput.value = data.camera_source;
            savedCustomIPAddress = data.camera_source;
          } else if (data.saved_custom_ip) {
            customInput.value = data.saved_custom_ip;
            savedCustomIPAddress = data.saved_custom_ip;
          } else if (!customInput.value || customInput.value === '0' || customInput.value === '1') {
            customInput.value = savedCustomIPAddress || '192.168.4.1';
          }
          customInput.focus();
          customInput.select();
        }
      })
      .catch(() => {
        const customInput = document.getElementById('custom-cam-input');
        if (customInput && (!customInput.value || customInput.value === '0' || customInput.value === '1')) {
          customInput.value = savedCustomIPAddress || '192.168.4.1';
        }
      });
  }
};

window.closeCameraModal = function() {
  const modal = document.getElementById('camera-modal');
  if (modal) modal.style.display = 'none';
};

window.switchCameraModalTab = function(tab) {
  const tabCustom = document.getElementById('modal-tab-custom-ip');
  const tabUsb = document.getElementById('modal-tab-usb-cams');
  const btnCustom = document.getElementById('tab-btn-custom-ip');
  const btnUsb = document.getElementById('tab-btn-usb-cams');

  if (tab === 'custom') {
    if (tabCustom) tabCustom.style.display = 'block';
    if (tabUsb) tabUsb.style.display = 'none';
    if (btnCustom) {
      btnCustom.style.background = 'rgba(6, 182, 212, 0.2)';
      btnCustom.style.borderColor = '#06b6d4';
      btnCustom.style.color = '#38bdf8';
      btnCustom.style.fontWeight = '700';
    }
    if (btnUsb) {
      btnUsb.style.background = 'transparent';
      btnUsb.style.borderColor = 'rgba(255,255,255,0.1)';
      btnUsb.style.color = '#94a3b8';
      btnUsb.style.fontWeight = 'normal';
    }
  } else {
    if (tabCustom) tabCustom.style.display = 'none';
    if (tabUsb) tabUsb.style.display = 'block';
    if (btnUsb) {
      btnUsb.style.background = 'rgba(6, 182, 212, 0.2)';
      btnUsb.style.borderColor = '#06b6d4';
      btnUsb.style.color = '#38bdf8';
      btnUsb.style.fontWeight = '700';
    }
    if (btnCustom) {
      btnCustom.style.background = 'transparent';
      btnCustom.style.borderColor = 'rgba(255,255,255,0.1)';
      btnCustom.style.color = '#94a3b8';
      btnCustom.style.fontWeight = 'normal';
    }
    loadAvailableCameraDevices();
  }
};

window.applyIPPreset = function(suffix) {
  const customInput = document.getElementById('custom-cam-input');
  if (!customInput) return;
  let val = customInput.value.trim();
  let ipOnly = val.replace(/^https?:\/\//i, '').replace(/^rtsp:\/\//i, '').split('/')[0].split(':')[0];
  if (!ipOnly || ipOnly === '0' || ipOnly === '1') ipOnly = '192.168.4.1';
  
  if (suffix.startsWith(':') || suffix.startsWith('/')) {
    customInput.value = `http://${ipOnly}${suffix}`;
  } else {
    customInput.value = suffix;
  }
  testCustomIPConnection();
};

window.testCustomIPConnection = function() {
  const customInput = document.getElementById('custom-cam-input');
  const feedback = document.getElementById('custom-ip-test-feedback');
  const testBtn = document.getElementById('btn-test-custom-ip');
  let val = customInput ? customInput.value.trim() : '';

  if (!val) {
    alert('Please enter an IP address or stream URL to test.');
    return;
  }

  if (feedback) {
    feedback.style.display = 'block';
    feedback.style.background = 'rgba(56, 189, 248, 0.15)';
    feedback.style.border = '1px solid rgba(56, 189, 248, 0.3)';
    feedback.style.color = '#38bdf8';
    feedback.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Probing camera stream at ' + val + '...';
  }
  if (testBtn) testBtn.disabled = true;

  fetch('/api/camera/test-ip', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ip: val })
  })
  .then(r => r.json())
  .then(res => {
    if (testBtn) testBtn.disabled = false;
    if (feedback) {
      if (res.status === 'success') {
        feedback.style.background = 'rgba(34, 197, 94, 0.15)';
        feedback.style.border = '1px solid #22c55e';
        feedback.style.color = '#4ade80';
        feedback.innerHTML = `<i class="fa-solid fa-circle-check"></i> <strong>${res.message}</strong><br><span style="font-size:0.74rem; opacity:0.9;">Working Endpoint: ${res.working_url}</span>`;
        if (customInput && res.working_url) {
          customInput.value = res.working_url;
        }
      } else if (res.status === 'warning') {
        feedback.style.background = 'rgba(245, 158, 11, 0.15)';
        feedback.style.border = '1px solid #f59e0b';
        feedback.style.color = '#fbbf24';
        feedback.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <strong>Device Responded:</strong> ${res.message}`;
      } else {
        feedback.style.background = 'rgba(239, 68, 68, 0.15)';
        feedback.style.border = '1px solid #ef4444';
        feedback.style.color = '#f87171';
        feedback.innerHTML = `<i class="fa-solid fa-circle-xmark"></i> <strong>Camera Offline:</strong> ${res.message || res.error || 'Connection timed out'}`;
      }
    }
  })
  .catch(err => {
    if (testBtn) testBtn.disabled = false;
    if (feedback) {
      feedback.style.background = 'rgba(239, 68, 68, 0.15)';
      feedback.style.border = '1px solid #ef4444';
      feedback.style.color = '#f87171';
      feedback.innerHTML = `<i class="fa-solid fa-circle-xmark"></i> Test error: ${err.message}`;
    }
  });
};

window.loadAvailableCameraDevices = function() {
  const container = document.getElementById('detected-cameras-list');
  if (!container) return;
  fetch('/api/camera/config')
    .then(r => r.json())
    .then(data => {
      const activeSrc = data.camera_source;
      const devices = data.available_devices || [
        { index: 0, name: 'Laptop Webcam (Index 0)' },
        { index: 1, name: 'External HD Webcam (Index 1)' }
      ];
      
      let html = '';
      devices.forEach(dev => {
        const isCurrent = (activeSrc == dev.index);
        html += `
          <div onclick="selectCameraDevice(${dev.index})" style="display: flex; align-items: center; justify-content: space-between; padding: 0.65rem 0.85rem; background: ${isCurrent ? 'rgba(6, 182, 212, 0.2)' : 'rgba(255,255,255,0.04)'}; border: 1px solid ${isCurrent ? '#06b6d4' : 'rgba(255,255,255,0.1)'}; border-radius: 8px; cursor: pointer; transition: all 0.2s ease;">
            <div style="display: flex; align-items: center; gap: 0.6rem;">
              <i class="fa-solid fa-video" style="color: ${isCurrent ? '#06b6d4' : '#94a3b8'};"></i>
              <div>
                <strong style="font-size: 0.85rem; color: #f8fafc;">Device Index ${dev.index}: ${dev.name}</strong>
                <div style="font-size: 0.72rem; color: #94a3b8;">Click to switch immediately</div>
              </div>
            </div>
            ${isCurrent ? '<span style="font-size: 0.7rem; background: #06b6d4; color: #020617; font-weight: 700; padding: 0.2rem 0.5rem; border-radius: 4px;">ACTIVE</span>' : '<span style="font-size: 0.72rem; color: #38bdf8;">Select</span>'}
          </div>
        `;
      });
      container.innerHTML = html;
    })
    .catch(err => {
      container.innerHTML = '<div style="color: #ef4444; font-size: 0.8rem;">Could not query camera devices.</div>';
    });
};

window.selectCameraDevice = function(idx) {
  fetch('/api/camera/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ camera_source: idx })
  })
  .then(r => r.json())
  .then(res => {
    closeCameraModal();
    syncCameraConfiguration();
    reloadLiveStream();
  })
  .catch(err => alert('Failed to switch camera: ' + err.message));
};

window.saveCameraSelection = function() {
  const customInput = document.getElementById('custom-cam-input');
  let val = customInput ? customInput.value.trim() : '';
  if (!val && val !== '0') {
    alert('Please enter an IP address, stream URL, or camera index.');
    return;
  }
  
  fetch('/api/camera/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ camera_source: val })
  })
  .then(r => r.json())
  .then(res => {
    if (res.status === 'success') {
      closeCameraModal();
      syncCameraConfiguration();
      reloadLiveStream();
    } else {
      alert('Error updating camera: ' + (res.error || 'Unknown error'));
    }
  })
  .catch(err => {
    alert('Failed to connect to server: ' + err.message);
  });
};

function updateLiveStatusUI(data) {
  const statusEl = document.getElementById('cam-status-val');
  const detectionEl = document.getElementById('cam-detection-val');
  const countEl = document.getElementById('cam-count-val');
  const confidenceEl = document.getElementById('cam-confidence-val');
  const lastTimeEl = document.getElementById('cam-time-val');
  const bboxPanel = document.getElementById('panel-bbox-view');
  const btnBbox = document.getElementById('btn-bbox-mode');

  if (statusEl && statusEl.textContent !== data.camera_status) {
    statusEl.textContent = data.camera_status;
    statusEl.className = 'status-value ' + (data.camera_status === 'CONNECTED' ? 'connected' : 'disconnected');
  }

  if (detectionEl) {
    const isDet = (data.detection_status || '').includes('ELEPHANT');
    const isOff = (data.detection_status || '').includes('OFFLINE') || (data.detection_status || '').includes('offline');
    const targetClass = 'status-value ' + (isDet ? 'alert' : (isOff ? 'disconnected' : 'safe'));
    if (detectionEl.textContent !== data.detection_status) {
      detectionEl.textContent = data.detection_status;
    }
    if (detectionEl.className !== targetClass) {
      detectionEl.className = targetClass;
    }
  }

  const countStr = String(data.elephant_count ?? 0);
  if (countEl && countEl.textContent !== countStr) countEl.textContent = countStr;

  const confStr = String(data.confidence ?? '0.0%');
  if (confidenceEl && confidenceEl.textContent !== confStr) confidenceEl.textContent = confStr;

  const timeStr = String(data.last_detection_time ?? 'N/A');
  if (lastTimeEl && lastTimeEl.textContent !== timeStr) lastTimeEl.textContent = timeStr;

  // Render bounding box view only when image actually changes to prevent video/panel flashing
  if (bboxPanel) {
    const currentImg = data.latest_detection_image && data.latest_detection_image !== 'N/A' ? data.latest_detection_image : '';
    if (bboxPanel.dataset.activeImg !== currentImg) {
      bboxPanel.dataset.activeImg = currentImg;
      if (currentImg) {
        const imageUrl = `/api/detection-images/${currentImg}`;
        bboxPanel.innerHTML = `
          <img src="${imageUrl}" class="live-image-feed" id="live-feed-img" alt="Latest Detection Image" style="cursor: pointer; width: 100%; height: 100%; object-fit: contain;" onclick="openImageModal('${imageUrl}', 'Latest Detection: ${currentImg}')">
          <div class="live-image-overlay">
            <span><i class="fa-solid fa-camera"></i> LATEST ELEPHANT BOUNDING BOX</span>
            <span><i class="fa-solid fa-clock"></i> ${data.last_detection_time}</span>
          </div>
        `;
        if (btnBbox && currentCameraViewMode !== 'bbox') {
          btnBbox.innerHTML = `<i class="fa-solid fa-vector-square" style="color: #f59e0b;"></i> Bounding Box <span style="display:inline-block; width:6px; height:6px; background:#f59e0b; border-radius:50%; margin-left:3px;"></span>`;
        }
      } else {
        bboxPanel.innerHTML = `
          <div class="live-image-placeholder">
            <i class="fa-solid fa-video-slash"></i>
            <p style="font-weight: 600;">No Recent Bounding Box Image Available</p>
            <p style="font-size: 0.75rem; color: var(--text-dim);">When elephants are detected by the webcam, bounding-box images will be rendered here.</p>
          </div>
        `;
      }
    }
  }
}

// ==========================================
// 2. DETECTION HISTORY DATASET LOG
// ==========================================
function loadHistoryData() {
  if (!document.getElementById('camera-tab')?.classList.contains('active')) return;
  console.log("[DETECTION] Loading detection history from Supabase...");
  
  // Build query parameters
  const params = new URLSearchParams({
    limit: 50
  });
  
  // Get current filter value
  const filterSelect = document.getElementById('camera-filter');
  if (filterSelect && filterSelect.value && filterSelect.value !== 'all') {
    params.append('detection_type', filterSelect.value);
  }
  
  fetch(`/api/supabase/detections?${params}`)
    .then(res => {
      if (!res.ok) throw new Error('Supabase detections API unavailable');
      return res.json();
    })
    .then(data => {
      if (data.error) {
        console.error("[DETECTION] Error loading detections:", data.error);
        const tbody = document.getElementById('history-table-body');
        if (tbody) {
          tbody.innerHTML = `
            <tr>
              <td colspan="6" style="text-align: center; color: var(--status-danger); padding: 2rem;">
                <i class="fa-solid fa-triangle-exclamation" style="font-size: 1.5rem; margin-bottom: 0.5rem;"></i>
                <p style="font-weight:600;">Unable to load detection history</p>
                <p style="font-size: 0.75rem;">${data.error}</p>
              </td>
            </tr>
          `;
        }
        return;
      }
      
      const currentJson = JSON.stringify(data);
      if (currentJson === lastHistoryDataJson && filteredData.length > 0) {
        return; // Data has not changed - prevent table blinking
      }
      lastHistoryDataJson = currentJson;
      historyData = data;
      filteredData = [...historyData];
      renderHistoryTable();
    })
    .catch(err => {
      console.error("Error loading detections history:", err);
      const tbody = document.getElementById('history-table-body');
      if (tbody) {
        tbody.innerHTML = `
          <tr>
            <td colspan="6" style="text-align: center; color: var(--status-danger); padding: 2rem;">
              <i class="fa-solid fa-triangle-exclamation" style="font-size: 1.5rem; margin-bottom: 0.5rem;"></i>
              <p style="font-weight:600;">Detection History Log Unavailable</p>
              <p style="font-size: 0.75rem;">${err.message}</p>
            </td>
          </tr>
        `;
      }
    });
}

function renderHistoryTable() {
  const tbody = document.getElementById('history-table-body');
  if (!tbody) return;

  if (filteredData.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; padding: 2rem; color: var(--text-muted);">
          <i class="fa-solid fa-circle-info" style="font-size: 1.5rem; margin-bottom: 0.5rem; color: var(--text-dim);"></i>
          <p style="font-weight: 600;">No matching records found</p>
        </td>
      </tr>
    `;
    updatePaginationUI();
    return;
  }

  // Sort filteredData based on sortColumn and sortAscending
  filteredData.sort((a, b) => {
    let valA = a[sortColumn];
    let valB = b[sortColumn];

    if (sortColumn === 'timestamp') {
      // Use timestamp value directly
      valA = a.timestamp || (a.date + 'T' + a.time);
      valB = b.timestamp || (b.date + 'T' + b.time);
    } else if (sortColumn === 'count') {
      valA = parseInt(a.elephant_count) || 0;
      valB = parseInt(b.elephant_count) || 0;
    } else if (sortColumn === 'confidence') {
      valA = parseFloat(a.confidence) || 0.0;
      valB = parseFloat(b.confidence) || 0.0;
    }

    if (valA < valB) return sortAscending ? -1 : 1;
    if (valA > valB) return sortAscending ? 1 : -1;
    return 0;
  });

  // Handle Pagination
  const startIndex = (currentPage - 1) * rowsPerPage;
  const endIndex = startIndex + rowsPerPage;
  const pageData = filteredData.slice(startIndex, endIndex);

  // Compute a strict table content signature to prevent unnecessary DOM mutations and blinking
  const tableSignature = pageData.map(r => `${r.id || r.timestamp}_${r.elephant_count}_${r.confidence}_${r.time}`).join('|');
  if (tbody.dataset.activeSignature === tableSignature && tbody.children.length === pageData.length) {
    updatePaginationUI();
    return; // Exact same content already in DOM; skip to prevent repaint flicker
  }

  const rowsHtml = pageData.map(row => {
    const isAlert = row.elephant_detected === 'YES' || row.detection === 'ELEPHANT_DETECTED' || row.elephant_count > 0;
    const rowClass = isAlert ? 'alert-row' : '';
    const badgeClass = isAlert ? 'badge-det yes' : 'badge-det no';
    const badgeText = isAlert ? '🐘 DETECTED' : 'SAFE';

    const confDisplay = typeof row.confidence === 'number' ? row.confidence.toFixed(1) : (row.confidence || 0);

    let displayDate = row.date || '—';
    let displayTime = row.time || '—';
    if (row.timestamp) {
      try {
        const cleanTs = String(row.timestamp).trim().replace('Z', '+00:00');
        const dtObj = new Date(cleanTs.includes('+') || cleanTs.includes('Z') ? cleanTs : cleanTs + 'Z');
        if (!isNaN(dtObj.getTime())) {
          displayTime = dtObj.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
          displayDate = dtObj.toLocaleDateString('en-CA'); // YYYY-MM-DD in local time
        }
      } catch (err) {}
    }

    let imageCellHtml = '<span class="no-image-text">—</span>';
    if (isAlert && row.image_path && row.image_path.trim() !== '') {
      const imageUrl = `/api/supabase/storage/image?image_path=${encodeURIComponent(row.image_path)}`;
      if (brokenImageUrls.has(imageUrl)) {
        imageCellHtml = '<span class="no-image-text">—</span>';
      } else {
        imageCellHtml = `
          <button class="btn-thumbnail" onclick="openImageModal('${imageUrl}', 'Detection at ${displayTime}')" title="View Full Bounding Box Image">
            <img src="${imageUrl}" class="table-thumb" alt="Thumb" loading="lazy" onerror="window.handleThumbError && window.handleThumbError(this, '${imageUrl}')">
            <span class="no-image-text" style="display:none">—</span>
          </button>
        `;
      }
    }

    return `
      <tr class="${rowClass}">
        <td>${displayDate}</td>
        <td>${displayTime}</td>
        <td>
          <span class="${badgeClass}">
            ${isAlert ? `<i class="fa-solid fa-warning"></i>` : `<i class="fa-solid fa-check"></i>`}
            ${badgeText}
          </span>
        </td>
        <td><strong>${row.elephant_count || 0}</strong></td>
        <td>${confDisplay}%</td>
        <td>${imageCellHtml}</td>
      </tr>
    `;
  }).join('');

  tbody.innerHTML = rowsHtml;
  tbody.dataset.activeSignature = tableSignature;

  updatePaginationUI();
}

function updatePaginationUI() {
  const totalPages = Math.ceil(filteredData.length / rowsPerPage) || 1;
  const prevBtn = document.getElementById('prev-page-btn');
  const nextBtn = document.getElementById('next-page-btn');
  const infoEl = document.getElementById('pagination-info');

  if (currentPage > totalPages) currentPage = totalPages;

  if (prevBtn) prevBtn.disabled = (currentPage === 1);
  if (nextBtn) nextBtn.disabled = (currentPage === totalPages);

  if (infoEl) {
    const start = filteredData.length === 0 ? 0 : (currentPage - 1) * rowsPerPage + 1;
    const end = Math.min(currentPage * rowsPerPage, filteredData.length);
    infoEl.textContent = `Showing ${start} to ${end} of ${filteredData.length} records (Page ${currentPage} of ${totalPages})`;
  }
}

function prevPage() {
  if (currentPage > 1) {
    currentPage--;
    renderHistoryTable();
  }
}

function nextPage() {
  const totalPages = Math.ceil(filteredData.length / rowsPerPage);
  if (currentPage < totalPages) {
    currentPage++;
    renderHistoryTable();
  }
}

function sortTable(column) {
  if (sortColumn === column) {
    sortAscending = !sortAscending;
  } else {
    sortColumn = column;
    sortAscending = true; // default asc
  }

  // Update sorting indicators in UI
  const headers = document.querySelectorAll('.history-table th');
  headers.forEach(header => {
    const colAttr = header.getAttribute('onclick');
    if (colAttr && colAttr.includes(column)) {
      const icon = header.querySelector('i');
      if (icon) {
        icon.className = sortAscending ? 'fa-solid fa-chevron-up' : 'fa-solid fa-chevron-down';
        icon.style.color = 'var(--accent-emerald)';
      }
    } else {
      const icon = header.querySelector('i');
      if (icon) {
        icon.className = 'fa-solid fa-sort';
        icon.style.color = 'var(--text-dim)';
      }
    }
  });

  currentPage = 1;
  renderHistoryTable();
}

function handleSearchAndFilter() {
  const searchVal = (document.getElementById('camera-search')?.value || '').toLowerCase().trim();
  const filterVal = document.getElementById('camera-filter')?.value || 'all';

  filteredData = historyData.filter(row => {
    // 1. Filter Check
    const isAlert = row.elephant_detected === 'YES' || row.elephant_count > 0;
    if (filterVal === 'alert' && !isAlert) return false;
    if (filterVal === 'safe' && isAlert) return false;

    // 2. Search Check
    if (searchVal) {
      const dateMatch = row.date.toLowerCase().includes(searchVal);
      const timeMatch = row.time.toLowerCase().includes(searchVal);
      const confidenceMatch = (row.confidence.toFixed(1) + '%').includes(searchVal);
      const countMatch = String(row.elephant_count).includes(searchVal);
      const statusText = isAlert ? 'detected elephant alert' : 'safe clear';
      const statusMatch = statusText.includes(searchVal);

      return dateMatch || timeMatch || confidenceMatch || countMatch || statusMatch;
    }

    return true;
  });

  currentPage = 1;
  renderHistoryTable();
}

// ==========================================
// 3. DETECTED ELEPHANT IMAGES GALLERY
// ==========================================
function loadGalleryImages() {
  if (!document.getElementById('camera-tab')?.classList.contains('active')) return;
  console.log("[GALLERY] Loading elephant images from Supabase...");
  
  // Query for elephant detections with images
  const params = new URLSearchParams({
    detection_type: 'ELEPHANT_DETECTED',
    limit: 20
  });
  
  fetch(`/api/supabase/detections?${params}`)
    .then(res => {
      if (!res.ok) throw new Error('Supabase gallery API unavailable');
      return res.json();
    })
    .then(detections => {
      if (detections.error) {
        console.error("[GALLERY] Error loading gallery:", detections.error);
        const container = document.getElementById('gallery-grid-container');
        if (container) {
          container.innerHTML = `
            <div class="gallery-placeholder">
              <i class="fa-solid fa-triangle-exclamation" style="font-size: 2rem; color: var(--status-danger);"></i>
              <p style="font-weight: 600;">Unable to load elephant images</p>
              <p style="font-size: 0.75rem;">${detections.error}</p>
            </div>
          `;
        }
        return;
      }
      
      // Filter for detections with genuine image paths and extensions
      const seenImages = new Set();
      const detectionsWithImages = detections.filter(d => {
        if (!d.image_path || typeof d.image_path !== 'string') return false;
        const trimmed = d.image_path.trim();
        if (!trimmed || trimmed === '0' || trimmed === 'N/A' || /^\d+$/.test(trimmed)) return false;
        if (!/\.(jpg|jpeg|png|webp)$/i.test(trimmed)) return false;
        const norm = trimmed.toLowerCase().split('/').pop().split('\\').pop();
        if (seenImages.has(norm)) return false;
        seenImages.add(norm);
        return true;
      });
      
      console.log(`[GALLERY] Found ${detectionsWithImages.length} elephant detections with valid images`);
      
      // Convert to gallery format with signed URLs
      galleryImages = detectionsWithImages.map(detection => ({
        filename: detection.image_path.split('/').pop().split('\\').pop() || 'unknown.jpg',
        timestamp: detection.timestamp,
        elephant_count: detection.elephant_count,
        confidence: detection.confidence,
        image_path: detection.image_path,
        detection_id: detection.id
      }));
      
      const currentGalleryJson = JSON.stringify(galleryImages);
      if (currentGalleryJson === lastGalleryDataJson && galleryImages.length > 0) {
        return; // Gallery unchanged - avoid re-renders
      }
      lastGalleryDataJson = currentGalleryJson;
      renderImageGallery();
    })
    .catch(err => {
      console.error("Error loading image gallery:", err);
      const container = document.getElementById('gallery-grid-container');
      if (container) {
        container.innerHTML = `
          <div class="gallery-placeholder">
            <i class="fa-solid fa-triangle-exclamation" style="font-size: 2rem; color: var(--status-danger);"></i>
            <p style="font-weight: 600;">Elephant Image Gallery Unavailable</p>
            <p style="font-size: 0.75rem;">${err.message}</p>
          </div>
        `;
      }
    });
}

async function renderImageGallery() {
  const container = document.getElementById('gallery-grid-container');
  if (!container) return;

  if (galleryImages.length === 0) {
    container.innerHTML = `
      <div class="gallery-placeholder">
        <i class="fa-solid fa-image" style="font-size: 3rem; color: var(--text-dim);"></i>
        <p style="font-weight: 600; margin-top: 0.5rem;">No Captured Bounding Box Images Found</p>
        <p style="font-size: 0.75rem;">When the detector triggers an elephant event, saved images will appear here automatically.</p>
      </div>
    `;
    container.dataset.activeSignature = 'empty';
    return;
  }

  const gallerySig = galleryImages.map(g => `${g.detection_id || g.filename}_${g.timestamp}`).join('|');
  if (container.dataset.activeSignature === gallerySig && container.children.length > 0) {
    return; // Gallery items unchanged; keep existing DOM to prevent blinking
  }

  // Fetch signed URLs and build cards in memory
  try {
    const cardPromises = galleryImages.map(async (imageData) => {
      try {
        const signedUrlResponse = await fetch(`/api/supabase/storage/signed-url?image_path=${encodeURIComponent(imageData.image_path)}`);
        if (!signedUrlResponse.ok) return null;
        const signedUrlData = await signedUrlResponse.json();
        if (signedUrlData.error || !signedUrlData.signed_url) return null;

        const imageUrl = signedUrlData.signed_url;
        let timestampStr = "Unknown Date/Time";
        if (imageData.timestamp) {
          try {
            const dt = new Date(imageData.timestamp);
            timestampStr = dt.toLocaleString();
          } catch {
            timestampStr = imageData.timestamp;
          }
        }
        const confFormatted = typeof imageData.confidence === 'number' ? imageData.confidence.toFixed(1) : imageData.confidence;

        return `
          <div class="gallery-card">
            <div class="gallery-image-wrapper">
              <img src="${imageUrl}" alt="Elephant Detection" class="gallery-image"
                   onerror="this.onerror=null; const c=this.closest('.gallery-card'); if(c) c.remove();"
                   onclick="openImageModal('${imageUrl}', '${imageData.filename}')">
              <div class="gallery-overlay">
                <span><i class="fa-solid fa-camera"></i> 🐘 Detected</span>
                <span><i class="fa-solid fa-clock"></i> ${timestampStr}</span>
              </div>
            </div>
            <div class="gallery-card-content">
              <div class="gallery-filename" title="${imageData.filename}">${imageData.filename}</div>
              <div class="gallery-meta">
                <span><i class="fa-solid fa-users"></i> ${imageData.elephant_count} Elephant${imageData.elephant_count > 1 ? 's' : ''}</span>
                <span><i class="fa-solid fa-bullseye"></i> ${confFormatted}%</span>
              </div>
            </div>
          </div>
        `;
      } catch {
        return null;
      }
    });

    const cards = (await Promise.all(cardPromises)).filter(Boolean);
    if (cards.length > 0) {
      container.innerHTML = cards.join('');
      container.dataset.activeSignature = gallerySig;
    }
  } catch (error) {
    console.error("[GALLERY] Error rendering gallery:", error);
  }
}

// ==========================================
// 4. IMAGE DETAIL MODAL OVERLAY
// ==========================================
function openImageModal(imgSrc, captionText) {
  const modal = document.getElementById('image-modal');
  const modalImg = document.getElementById('modal-image-view');
  const modalCaption = document.getElementById('modal-caption-text');

  if (modal && modalImg) {
    modal.classList.add('show');
    modalImg.src = imgSrc;
    if (modalCaption) {
      modalCaption.textContent = captionText;
    }
  }
}

function closeModal() {
  const modal = document.getElementById('image-modal');
  if (modal) {
    modal.classList.remove('show');
  }
}

// Global Refresh Action helper
function refreshCameraTab() {
  console.log("Refreshing camera tab dataset manually...");
  pollCameraStatus();
  loadHistoryData();
  loadGalleryImages();
}

// ==========================================
// REAL ELEPHANT DETECTION MONITORING
// ==========================================

// ==========================================
// ALERT SOUND (Web Audio API — no file needed)
// ==========================================

let alertAudioContext = null;
let alertSoundInterval = null;

function playAlertSound() {
  // Stop any previous sound loop first
  stopAlertSound();

  try {
    // Lazily create AudioContext on first user-interaction-unlocked call
    if (!alertAudioContext || alertAudioContext.state === 'closed') {
      alertAudioContext = new (window.AudioContext || window.webkitAudioContext)();
    }

    // Resume if suspended (autoplay policy)
    if (alertAudioContext.state === 'suspended') {
      alertAudioContext.resume();
    }

    // Play a 3-beep urgent pattern, then repeat every 4 seconds
    function playOneCycle() {
      if (!alertAudioContext) return;

      // Three rising beeps: 880 Hz, 1100 Hz, 1400 Hz
      const beeps = [
        { freq: 880,  startAt: 0.00, duration: 0.18 },
        { freq: 1100, startAt: 0.25, duration: 0.18 },
        { freq: 1400, startAt: 0.50, duration: 0.22 }
      ];

      const now = alertAudioContext.currentTime;

      beeps.forEach(({ freq, startAt, duration }) => {
        const osc     = alertAudioContext.createOscillator();
        const gainNode = alertAudioContext.createGain();

        osc.type      = 'square';
        osc.frequency.setValueAtTime(freq, now + startAt);

        // Sharp attack, quick decay — punchy beep
        gainNode.gain.setValueAtTime(0, now + startAt);
        gainNode.gain.linearRampToValueAtTime(0.55, now + startAt + 0.01);
        gainNode.gain.exponentialRampToValueAtTime(0.001, now + startAt + duration);

        osc.connect(gainNode);
        gainNode.connect(alertAudioContext.destination);

        osc.start(now + startAt);
        osc.stop(now + startAt + duration + 0.05);
      });
    }

    // Fire immediately then repeat
    playOneCycle();
    alertSoundInterval = setInterval(playOneCycle, 4000);

  } catch (e) {
    console.warn('Alert sound error:', e);
  }
}

function stopAlertSound() {
  if (alertSoundInterval) {
    clearInterval(alertSoundInterval);
    alertSoundInterval = null;
  }
}

// ==========================================
// REAL ELEPHANT DETECTION MONITORING
// ==========================================

// Poll for real elephant detections every 2 seconds
function startRealDetectionMonitoring() {
  console.log("Starting real elephant detection monitoring...");
  // Run immediately, then every 2 seconds
  checkForRealDetection();
  setInterval(checkForRealDetection, 2000);
}

// Check for real elephant detection from backend
async function checkForRealDetection() {
  try {
    const response = await fetch('/api/elephant-detection/confirmed');
    const data = await response.json();
    
    if (data.confirmed && data.detection) {
      const detection = data.detection;
      const detectionId = detection.id || `${detection.timestamp}_${detection.count}`;
      
      // Only trigger popup if this is a new detection (not already shown)
      if (detectionId !== lastRealDetectionId) {
        console.log("Real elephant detection confirmed:", detection);
        showRealElephantPopup(detection);
        lastRealDetectionId = detectionId;
      }
    }
  } catch (error) {
    // Silent fail - API might not be available yet
  }
}

// Show popup with real detection data from backend
function showRealElephantPopup(detection) {
  // Update popup content with REAL data
  const countElement = document.getElementById('popup-count');
  const confidenceElement = document.getElementById('popup-confidence');
  const timeElement = document.getElementById('popup-time');
  const pirElement = document.getElementById('popup-pir');
  const soundElement = document.getElementById('popup-sound');
  
  if (countElement) {
    countElement.textContent = detection.count || 0;
  }
  
  if (confidenceElement) {
    confidenceElement.textContent = `${(detection.confidence || 0).toFixed(1)}%`;
  }
  
  // Update PIR and Sound values
  if (pirElement) {
    if (detection.pir !== null && detection.pir !== undefined) {
      pirElement.textContent = detection.pir.toFixed(2);
    } else {
      pirElement.textContent = 'N/A';
    }
  }
  
  if (soundElement) {
    if (detection.sound !== null && detection.sound !== undefined) {
      soundElement.textContent = detection.sound.toFixed(2);
    } else {
      soundElement.textContent = 'N/A';
    }
  }
  
  if (timeElement) {
    // Parse timestamp and format
    let displayTime = detection.time || "N/A";
    if (detection.date && detection.time) {
      displayTime = `${detection.date} ${detection.time}`;
    }
    timeElement.textContent = displayTime;
  }
  
  // Show popup
  const overlay = document.getElementById('elephant-popup-overlay');
  const popup = document.getElementById('elephant-popup');
  
  if (overlay) overlay.classList.add('active');
  if (popup) popup.classList.add('active');

  // Play urgent alert sound
  playAlertSound();

  // Clear any existing timeout (from elephant_popup.js)
  if (window.elephantPopupTimeout) {
    clearTimeout(window.elephantPopupTimeout);
  }
  
  // Auto-dismiss after 30 seconds
  window.elephantPopupTimeout = setTimeout(() => {
    dismissElephantPopup();
  }, 30000);
  
  // Trigger browser notification
  triggerBrowserNotification(detection);
}

// Dismiss popup
window.dismissElephantPopup = function() {
  const overlay = document.getElementById('elephant-popup-overlay');
  const popup = document.getElementById('elephant-popup');
  
  if (overlay) overlay.classList.remove('active');
  if (popup) popup.classList.remove('active');

  // Stop the alert sound
  stopAlertSound();
};

// View detection - navigate to camera tab
window.viewDetection = function() {
  if (typeof dismissElephantPopup === 'function') {
    dismissElephantPopup();
  } else {
    const overlay = document.getElementById('elephant-popup-overlay');
    const popup = document.getElementById('elephant-popup');
    if (overlay) overlay.classList.remove('active');
    if (popup) popup.classList.remove('active');
  }
  
  // Switch to camera tab
  if (typeof switchTab === 'function') {
    switchTab('camera-tab');
  } else {
    const cameraTab = document.getElementById('nav-tab-camera') ||
                      document.querySelector('[data-tab="camera-tab"]') ||
                      document.querySelector('button[onclick*="camera-tab"]');
    if (cameraTab) cameraTab.click();
  }

  // Force active state
  const cameraPane = document.getElementById('camera-tab');
  if (cameraPane) {
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    cameraPane.classList.add('active');
  }
  document.querySelectorAll('.nav-tab').forEach(t => {
    t.classList.remove('active');
    const onclickAttr = t.getAttribute('onclick') || '';
    if (onclickAttr.includes('camera-tab') || t.getAttribute('data-tab') === 'camera-tab' || t.id === 'nav-tab-camera') {
      t.classList.add('active');
    }
  });

  if (typeof pollCameraStatus === 'function') pollCameraStatus();
  if (typeof loadHistoryData === 'function') loadHistoryData();
  if (typeof loadGalleryImages === 'function') loadGalleryImages();

  window.scrollTo({ top: 0, behavior: 'smooth' });
};

// Trigger browser notification
function triggerBrowserNotification(detection) {
  if (!('Notification' in window)) {
    return;
  }
  
  if (Notification.permission === 'granted') {
    // Build notification body with PIR and Sound
    let body = `Count: ${detection.count} | Confidence: ${(detection.confidence || 0).toFixed(1)}%`;
    
    // Add PIR and Sound if available
    const pirValue = (detection.pir !== null && detection.pir !== undefined) ? detection.pir.toFixed(2) : 'N/A';
    const soundValue = (detection.sound !== null && detection.sound !== undefined) ? detection.sound.toFixed(2) : 'N/A';
    body += `\nPIR: ${pirValue} | Sound: ${soundValue}`;
    
    const notification = new Notification('🐘 ELEPHANT DETECTED', {
      body: body,
      icon: '/static/icons/elephant-icon.png',
      badge: '/static/icons/elephant-badge.png',
      tag: 'elephant-detection-' + (detection.id || Date.now()),
      requireInteraction: true
    });
    
    notification.onclick = function() {
      window.focus();
      viewDetection();
      notification.close();
    };
  } else if (Notification.permission !== 'denied') {
    // Request permission if not granted
    Notification.requestPermission().then(function(permission) {
      if (permission === 'granted') {
        triggerBrowserNotification(detection);
      }
    });
  }
}
