/**
 * Camera Elephant Detection Integration Module
 * Department of AI & ML, Sri Sairam College of Engineering
 */

// Global State for Camera Detection and History Table
let historyData = [];
let filteredData = [];
let galleryImages = [];
let lastRealDetectionId = null; // Track last real detection to avoid duplicate popups

// Pagination state
let currentPage = 1;
const rowsPerPage = 10;

// Sorting state
let sortColumn = 'timestamp';
let sortAscending = false; // default latest first

document.addEventListener('DOMContentLoaded', () => {
  console.log("Camera Detection Integration Initializing...");

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

function updateLiveStatusUI(data) {
  const statusEl = document.getElementById('cam-status-val');
  const detectionEl = document.getElementById('cam-detection-val');
  const countEl = document.getElementById('cam-count-val');
  const confidenceEl = document.getElementById('cam-confidence-val');
  const lastTimeEl = document.getElementById('cam-time-val');
  const liveViewContainer = document.getElementById('live-feed-view');

  if (statusEl) {
    statusEl.textContent = data.camera_status;
    statusEl.className = 'status-value ' + (data.camera_status === 'CONNECTED' ? 'connected' : 'disconnected');
  }

  if (detectionEl) {
    detectionEl.textContent = data.detection_status;
    if (data.detection_status.includes('ELEPHANT')) {
      detectionEl.className = 'status-value alert';
    } else if (data.detection_status === 'OFFLINE' || data.detection_status.includes('offline')) {
      detectionEl.className = 'status-value disconnected';
    } else {
      detectionEl.className = 'status-value safe';
    }
  }

  if (countEl) countEl.textContent = data.elephant_count;
  if (confidenceEl) confidenceEl.textContent = data.confidence;
  if (lastTimeEl) lastTimeEl.textContent = data.last_detection_time;

  // Render the latest detection image if available
  if (liveViewContainer) {
    if (data.latest_detection_image && data.latest_detection_image !== 'N/A') {
      const imageUrl = `/api/detection-images/${data.latest_detection_image}`;
      liveViewContainer.innerHTML = `
        <img src="${imageUrl}" class="live-image-feed" id="live-feed-img" alt="Latest Detection Image" style="cursor: pointer;" onclick="openImageModal('${imageUrl}', 'Latest Detection: ${data.latest_detection_image}')">
        <div class="live-image-overlay">
          <span><i class="fa-solid fa-camera"></i> LIVE WEB-CAMERA DETECTION</span>
          <span><i class="fa-solid fa-clock"></i> ${data.last_detection_time}</span>
        </div>
      `;
    } else {
      liveViewContainer.innerHTML = `
        <div class="live-image-placeholder">
          <i class="fa-solid fa-video-slash"></i>
          <p style="font-weight: 600;">No Recent Bounding Box Image Available</p>
          <p style="font-size: 0.75rem; color: var(--text-dim);">When elephants are detected by the webcam, bounding-box images will be rendered here.</p>
        </div>
      `;
    }
  }
}

// ==========================================
// 2. DETECTION HISTORY DATASET LOG
// ==========================================
function loadHistoryData() {
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
      
      historyData = data;
      filteredData = [...historyData];
      console.log(`[DETECTION] Loaded ${historyData.length} detection records from Supabase`);
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

  tbody.innerHTML = '';
  pageData.forEach(row => {
    const isAlert = row.elephant_detected === 'YES' || row.elephant_count > 0;
    const rowClass = isAlert ? 'alert-row' : '';
    const badgeClass = isAlert ? 'badge-det yes' : 'badge-det no';
    const badgeText = isAlert ? '🐘 DETECTED' : 'SAFE';
    
    let imageCellHtml = '<span class="no-image-text">—</span>';
    if (isAlert && row.image_path && row.image_path.trim() !== '') {
      const imageUrl = `/api/supabase/storage/image?image_path=${encodeURIComponent(row.image_path)}`;
      imageCellHtml = `
        <button class="btn-thumbnail" onclick="openImageModal('${imageUrl}', 'Detection at ${row.time}')" title="View Full Bounding Box Image">
          <img src="${imageUrl}" class="table-thumb" alt="Thumb" onerror="this.outerHTML='<span class=\'no-image-text\'>Missing</span>'">
        </button>
      `;
    }

    tbody.innerHTML += `
      <tr class="${rowClass}">
        <td>${row.date}</td>
        <td>${row.time}</td>
        <td>
          <span class="${badgeClass}">
            ${isAlert ? `<i class="fa-solid fa-warning"></i>` : `<i class="fa-solid fa-check"></i>`}
            ${badgeText}
          </span>
        </td>
        <td><strong>${row.elephant_count}</strong></td>
        <td>${row.confidence.toFixed(1)}%</td>
        <td>${imageCellHtml}</td>
      </tr>
    `;
  });

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
      
      // Filter for detections with image paths
      const detectionsWithImages = detections.filter(d => d.image_path && d.image_path.trim() !== '');
      
      console.log(`[GALLERY] Found ${detectionsWithImages.length} elephant detections with images`);
      
      // Convert to gallery format with signed URLs
      galleryImages = detectionsWithImages.map(detection => ({
        filename: detection.image_path.split('/').pop() || 'unknown.jpg',
        timestamp: detection.timestamp,
        elephant_count: detection.elephant_count,
        confidence: detection.confidence,
        image_path: detection.image_path,
        detection_id: detection.id
      }));
      
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

function renderImageGallery() {
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
    return;
  }

  container.innerHTML = '';
  
  // Process each image
  galleryImages.forEach(async (imageData) => {
    try {
      // Get signed URL for this image
      const signedUrlResponse = await fetch(`/api/supabase/storage/signed-url?image_path=${encodeURIComponent(imageData.image_path)}`);
      const signedUrlData = await signedUrlResponse.json();
      
      if (signedUrlData.error) {
        console.error("[GALLERY] Error getting signed URL:", signedUrlData.error);
        return;
      }
      
      const imageUrl = signedUrlData.signed_url;
      
      // Format timestamp
      let timestampStr = "Unknown Date/Time";
      if (imageData.timestamp) {
        try {
          const dt = new Date(imageData.timestamp);
          timestampStr = dt.toLocaleString();
        } catch {
          timestampStr = imageData.timestamp;
        }
      }
      
      // Create image card
      const card = document.createElement('div');
      card.className = 'gallery-card';
      card.innerHTML = `
        <div class="gallery-image-wrapper">
          <img src="${imageUrl}" alt="Elephant Detection" class="gallery-image" onclick="openImageModal('${imageUrl}', '${imageData.filename}')">
          <div class="gallery-overlay">
            <span><i class="fa-solid fa-camera"></i> 🐘 Elephant Detected</span>
            <span><i class="fa-solid fa-clock"></i> ${timestampStr}</span>
          </div>
        </div>
        <div class="gallery-card-content">
          <div class="gallery-filename">${imageData.filename}</div>
          <div class="gallery-meta">
            <span><i class="fa-solid fa-users"></i> ${imageData.elephant_count} Elephant${imageData.elephant_count > 1 ? 's' : ''}</span>
            <span><i class="fa-solid fa-bullseye"></i> ${imageData.confidence.toFixed(1)}%</span>
          </div>
        </div>
      `;
      
      container.appendChild(card);
      
    } catch (error) {
      console.error("[GALLERY] Error rendering image:", error);
    }
  });
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
  dismissElephantPopup();
  
  // Switch to camera tab
  const cameraTab = document.querySelector('[onclick="switchTab(\'camera-tab\')"]');
  if (cameraTab) {
    cameraTab.click();
  }
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
