/**
 * Elephant Detection Popup Module
 * Department of AI & ML, Sri Sairam College of Engineering
 * 
 * Handles automatic popup display for confirmed elephant detections
 * Note: Real-time monitoring is now in camera_detection.js
 */

// Global state for test functionality
let currentDetectionData = null;
let popupTimeout = null;
const POPUP_AUTO_DISMISS = 30000; // Auto-dismiss after 30 seconds

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  console.log("Elephant Popup Module Initialized (Legacy/Test Mode)");
  // Note: Real-time monitoring is handled in camera_detection.js
});

// Test function to manually trigger popup (for testing)
window.testElephantPopup = async function() {
  try {
    const response = await fetch('/api/elephant-detection/test-popup', {
      method: 'POST'
    });
    const data = await response.json();
    
    if (data.confirmed && data.detection) {
      const detection = data.detection;
      const detectionId = detection.id || `${detection.timestamp}_${detection.count}`;
      
      // Force show popup even if same ID
      showElephantPopup(detection);
      currentDetectionData = detection;
    }
  } catch (error) {
    console.error('Error testing elephant popup:', error);
  }
};

// Show elephant detection popup (for test/manual use)
function showElephantPopup(detection) {
  console.log('Showing elephant popup for detection:', detection);
  
  // Update popup content with real detection data
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
  
  if (timeElement) {
    const time = new Date(detection.timestamp);
    timeElement.textContent = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
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
  
  // Show popup overlay and popup
  const overlay = document.getElementById('elephant-popup-overlay');
  const popup = document.getElementById('elephant-popup');
  
  if (overlay) overlay.classList.add('active');
  if (popup) popup.classList.add('active');
  
  // Clear any existing timeout
  if (popupTimeout) {
    clearTimeout(popupTimeout);
  }
  
  // Set auto-dismiss timeout
  popupTimeout = setTimeout(() => {
    dismissElephantPopup();
  }, POPUP_AUTO_DISMISS);
  
  // Trigger browser notification if enabled
  triggerBrowserNotification(detection);
}

// Dismiss elephant popup
window.dismissElephantPopup = function() {
  console.log('Dismissing elephant popup');
  
  const overlay = document.getElementById('elephant-popup-overlay');
  const popup = document.getElementById('elephant-popup');
  
  if (overlay) overlay.classList.remove('active');
  if (popup) popup.classList.remove('active');
  
  // Clear timeout
  if (popupTimeout) {
    clearTimeout(popupTimeout);
    popupTimeout = null;
  }
}

// View detection - navigate to camera tab and show detection
window.viewDetection = function() {
  console.log('Viewing detection:', currentDetectionData);
  
  // Dismiss popup
  dismissElephantPopup();
  
  // Switch to camera tab
  const cameraTab = document.querySelector('[data-tab="camera-tab"]');
  if (cameraTab) {
    cameraTab.click();
  }
  
  // If we have detection data, we could highlight it or scroll to it
  // For now, just navigate to the camera tab
  if (currentDetectionData && currentDetectionData.image) {
    console.log('Detection image:', currentDetectionData.image);
    // Could add logic to highlight specific detection in the camera tab
  }
}

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
    
    const notification = new Notification('🐘 Elephant Detected', {
      body: body,
      icon: '/static/icons/elephant-icon.png', // Optional: add elephant icon
      badge: '/static/icons/elephant-badge.png', // Optional: add badge
      tag: 'elephant-detection', // Prevents duplicate notifications
      requireInteraction: true
    });
    
    notification.onclick = () => {
      window.focus();
      viewDetection();
      notification.close();
    };
  }
}

// Make functions globally available
window.testElephantPopup = testElephantPopup;

console.log('Elephant Popup Module Loaded');