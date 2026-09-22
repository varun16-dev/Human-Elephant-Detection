/**
 * Push Subscription Management for Elephant Alert System
 * Department of AI & ML, Sri Sairam College of Engineering
 * 
 * Manages web push subscription requests and UI
 */

console.log('=== push_subscription.js START ===');
console.log('push_subscription.js loaded successfully');

let pushSubscription = null;
let vapidPublicKey = null;

// Initialize push subscription
async function initPushSubscription() {
  // Check if push is supported
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    console.log('Push notifications not supported');
    updatePushUI('unsupported');
    return;
  }

  if (!('Notification' in window)) {
    updatePushUI('unsupported');
    return;
  }
  
  // Check notification permission
  if (Notification.permission === 'denied') {
    updatePushUI('denied');
    return;
  }

  // Register service worker
  try {
    console.log('Attempting to register service worker...');
    const registration = await navigator.serviceWorker.register('/service-worker.js', {
      scope: '/'
    });
    console.log('Service Worker registered successfully:', registration);

    // Get VAPID public key from server
    console.log('Fetching VAPID key from server...');
    const response = await fetch('/api/push/vapid-key');
    if (!response.ok) {
      console.error('Failed to fetch VAPID key, status:', response.status);
      throw new Error('Push backend is unavailable');
    }
    const data = await response.json();
    
    console.log('VAPID key response:', data);
    
    if (data.vapid_public_key) {
      vapidPublicKey = data.vapid_public_key;
      console.log('VAPID public key loaded, length:', vapidPublicKey.length);
      
      // Check existing subscription
      const existingSubscription = await registration.pushManager.getSubscription();
      if (existingSubscription) {
        pushSubscription = existingSubscription;
        console.log('Existing subscription found');
        try {
          await syncSubscription(existingSubscription);
          updatePushUI('subscribed');
        } catch (syncError) {
          console.error('Sync subscription failed:', syncError);
          // Continue anyway, show as ready state
          updatePushUI('ready');
        }
      } else {
        console.log('No existing subscription');
        updatePushUI('ready');
      }
    } else {
      console.log('No VAPID public key in response');
      updatePushUI('not_configured');
    }
  } catch (error) {
    console.error('Service Worker registration failed:', error);
    console.error('Error details:', error.message, error.stack);
    updatePushUI(error.message === 'Push backend is unavailable' ? 'backend_unavailable' : 'error');
  }
}

async function syncSubscription(subscription) {
  const response = await fetch('/api/push/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ subscription: subscription.toJSON(), user_role: 'VILLAGER', user_name: 'Dashboard User' })
  });
  if (!response.ok) throw new Error('Unable to sync the Push subscription');
}

// Subscribe to push notifications
async function subscribeToPush(role = 'VILLAGER', name = 'Unknown') {
  if (!vapidPublicKey) {
    alert('Push notifications not configured. Please contact administrator.');
    return false;
  }

  try {
    const registration = await navigator.serviceWorker.ready;
    
    // Convert VAPID key
    const convertedVapidKey = urlBase64ToUint8Array(vapidPublicKey);
    
    // Subscribe
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: convertedVapidKey
    });
    
    // Send subscription to server
    const response = await fetch('/api/push/subscribe', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        subscription: subscription.toJSON(),
        user_role: role,
        user_name: name
      })
    });
    
    const result = await response.json();
    
    if (result.success) {
      pushSubscription = subscription;
      updatePushUI('subscribed');
      alert('Successfully subscribed to elephant alerts!');
      return true;
    } else {
      alert('Failed to subscribe: ' + (result.error || 'Unknown error'));
      return false;
    }
  } catch (error) {
    console.error('Subscription failed:', error);
    alert('Failed to subscribe: ' + error.message);
    return false;
  }
}

// Unsubscribe from push notifications
async function unsubscribeFromPush() {
  if (!pushSubscription) {
    alert('No active subscription to remove.');
    return false;
  }

  try {
    await pushSubscription.unsubscribe();
    
    // Notify server
    const response = await fetch('/api/push/unsubscribe', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        subscription: pushSubscription.toJSON()
      })
    });
    
    pushSubscription = null;
    updatePushUI('ready');
    alert('Successfully unsubscribed from elephant alerts.');
    return true;
  } catch (error) {
    console.error('Unsubscribe failed:', error);
    alert('Failed to unsubscribe: ' + error.message);
    return false;
  }
}

// Update push UI based on state
function updatePushUI(state) {
  const statusElement = document.getElementById('push-status');
  const subscribeButton = document.getElementById('push-subscribe-btn');
  const unsubscribeButton = document.getElementById('push-unsubscribe-btn');
  
  if (!statusElement) return;
  
  switch (state) {
    case 'unsupported':
      statusElement.textContent = 'Not supported by this browser';
      statusElement.className = 'push-status error';
      if (subscribeButton) subscribeButton.disabled = true;
      if (unsubscribeButton) unsubscribeButton.disabled = true;
      break;
      
    case 'not_configured':
      statusElement.textContent = 'Not configured by administrator';
      statusElement.className = 'push-status error';
      if (subscribeButton) subscribeButton.disabled = true;
      if (unsubscribeButton) unsubscribeButton.disabled = true;
      break;
      
    case 'ready':
      statusElement.textContent = '🔕 Notifications disabled — permission not yet granted';
      statusElement.className = 'push-status ready';
      if (subscribeButton) subscribeButton.disabled = false;
      if (unsubscribeButton) unsubscribeButton.disabled = true;
      break;
      
    case 'subscribed':
      statusElement.textContent = '🔔 Notifications enabled';
      statusElement.className = 'push-status success';
      if (subscribeButton) subscribeButton.disabled = true;
      if (unsubscribeButton) unsubscribeButton.disabled = false;
      break;

    case 'denied':
      statusElement.textContent = '⚠️ Browser notification permission denied or blocked';
      statusElement.className = 'push-status error';
      if (subscribeButton) subscribeButton.disabled = true;
      if (unsubscribeButton) unsubscribeButton.disabled = true;
      break;
      
    case 'error':
      statusElement.textContent = 'Error initializing push notifications';
      statusElement.className = 'push-status error';
      if (subscribeButton) subscribeButton.disabled = true;
      if (unsubscribeButton) unsubscribeButton.disabled = true;
      break;

    case 'backend_unavailable':
      statusElement.textContent = '⚠️ Notification backend unavailable';
      statusElement.className = 'push-status error';
      if (subscribeButton) subscribeButton.disabled = true;
      if (unsubscribeButton) unsubscribeButton.disabled = true;
      break;
      
    default:
      statusElement.textContent = 'Unknown state';
      statusElement.className = 'push-status error';
  }
}

// Helper: Convert base64 to Uint8Array
function urlBase64ToUint8Array(base64String) {
  console.log('Converting VAPID key, input length:', base64String.length);
  console.log('VAPID key first 20 chars:', base64String.substring(0, 20));
  
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  
  console.log('Converted VAPID key to Uint8Array, length:', outputArray.length);
  console.log('Expected length: 65 (for P-256 curve)');
  
  // If the decoded key is 65 bytes and starts with 0x04, it's the full key
  // If it's 64 bytes, it's missing the 0x04 prefix, so add it
  if (outputArray.length === 64) {
    console.log('Adding 0x04 prefix to 64-byte key');
    const newArray = new Uint8Array(65);
    newArray[0] = 0x04;
    newArray.set(outputArray, 1);
    return newArray;
  }
  
  return outputArray;
}

// Request notification permission
async function requestNotificationPermission() {
  if (!('Notification' in window)) {
    alert('This browser does not support notifications');
    return false;
  }
  
  if (Notification.permission === 'granted') {
    return true;
  }
  
  if (Notification.permission !== 'denied') {
    const permission = await Notification.requestPermission();
    return permission === 'granted';
  }
  
  updatePushUI('denied');
  alert('Notification permission denied or blocked. Enable it in browser settings to continue.');
  return false;
}

// Initialize on page load
try {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      console.log('DOM loaded, initializing push subscription...');
      initPushSubscription();
    });
  } else {
    // DOM already loaded
    console.log('DOM already loaded, initializing push subscription immediately...');
    initPushSubscription();
  }
} catch (error) {
  console.error('Error during push subscription initialization:', error);
}

// Make functions globally available for HTML onclick handlers
window.handlePushSubscribe = handlePushSubscribe;
window.handlePushUnsubscribe = handlePushUnsubscribe;

console.log('=== push_subscription.js END ===');
console.log('Functions attached to window:', {
  handlePushSubscribe: typeof window.handlePushSubscribe,
  handlePushUnsubscribe: typeof window.handlePushUnsubscribe,
  sendTestPush: typeof window.sendTestPush
});
// Handle subscribe button click
async function handlePushSubscribe() {
  console.log('Subscribe button clicked');
  try {
    const permissionGranted = await requestNotificationPermission();
    if (permissionGranted) {
      // Use default role and name for simplicity
      await subscribeToPush('VILLAGER', 'Dashboard User');
    } else {
      console.log('Notification permission not granted');
    }
  } catch (error) {
    console.error('Subscribe error:', error);
    alert('Failed to subscribe: ' + error.message);
  }
}

// Handle unsubscribe button click
async function handlePushUnsubscribe() {
  console.log('Unsubscribe button clicked');
  try {
    await unsubscribeFromPush();
  } catch (error) {
    console.error('Unsubscribe error:', error);
    alert('Failed to unsubscribe: ' + error.message);
  }
}

// Make sendTestPush globally available
window.sendTestPush = async function(role) {
  console.log('Test notification button clicked for role:', role);
  try {
    const response = await fetch('/api/push/test', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ role: role })
    });
    
    const result = await response.json();
    
    if (result.success) {
      alert(`Test notification sent to ${role}s! Check your browser notifications.`);
    } else {
      alert(`Failed to send test notification: ${result.error || 'Unknown error'}`);
    }
  } catch (error) {
    console.error('Test notification failed:', error);
    alert('Failed to send test notification: ' + error.message);
  }
};

console.log('=== push_subscription.js END ===');
console.log('Functions attached to window:', {
  handlePushSubscribe: typeof window.handlePushSubscribe,
  handlePushUnsubscribe: typeof window.handlePushUnsubscribe,
  sendTestPush: typeof window.sendTestPush
});