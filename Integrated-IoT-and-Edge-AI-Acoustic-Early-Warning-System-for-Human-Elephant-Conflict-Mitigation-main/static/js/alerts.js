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
        <td colspan="5" style="text-align: center; padding: 2rem; color: var(--text-muted);">
          <i class="fa-solid fa-circle-info" style="font-size: 1.5rem; margin-bottom: 0.5rem; color: var(--text-dim);"></i>
          <p style="font-weight: 600;">No confirmed elephant alerts yet</p>
        </td>
      </tr>
    `;
    return;
  }
  
  tbody.innerHTML = '';
  
  // Show most recent 20 alerts
  const recentAlerts = alertHistory.slice(-20).reverse();
  
  recentAlerts.forEach(alert => {
    const timestamp = alert.timestamp || 'N/A';
    const time = timestamp.split('T')[1]?.split('.')[0] || timestamp;
    const count = alert.elephant_count || 0;
    const confidence = alert.confidence || 0;
    
    const webPushStatus = alert.delivery_status?.web_push;
    const webPushBadge = getStatusBadge(webPushStatus);
    
    tbody.innerHTML += `
      <tr>
        <td>${time}</td>
        <td><strong>${count}</strong></td>
        <td>${confidence}%</td>
        <td>${webPushBadge}</td>
      </tr>
    `;
  });
}

// Get status badge HTML
function getStatusBadge(status) {
  if (!status) return '<span class="badge-det no">N/A</span>';
  
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
  const consecutiveVal = document.getElementById('alert-consecutive-val');
  const confidenceVal = document.getElementById('alert-confidence-val');
  const timeVal = document.getElementById('alert-time-val');
  
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

// Reset alert cooldown
async function resetAlertCooldown() {
  if (!confirm('Reset alert cooldown? This is for testing only.')) return;
  
  try {
    const response = await fetch('/api/alerts/reset-cooldown', {
      method: 'POST'
    });
    
    const result = await response.json();
    
    if (result.success) {
      alert('Alert cooldown reset successfully');
      pollAlertStatus(); // Refresh status
    } else {
      alert('Failed to reset cooldown');
    }
  } catch (error) {
    alert(`Error: ${error.message}`);
  }
}

// Reset alert cooldown
async function resetAlertCooldown() {
  if (!confirm('Reset alert cooldown? This is for testing only.')) return;
  
  try {
    const response = await fetch('/api/alerts/reset-cooldown', {
      method: 'POST'
    });
    
    const result = await response.json();
    
    if (result.success) {
      alert('Alert cooldown reset successfully');
      pollAlertStatus(); // Refresh status
    } else {
      alert('Failed to reset cooldown');
    }
  } catch (error) {
    alert(`Error: ${error.message}`);
  }
}
