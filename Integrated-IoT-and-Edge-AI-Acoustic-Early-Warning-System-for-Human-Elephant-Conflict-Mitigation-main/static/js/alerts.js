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
  
  // Load alert history
  loadAlertHistory();
  
  // Start polling alert status
  pollAlertStatus();
  setInterval(pollAlertStatus, 2000);
  
  // Load configuration
  loadAlertConfig();
});

// Load alert history from API
async function loadAlertHistory() {
  try {
    const response = await fetch('/api/alerts/history');
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
  
  if (alertHistory.length === 0) {
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
  
  // Show most recent 20 events
  const recentEvents = alertHistory.slice(-20).reverse();
  
  recentEvents.forEach(event => {
    const timestamp = event.timestamp || 'N/A';
    const time = timestamp.split('T')[1]?.split('.')[0] || timestamp;
    
    // Determine event type and styling
    const eventType = event.event_type || event.alert_type || 'UNKNOWN';
    const isActivity = eventType === 'ACTIVITY_DETECTED' || eventType === 'ACTIVITY_VERIFIED_NO_ELEPHANT';
    const isElephant = eventType === 'ELEPHANT_DETECTED' || eventType === 'ELEPHANT_CONFIRMED';
    
    let typeBadge = '';
    let rowClass = '';
    
    if (isActivity) {
      typeBadge = '<span class="badge-det warning">⚠️ Activity</span>';
      rowClass = 'activity-row';
    } else if (isElephant) {
      typeBadge = '<span class="badge-det critical">🐘 Elephant</span>';
      rowClass = 'elephant-row';
    } else {
      typeBadge = '<span class="badge-det no">Unknown</span>';
    }
    
    // Get trigger source for activity events
    const triggerSource = event.trigger_source || '-';
    const location = event.location || '-';
    const cameraStatus = event.camera_verification || '-';
    
    // Get notification status
    const webPushStatus = event.delivery_status?.web_push;
    const notificationBadge = getNotificationBadge(webPushStatus);
    
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
