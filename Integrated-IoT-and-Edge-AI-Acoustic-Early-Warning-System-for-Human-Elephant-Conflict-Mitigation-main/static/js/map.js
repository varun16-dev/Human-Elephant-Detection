/**
 * Module 4: Live GIS Elephant Trajectory Map
 * Bannerghatta National Park Fringe Area (Anekal / Jigani Range)
 * Integrated IoT and Edge-AI Acoustic Early Warning System
 */

let leafletMap = null;
let nodeMarkers = [];
let herdMarkers = [];
let pathPolyline = null;
let riskCircles = [];

function initGISMap(nodes, herdInfo) {
  const mapElement = document.getElementById('map-container');
  if (!mapElement) return;

  // Safely teardown existing map instance if re-initialized to prevent Leaflet container duplicate errors
  if (leafletMap !== null) {
    leafletMap.remove();
    leafletMap = null;
    nodeMarkers = [];
    herdMarkers = [];
    riskCircles = [];
    pathPolyline = null;
  }

  // Define single full world boundary (prevents infinite horizontal tile looping)
  const worldBounds = L.latLngBounds([[-85, -180], [85, 180]]);

  // Initialize Map centered across the Southern Elephant Corridor (Bannerghatta, Anekal, Thally, Jawalagiri, Ramanagara)
  leafletMap = L.map('map-container', {
    center: [12.6800, 77.6600],
    zoom: 11,
    minZoom: 2,
    maxZoom: 18,
    maxBounds: worldBounds,
    maxBoundsViscosity: 1.0,
    worldCopyJump: false
  });

  // Base Map Tile Layers with noWrap: true (100% Free - ZERO API Keys / NO Watermark!)
  const darkTiles = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ',
    maxZoom: 16,
    noWrap: true
  });

  const streetTiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
    noWrap: true
  });

  const satelliteTiles = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri',
    maxZoom: 18,
    noWrap: true
  });

  darkTiles.addTo(leafletMap);

  // Add Tile Layer Control (Zero API Keys Needed)
  const baseMaps = {
    "Dark Mode (Default)": darkTiles,
    "Street Map (OSM)": streetTiles,
    "Satellite Imagery": satelliteTiles
  };
  L.control.layers(baseMaps).addTo(leafletMap);

  // Custom Icon Definitions
  const elephantIcon = L.divIcon({
    className: 'custom-leaflet-icon',
    html: `<div style="background: rgba(239, 68, 68, 0.9); border: 2px solid #fff; width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 16px; box-shadow: 0 0 15px rgba(239, 68, 68, 0.8);"><i class="fa-solid fa-paw"></i></div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17]
  });

  const nodeAlertIcon = L.divIcon({
    className: 'custom-leaflet-icon',
    html: `<div style="background: rgba(245, 158, 11, 0.9); border: 2px solid #fff; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 13px; box-shadow: 0 0 10px rgba(245, 158, 11, 0.7);"><i class="fa-solid fa-tower-broadcast"></i></div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14]
  });

  const nodeSafeIcon = L.divIcon({
    className: 'custom-leaflet-icon',
    html: `<div style="background: rgba(16, 185, 129, 0.85); border: 2px solid #fff; width: 26px; height: 26px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 12px;"><i class="fa-solid fa-microchip"></i></div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13]
  });

  // 1. Render ESP32 Sensor Nodes
  nodes.forEach(node => {
    const isAlert = node.status === 'ALERT';
    const icon = isAlert ? nodeAlertIcon : nodeSafeIcon;
    const marker = L.marker([node.lat, node.lng], { icon: icon }).addTo(leafletMap);
    
    // Store node data in marker for dynamic updates
    marker.nodeData = node;
    
    // Use node's actual GPS coordinates as single source of truth
    const nodeCoords = {
      latitude: node.lat,
      longitude: node.lng
    };
    
    // Dynamic node name based on location for Node 1
    const dynamicNodeName = node.id === 'ESP32-NODE-01' 
      ? `Node 1 - ${node.location}` 
      : node.name;
    
    marker.bindPopup(`
      <div style="font-family: Inter, sans-serif; font-size: 12px; padding: 4px;">
        <strong style="color: ${isAlert ? '#ef4444' : '#10b981'}; font-size: 14px;">${dynamicNodeName}</strong><br/>
        <strong>Status:</strong> ${node.status}<br/>
        <strong>Location:</strong> ${node.location}<br/>
        <strong>Node 1 Position:</strong> ${nodeCoords.latitude.toFixed(4)}° N, ${nodeCoords.longitude.toFixed(4)}° E<br/>
        <strong>PIR:</strong> ${node.pir ? 'Detected' : 'Clear'}<br/>
        <strong>Sound:</strong> ${node.acoustic_db}<br/>
        <strong>Sound Class:</strong> ${node.sound_class} (${node.confidence}%)<br/>
        <strong>Battery/Solar:</strong> ${node.battery}% (${node.solar_v}V)
      </div>
    `);

    nodeMarkers.push(marker);
  });

  // 2. Render Elephant Herd Location & Trajectory Path
  if (herdInfo) {
    const herdMarker = L.marker([herdInfo.current_lat, herdInfo.current_lng], { icon: elephantIcon }).addTo(leafletMap);
    herdMarker.bindPopup(`
      <div style="font-family: Inter, sans-serif; font-size: 13px; padding: 4px;">
        <strong style="color: #ef4444; font-size: 15px;"><i class="fa-solid fa-triangle-exclamation"></i> ${herdInfo.herd_id}</strong><br/>
        <strong>Size:</strong> ${herdInfo.estimated_size}<br/>
        <strong>Threat Level:</strong> <span style="color: #ef4444; font-weight: bold;">CRITICAL</span><br/>
        <strong>Speed:</strong> ${herdInfo.speed_kmh} km/h (Heading ${herdInfo.heading_degree}° NW)<br/>
        <strong>Heading Towards:</strong> Jigani Agricultural Lands
      </div>
    `).openPopup();
    herdMarkers.push(herdMarker);

    // Render Danger Buffer Circle (1.5 km radius)
    const dangerCircle = L.circle([herdInfo.current_lat, herdInfo.current_lng], {
      color: '#ef4444',
      fillColor: '#ef4444',
      fillOpacity: 0.15,
      radius: 1500
    }).addTo(leafletMap);
    riskCircles.push(dangerCircle);

    // Render Trajectory Vector Polyline
    const pathCoords = herdInfo.path.map(pt => [pt.lat, pt.lng]);
    pathPolyline = L.polyline(pathCoords, {
      color: '#ef4444',
      weight: 3,
      dashArray: '6, 8',
      lineCap: 'round'
    }).addTo(leafletMap);
  }

  // 3. Real-Time Cursor Tracking & Geotargeted Reverse Geocoding
  let reverseGeoTimer = null;

  leafletMap.on('mousemove', (e) => {
    const lat = e.latlng.lat.toFixed(4);
    const lng = e.latlng.lng.toFixed(4);
    const numLat = e.latlng.lat;
    const numLng = e.latlng.lng;

    // 1. Instantaneous Regional Location Finder (0ms latency)
    const instantLocation = getInstantRegionName(numLat, numLng);

    // Update Main Title Line (Location Name ONLY - No repeated Lat/Lng)
    const titleTextEl = document.getElementById('map-title-text');
    if (titleTextEl) {
      titleTextEl.innerHTML = `Location: <strong style="color: #10b981;">${instantLocation}</strong>`;
    }

    // Keep Lat & Lng in the controls bar below
    const coordEl = document.getElementById('live-cursor-coordinates');
    if (coordEl) {
      coordEl.innerHTML = `<i class="fa-solid fa-location-crosshairs" style="color: #10b981;"></i> <strong>Cursor Position:</strong> ${lat}° N, ${lng}° E &nbsp;(<span style="color: #6ee7b7;">${instantLocation}</span>)`;
    }

    const headerTag = document.getElementById('map-location-tag');
    if (headerTag) {
      headerTag.textContent = `${lat}° N, ${lng}° E`;
    }

    // 3. Keep popups showing actual node GPS coordinates (NOT cursor position)
    // Cursor position is shown separately in the header
    // Node coordinates remain as the single source of truth from ESP32

    // 4. Debounced Exact Reverse Geocoding API for exact village/town/district precision anywhere in the world
    if (reverseGeoTimer) clearTimeout(reverseGeoTimer);
    reverseGeoTimer = setTimeout(() => {
      fetchReverseGeocode(numLat, numLng, titleTextEl, coordEl);
    }, 300);
  });

  leafletMap.on('mouseout', () => {
    if (reverseGeoTimer) clearTimeout(reverseGeoTimer);
    const titleTextEl = document.getElementById('map-title-text');
    if (titleTextEl) {
      titleTextEl.textContent = 'Bannerghatta National Park - Live Elephant Trajectory GIS Map';
    }
  });
}

function fetchReverseGeocode(lat, lng, titleEl, coordEl) {
  fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}&zoom=12`, {
    headers: { 'Accept-Language': 'en' }
  })
  .then(res => res.json())
  .then(data => {
    if (data && data.address) {
      const addr = data.address;
      const place = addr.village || addr.town || addr.city || addr.suburb || addr.county || addr.state_district || addr.district || '';
      const state = addr.state || addr.country || '';
      const fullName = place && state ? `${place}, ${state}` : (data.display_name.split(',').slice(0, 2).join(','));

      if (titleEl && fullName) {
        titleEl.innerHTML = `Location: <strong style="color: #10b981;">${fullName}</strong>`;
      }
      if (coordEl && fullName) {
        coordEl.innerHTML = `<i class="fa-solid fa-location-crosshairs" style="color: #10b981;"></i> <strong>Cursor Position:</strong> ${lat.toFixed(4)}° N, ${lng.toFixed(4)}° E &nbsp;(<span style="color: #6ee7b7;">${fullName}</span>)`;
      }
      // Popups remain showing actual node GPS coordinates, not cursor position
    }
  })
  .catch(() => {
    // Fallback gracefully to instant region calculation if offline or rate limited
  });
}

function getInstantRegionName(lat, lng) {
  // 1. ESP32 Specific Sensor Field Node Locations
  if (Math.hypot(lat - 12.8224, lng - 77.5770) < 0.015) return "Buthanahalli (Bannerghatta NP Fringe, KA)";
  if (Math.hypot(lat - 12.79213, lng - 77.61622) < 0.015) return "Begihalli (Anekal Taluk, KA)";
  if (Math.hypot(lat - 12.5195, lng - 77.8200) < 0.015) return "Bettamugilalam (Hosur-Denkanikottai, TN)";
  if (Math.hypot(lat - 12.7180, lng - 77.5840) < 0.015) return "Ragihalli Village (Bengaluru Urban, KA)";
  if (Math.hypot(lat - 12.6100, lng - 77.7100) < 0.015) return "Thammanayakanahalli (Anekal Area, Bengaluru Urban, KA)";
  if (Math.hypot(lat - 12.5400, lng - 77.7800) < 0.015) return "Kadusivanapalli (Jawalagiri Area, Krishnagiri, TN)";

  // 2. TAMIL NADU STATE REGIONS (Exact Geofencing)
  if (lat >= 12.65 && lng >= 77.72 && lng <= 78.10) return "Hosur Sector, Krishnagiri District, Tamil Nadu";
  if (lat >= 12.40 && lat < 12.65 && lng >= 77.62 && lng <= 78.00) return "Denkanikottai / Thally Range, Tamil Nadu";
  if (lat >= 12.10 && lat < 12.50 && lng >= 77.20 && lng < 77.70) return "Cauvery North Wildlife Sanctuary, Tamil Nadu";
  if (lat >= 12.00 && lat < 12.60 && lng >= 77.70 && lng < 78.50) return "Krishnagiri District, Tamil Nadu";
  if (lat >= 11.50 && lat < 12.20 && lng >= 77.50 && lng < 78.50) return "Dharmapuri / Salem District, Tamil Nadu";
  if (lat >= 11.00 && lat < 12.80 && lng >= 78.50 && lng < 80.00) return "Vellore / Tiruvannamalai District, Tamil Nadu";
  if (lat >= 8.00 && lat < 13.50 && lng >= 76.50 && lng <= 80.50) {
    if (lng >= 77.60 && lat < 12.67) return "Krishnagiri / Dharmapuri, Tamil Nadu";
    return "Tamil Nadu State Region";
  }

  // 3. KARNATAKA STATE REGIONS
  if (lat >= 12.67 && lat <= 12.75 && lng >= 77.62 && lng <= 77.75) return "Anekal Taluk, Bengaluru Urban, Karnataka";
  if (lat >= 12.75 && lat <= 12.82 && lng >= 77.62 && lng <= 77.68) return "Jigani Industrial Sector, Karnataka";
  if (lat >= 12.70 && lat <= 12.82 && lng >= 77.50 && lng <= 77.61) return "Bannerghatta National Park Reserve Forest, Karnataka";
  if (lat >= 12.83 && lat <= 13.20 && lng >= 77.45 && lng <= 77.75) return "Bengaluru Metropolitan Area, Karnataka";
  if (lat >= 12.30 && lat < 12.70 && lng >= 76.40 && lng < 77.40) return "Ramanagara / Mandya District, Karnataka";
  if (lat >= 13.00 && lat < 13.80 && lng >= 77.80 && lng < 78.60) return "Kolar / Chikkaballapura District, Karnataka";
  if (lat >= 11.50 && lat < 18.50 && lng >= 74.00 && lng <= 78.50) return "Karnataka State Region";

  // 4. OTHER STATES & GLOBAL REGIONS
  if (lat >= 13.10 && lng >= 78.30) return "Chittoor District, Andhra Pradesh";
  if (lat >= 8.50 && lat < 12.80 && lng >= 74.80 && lng < 77.20) return "Kerala State Region";

  return `Coordinates: ${lat.toFixed(2)}°, ${lng.toFixed(2)}°`;
}

function filterMap(category) {
  // Filter logic for map layers
  const btns = document.querySelectorAll('.map-filter-btn');
  btns.forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');

  if (!leafletMap) return;

  if (category === 'all') {
    nodeMarkers.forEach(m => leafletMap.addLayer(m));
    herdMarkers.forEach(m => leafletMap.addLayer(m));
    if (pathPolyline) leafletMap.addLayer(pathPolyline);
  } else if (category === 'nodes') {
    nodeMarkers.forEach(m => leafletMap.addLayer(m));
    herdMarkers.forEach(m => leafletMap.removeLayer(m));
    if (pathPolyline) leafletMap.removeLayer(pathPolyline);
  } else if (category === 'herds') {
    nodeMarkers.forEach(m => leafletMap.removeLayer(m));
    herdMarkers.forEach(m => leafletMap.addLayer(m));
    if (pathPolyline) leafletMap.addLayer(pathPolyline);
  }
}

let lastAlertedMapNodeId = null;

function updateMapNodes(nodes, herdInfo) {
  if (!leafletMap) return;

  const nodeAlertIcon = L.divIcon({
    className: 'custom-leaflet-icon',
    html: `<div style="background: rgba(239, 68, 68, 0.95); border: 2px solid #fff; width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 16px; box-shadow: 0 0 20px rgba(239, 68, 68, 0.9);"><i class="fa-solid fa-triangle-exclamation"></i></div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17]
  });

  const nodeSafeIcon = L.divIcon({
    className: 'custom-leaflet-icon',
    html: `<div style="background: rgba(16, 185, 129, 0.85); border: 2px solid #fff; width: 26px; height: 26px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 12px;"><i class="fa-solid fa-microchip"></i></div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13]
  });

  // Clear previous dynamic risk circles
  riskCircles.forEach(c => leafletMap.removeLayer(c));
  riskCircles = [];

  let alertNodeFound = null;

  nodes.forEach((node, index) => {
    const isAlert = node.status === 'ALERT';
    if (isAlert) alertNodeFound = node;

    // Match marker by array index or node ID
    const marker = nodeMarkers[index];
    if (marker) {
      marker.setLatLng([node.lat, node.lng]);
      marker.setIcon(isAlert ? nodeAlertIcon : nodeSafeIcon);
      marker.nodeData = node; // Update node data reference
      
      // Use node's actual GPS coordinates as single source of truth
      const nodeCoords = {
        latitude: node.lat,
        longitude: node.lng
      };
      
      // Dynamic node name based on location for Node 1
      const dynamicNodeName = node.id === 'ESP32-NODE-01' 
        ? `Node 1 - ${node.location}` 
        : node.name;
      
      marker.setPopupContent(`
        <div style="font-family: Inter, sans-serif; font-size: 12px; padding: 4px;">
          <strong style="color: ${isAlert ? '#ef4444' : '#10b981'}; font-size: 14px;">${dynamicNodeName}</strong><br/>
          <strong>Status:</strong> ${isAlert ? '🚨 CRITICAL ELEPHANT INTRUSION' : 'SAFE / MONITORING'}<br/>
          <strong>Location:</strong> ${node.location}<br/>
          <strong>Node 1 Position:</strong> ${nodeCoords.latitude.toFixed(4)}° N, ${nodeCoords.longitude.toFixed(4)}° E<br/>
          <strong>PIR:</strong> ${node.pir ? 'Detected' : 'Clear'}<br/>
          <strong>Sound:</strong> ${node.acoustic_db}<br/>
          <strong>Sound Class:</strong> ${node.sound_class} (${node.confidence}%)<br/>
          <strong>Battery/Solar:</strong> ${node.battery}% (${node.solar_v}V)
        </div>
      `);
    }

    if (isAlert) {
      const circle = L.circle([node.lat, node.lng], {
        color: '#ef4444',
        fillColor: '#ef4444',
        fillOpacity: 0.2,
        radius: 1500
      }).addTo(leafletMap);
      riskCircles.push(circle);
    }
  });

  // Pan to alerted node area
  if (alertNodeFound && lastAlertedMapNodeId !== alertNodeFound.id) {
    lastAlertedMapNodeId = alertNodeFound.id;
    leafletMap.flyTo([alertNodeFound.lat, alertNodeFound.lng], 13, { duration: 1.2 });
    
    // Open popup for alerted node
    const alertedIndex = nodes.findIndex(n => n.id === alertNodeFound.id);
    if (alertedIndex >= 0 && nodeMarkers[alertedIndex]) {
      nodeMarkers[alertedIndex].openPopup();
    }
  } else if (!alertNodeFound) {
    lastAlertedMapNodeId = null;
  }
}

