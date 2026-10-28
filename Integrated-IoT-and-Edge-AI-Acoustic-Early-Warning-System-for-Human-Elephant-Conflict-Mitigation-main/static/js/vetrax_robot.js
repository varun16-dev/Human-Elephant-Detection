/**
 * VETRAX Spider Robot Recon & Telemetry Controller
 * Integrates ESP32-CAM frame streaming with server-side AI elephant detection
 */

(function () {
  'use strict';

  let pollInterval = null;
  let isSimulating = false;

  async function fetchVetraxStatus() {
    try {
      const res = await fetch('/api/robot/vetrax/status', {
        headers: { 'Accept': 'application/json' }
      });
      if (!res.ok) throw new Error('Status HTTP ' + res.status);
      const data = await res.json();
      updateVetraxUI(data);
    } catch (err) {
      console.warn('[VETRAX] Status fetch failed:', err.message);
    }
  }

  let lastProcessedFrameCount = 0;

  function updateVetraxUI(data) {
    const statusVal = document.getElementById('vetrax-status-val');
    const deviceIdVal = document.getElementById('vetrax-device-id');
    const detectionVal = document.getElementById('vetrax-detection-val');
    const telemetryVal = document.getElementById('vetrax-telemetry-val');
    const timestampBadge = document.getElementById('vetrax-timestamp-badge');
    const imgEl = document.getElementById('vetrax-latest-img');
    const placeholderEl = document.getElementById('vetrax-placeholder');

    // Auto-refresh gallery and table if new frames arrived
    if (data.frames_received && data.frames_received !== lastProcessedFrameCount) {
      lastProcessedFrameCount = data.frames_received;
      if (typeof loadHistoryData === 'function') loadHistoryData();
      if (typeof loadGalleryImages === 'function') loadGalleryImages();
    }

    if (!statusVal) return;

    // Online calculation
    const now = Date.now() / 1000;
    const isRecentlyActive = data.last_frame_timestamp && (now - data.last_frame_timestamp < 45);

    if (isRecentlyActive) {
      statusVal.innerHTML = '<span class="dot-indicator" style="background: #10b981; display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; box-shadow: 0 0 8px #10b981;"></span><span style="color: #10b981; font-weight: 700;">STREAMING ACTIVE</span>';
    } else if (data.frames_received > 0) {
      statusVal.innerHTML = '<span class="dot-indicator" style="background: #f59e0b; display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px;"></span><span style="color: #f59e0b; font-weight: 700;">STANDBY</span>';
    } else {
      statusVal.innerHTML = '<span class="dot-indicator" style="background: #64748b; display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px;"></span><span style="color: #94a3b8;">OFFLINE / IDLE</span>';
    }

    if (deviceIdVal && data.device_id) {
      deviceIdVal.textContent = data.device_id + (data.active_source ? ' (' + data.active_source + ')' : '');
    }

    if (detectionVal) {
      if (data.latest_detection && data.latest_detection.elephant_detected) {
        const count = data.latest_detection.elephant_count || 1;
        const conf = Math.round((data.latest_detection.confidence || 0) * 100);
        detectionVal.innerHTML = `<span style="color: #ef4444; font-weight: 800;"><i class="fa-solid fa-triangle-exclamation"></i> 🐘 ${count} ELEPHANT(S) DETECTED (${conf}%)</span>`;
      } else if (data.frames_received > 0) {
        detectionVal.innerHTML = `<span style="color: #10b981;"><i class="fa-solid fa-check-circle"></i> SAFE - NO ELEPHANTS</span>`;
      } else {
        detectionVal.innerHTML = `<span style="color: #64748b;">STANDBY</span>`;
      }
    }

    if (telemetryVal) {
      const fps = data.fps ? data.fps.toFixed(1) : '0.0';
      const infTime = data.latest_detection && data.latest_detection.inference_time_ms ? `${Math.round(data.latest_detection.inference_time_ms)}ms` : '--';
      telemetryVal.textContent = `${data.frames_received || 0} frames • ${fps} FPS • AI: ${infTime}`;
    }

    if (timestampBadge) {
      if (data.last_frame_iso) {
        const d = new Date(data.last_frame_iso);
        timestampBadge.textContent = 'Last: ' + d.toLocaleTimeString();
      } else {
        timestampBadge.textContent = 'No frames received';
      }
    }

    // Display image if available
    if (data.has_latest_frame && imgEl && placeholderEl) {
      imgEl.src = '/api/robot/vetrax/latest-frame?t=' + Date.now();
      imgEl.style.display = 'block';
      placeholderEl.style.display = 'none';
    }
  }

  async function simulateVetraxFrame() {
    if (isSimulating) return;
    const btn = document.getElementById('btn-vetrax-simulate');
    const notice = document.getElementById('vetrax-sim-notice');

    try {
      isSimulating = true;
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing AI Frame...';
      }
      if (notice) {
        notice.style.display = 'block';
        notice.style.color = '#818cf8';
        notice.textContent = 'Simulating VETRAX ESP32-CAM frame transmission & server-side MobileNet inference...';
      }

      const res = await fetch('/api/robot/vetrax/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ simulate_elephant: true, count: 1 })
      });

      const result = await res.json();
      if (!res.ok) throw new Error(result.error || 'Simulation failed');

      if (notice) {
        const det = (result.intake_result && result.intake_result.elephant_detected) ? result.intake_result : (result.detection || {});
        if (det.elephant_detected) {
          const conf = ((det.highest_confidence || det.confidence || 0) * 100).toFixed(1);
          notice.style.color = '#ef4444';
          notice.innerHTML = `<strong>Result:</strong> 🐘 Elephant detected with ${conf}% confidence! Telegram alert queued.`;
        } else {
          notice.style.color = '#10b981';
          notice.innerHTML = `<strong>Result:</strong> Frame processed. No elephants detected.`;
        }
      }

      await fetchVetraxStatus();

      // Trigger refresh of general camera history and alerts table
      if (typeof loadHistoryData === 'function') loadHistoryData();
      if (typeof loadGalleryImages === 'function') loadGalleryImages();

    } catch (err) {
      if (notice) {
        notice.style.display = 'block';
        notice.style.color = '#ef4444';
        notice.textContent = 'Error: ' + err.message;
      }
    } finally {
      isSimulating = false;
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-flask"></i> Simulate Robot Recon Frame';
      }
    }
  }

  // Expose to window
  window.fetchVetraxStatus = fetchVetraxStatus;
  window.simulateVetraxFrame = simulateVetraxFrame;

  document.addEventListener('DOMContentLoaded', () => {
    fetchVetraxStatus();
    // Auto-poll: every 2.5s when camera tab active, every 5s in background
    pollInterval = setInterval(() => {
      const cameraTab = document.getElementById('camera-tab');
      if (cameraTab && cameraTab.classList.contains('active')) {
        fetchVetraxStatus();
      }
    }, 2500);
  });
})();
