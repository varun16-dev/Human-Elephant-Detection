/**
 * Service Worker for Elephant Alert System
 * Department of AI & ML, Sri Sairam College of Engineering
 * 
 * Handles push notifications and offline functionality
 */

console.log('=== service-worker.js START ===');

const CACHE_NAME = 'elephant-alert-v1';
const urlsToCache = [
  '/',
  '/static/css/main.css',
  '/static/css/camera_detection.css',
  '/static/js/app.js',
  '/static/js/camera_detection.js',
  '/static/js/sensor_nodes.js',
  '/static/js/map.js',
  '/static/js/edge_ai.js',
  '/static/js/dss.js'
];

// Install event - cache resources
self.addEventListener('install', (event) => {
  console.log('Service Worker installing...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('Service Worker caching files...');
        return cache.addAll(urlsToCache);
      })
      .catch((error) => {
        console.error('Service Worker cache error:', error);
        // Don't fail installation if caching fails
      })
  );
  self.skipWaiting();
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request)
      .then((response) => {
        if (response) {
          return response;
        }
        return fetch(event.request);
      })
  );
});

// Push notification event
self.addEventListener('push', (event) => {
  console.log('Push notification received');
  let data = {};
  try {
    data = event.data.json();
  } catch (e) {
    console.error('Error parsing push data:', e);
    data = {
      title: '🐘 Elephant Alert',
      body: 'Elephant detected in monitored area'
    };
  }
  
  const options = {
    body: data.body || 'Elephant detected in monitored area',
    vibrate: [200, 100, 200],
    data: data.data || {},
    requireInteraction: true
  };
  
  event.waitUntil(
    self.registration.showNotification(data.title || '🐘 Elephant Alert', options)
  );
});

// Notification click event
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow('/')
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  console.log('Service Worker activating...');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            console.log('Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  return self.clients.claim();
});

console.log('=== service-worker.js END ===');
