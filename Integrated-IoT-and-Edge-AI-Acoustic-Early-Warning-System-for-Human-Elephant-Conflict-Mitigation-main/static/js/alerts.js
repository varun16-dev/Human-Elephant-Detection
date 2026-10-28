/**
 * Alert Management Module for Elephant Alert System
 * Department of AI & ML, Sri Sairam College of Engineering
 * 
 * Handles alert history, status display, and notification management
 */

// Global state
let alertHistory = [];
let alertStatusInterval = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  console.log("Alert Management Initializing...");
  
  // Load alert history immediately
  loadAlertHistory();
  
  // Poll alert history every 3 seconds to keep UI in sync
  setInterval(loadAlertHistory, 3000);
  
  // Start polling alert status
  pollAlertStatus();
  setInterval(pollAlertStatus, 2000);
  
  // Load configuration
  loadAlertConfig();

  // Also reload immediately whenever user clicks the Alerts & Notifications tab
  document.querySelectorAll('[data-tab="alerts-tab"], a[href="#alerts-tab"], .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      setTimeout(loadAlertHistory, 100);
    });
  });
});

// Load alert history from API
async function loadAlertHistory() {
  try {
    const response = await fetch('/api/alerts/history');
    if (!response.ok) return;
    const data = await response.json();
    
    if (Array.isArray(data)) {
      alertHistory = data;
      renderAlertHistory();
    }
  } catch (error) {
    console.error('Error loading alert history:', error);
  }
}

// Render alert history table
function renderAlertHistory() {
  const tbody = document.getElementById('alerts-table-body');
  if (!tbody) return;
  
  if (!alertHistory || alertHistory.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; padding: 2rem; color: var(--text-muted);">
          <i class="fa-solid fa-circle-info" style="font-size: 1.5rem; margin-bottom: 0.5rem; color: var(--text-dim);"></i>
          <p style="font-weight: 600;">No detection events yet</p>
        </td>
      </tr>
    `;
    return;
  }
  
  tbody.innerHTML = '';
  
  // Sort descending by timestamp (newest events first)
  const sortedEvents = [...alertHistory].sort((a, b) => {
    const tA = new Date(a.timestamp || a.created_at || 0).getTime();
    const tB = new Date(b.timestamp || b.created_at || 0).getTime();
    return tB - tA;
  });

  // Show most recent 25 events
  const recentEvents = sortedEvents.slice(0, 25);
  
  recentEvents.forEach(event => {
    const rawTs = event.timestamp || event.created_at || 'N/A';
    let time = 'N/A';
    if (rawTs && typeof rawTs === 'string') {
      if (rawTs.includes('T')) {
        time = rawTs.split('T')[1].split('.')[0];
      } else if (rawTs.includes(' ')) {
        time = rawTs.split(' ')[1];
      } else {
        time = rawTs;
      }
    }
    
    // Determine event type and styling
    const eventType = String(event.event_type || event.alert_type || event.detection || '').toUpperCase();
    const isElephant = eventType.includes('ELEPHANT') || event.elephant_detected === true || (event.elephant_count && event.elephant_count > 0);
    const isActivity = !isElephant && (eventType.includes('ACTIVITY') || event.pir_detected || event.sound_detected);
    
    let typeBadge = '';
    let rowClass = '';
    
    if (isElephant) {
      const cnt = event.elephant_count || 1;
      typeBadge = `<span class="badge-det critical">🐘 Elephant (${cnt})</span>`;
      rowClass = 'elephant-row';
    } else if (isActivity) {
      typeBadge = '<span class="badge-det warning">⚠️ Activity</span>';
      rowClass = 'activity-row';
    } else {
      typeBadge = '<span class="badge-det no">Notice</span>';
    }
    
    // Determine trigger source
    let triggerSource = event.trigger_source;
    if (!triggerSource || triggerSource === '-') {
      if (event.pir_detected && event.sound_detected) {
        triggerSource = 'PIR + Sound';
      } else if (event.pir_detected) {
        triggerSource = 'PIR Sensor';
      } else if (event.sound_detected) {
        triggerSource = 'Acoustic Sensor';
      } else {
        triggerSource = 'AI Camera Stream';
      }
    }
    
    const location = event.location || 'Anekal, Karnataka';
    
    // Determine camera status
    let cameraStatus = event.camera_verification;
    if (!cameraStatus || cameraStatus === '-') {
      if (isElephant) {
        cameraStatus = event.elephant_count ? `Verified (${event.elephant_count})` : 'Verified';
      } else {
        cameraStatus = 'Active';
      }
    }
    
    // Get notification status
    let webPushStatus = event.delivery_status?.web_push;
    if (!webPushStatus && event.alert_sent) {
      webPushStatus = 'sent';
    }
    const notificationBadge = getNotificationBadge(webPushStatus || event.delivery_status);
    
    tbody.innerHTML += `
      <tr class="${rowClass}">
        <td>${time}</td>
        <td>${typeBadge}</td>
        <td>${triggerSource}</td>
        <td>${location}</td>
        <td>${cameraStatus}</td>
        <td>${notificationBadge}</td>
      </tr>
    `;
  });
}

// Get notification badge HTML
function getNotificationBadge(status) {
  if (!status) return '<span class="badge-det no">N/A</span>';
  
  // Handle both old format (web_push object with roles) and new format (simple status)
  if (typeof status === 'string') {
    if (status === 'sent') {
      return '<span class="badge-det yes">✓ Sent</span>';
    } else if (status === 'failed') {
      return '<span class="badge-det no">✗ Failed</span>';
    } else {
      return '<span class="badge-det no">Pending</span>';
    }
  }
  
  // Old format with roles
  const webPushStatus = status.web_push;
  const forestStatus = webPushStatus?.forest_officers || 'pending';
  const villagerStatus = webPushStatus?.villagers || 'pending';
  
  if (forestStatus === 'sent' && villagerStatus === 'sent') {
    return '<span class="badge-det yes">✓ Sent</span>';
  } else if (forestStatus === 'failed' || villagerStatus === 'failed') {
    return '<span class="badge-det no">✗ Failed</span>';
  } else {
    return '<span class="badge-det no">Pending</span>';
  }
}

// Poll alert status
async function pollAlertStatus() {
  if (!document.getElementById('alerts-tab')?.classList.contains('active')) return;
  try {
    const response = await fetch('/api/alerts/status');
    const data = await response.json();
    
    if (data) {
      updateAlertStatusUI(data);
    }
  } catch (error) {
    console.error('Error polling alert status:', error);
  }
}

// Update alert status UI
function updateAlertStatusUI(status) {
  const stateVal = document.getElementById('alert-state-val');
  const activityStateVal = document.getElementById('activity-state-val');
  const consecutiveVal = document.getElementById('alert-consecutive-val');
  const confidenceVal = document.getElementById('alert-confidence-val');
  const timeVal = document.getElementById('alert-time-val');
  const activityTimeVal = document.getElementById('activity-time-val');
  
  // Elephant detection state
  if (stateVal) {
    stateVal.textContent = status.state || 'NO_DETECTION';
    stateVal.className = 'status-value';
    
    if (status.state === 'CONFIRMED' || status.state === 'ALERT_SENT') {
      stateVal.style.color = '#ef4444';
    } else if (status.state === 'POSSIBLE') {
      stateVal.style.color = '#f59e0b';
    } else {
      stateVal.style.color = '#10b981';
    }
  }
  
  // Activity detection state
  if (activityStateVal) {
    activityStateVal.textContent = status.activity_state || 'IDLE';
    activityStateVal.className = 'status-value';
    
    if (status.activity_state === 'ACTIVITY_DETECTED' || status.activity_state === 'CAMERA_PENDING') {
      activityStateVal.style.color = '#f59e0b';
    } else if (status.activity_state === 'CAMERA_VERIFIED_ELEPHANT') {
      activityStateVal.style.color = '#ef4444';
    } else if (status.activity_state === 'CAMERA_VERIFIED_NO_ELEPHANT') {
      activityStateVal.style.color = '#10b981';
    } else {
      activityStateVal.style.color = '#6b7280';
    }
  }
  
  if (consecutiveVal) {
    consecutiveVal.textContent = status.consecutive_detections || 0;
  }
  
  if (confidenceVal) {
    const avgConf = status.avg_confidence || 0;
    confidenceVal.textContent = `${(avgConf * 100).toFixed(1)}%`;
  }
  
  if (timeVal) {
    const timeSince = status.time_since_last_alert || 0;
    if (timeSince > 0) {
      timeVal.textContent = `${Math.floor(timeSince)}s ago`;
    } else {
      timeVal.textContent = 'N/A';
    }
  }
  
  if (activityTimeVal) {
    const timeSinceActivity = status.time_since_last_activity || 0;
    if (timeSinceActivity > 0) {
      activityTimeVal.textContent = `${Math.floor(timeSinceActivity)}s ago`;
    } else {
      activityTimeVal.textContent = 'N/A';
    }
  }
}

// Load alert configuration
function loadAlertConfig() {
  // Configuration is loaded from alert_config.json
  // For now, display default values
  const framesVal = document.getElementById('config-frames');
  const confidenceVal = document.getElementById('config-confidence');
  const cooldownVal = document.getElementById('config-cooldown');
  
  if (framesVal) framesVal.textContent = '3';
  if (confidenceVal) confidenceVal.textContent = '50%';
  if (cooldownVal) cooldownVal.textContent = '300 seconds';
}

// These functions are implemented in push_subscription.js
// handlePushSubscribe, handlePushUnsubscribe, sendTestPush
