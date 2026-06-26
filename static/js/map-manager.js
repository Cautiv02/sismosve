import { DateTimeUtils, MagnitudeUtils, ValidationUtils } from './utils.js';

export class MapManager {
    constructor() {
        this.map = null;
        this.markersGroup = null;
        this.initialized = false;
        this.markerIndex = [];
        this.init();
    }

    init() {
        try {
            const center = window.MAP_CENTER || [8.0, -66.0];
            const zoom   = window.MAP_ZOOM   || 6;
            this.map = L.map('map').setView(center, zoom);

            // --- Capas base ---
            const darkLayer = L.tileLayer(
                'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
                { attribution: '&copy; CartoDB', maxZoom: 19 }
            );
            const satelliteLayer = L.tileLayer(
                'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                { attribution: '&copy; ESRI', maxZoom: 19 }
            );
            const terrainLayer = L.tileLayer(
                'https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}',
                { attribution: '&copy; ESRI', maxZoom: 13 }
            );

            satelliteLayer.addTo(this.map);

            // --- Overlay: placas tectónicas ---
            this.tectonicLayer = L.layerGroup();
            fetch('https://raw.githubusercontent.com/fraxen/tectonicplates/master/GeoJSON/PB2002_boundaries.json')
                .then(r => r.json())
                .then(data => {
                    L.geoJSON(data, {
                        style: { color: '#FF6B35', weight: 2, opacity: 0.75, dashArray: '4 3' }
                    }).addTo(this.tectonicLayer);
                })
                .catch(() => {});

            // --- Overlay: fallas principales Venezuela ---
            this.faultsLayer = L.layerGroup();
            const faults = {
                type: 'FeatureCollection',
                features: [
                    { type: 'Feature', properties: { name: 'Falla de Boconó' },
                      geometry: { type: 'LineString', coordinates: [[-72.6,7.9],[-71.5,8.5],[-70.5,9.2],[-69.5,9.8],[-68.5,10.3],[-67.8,10.6]] } },
                    { type: 'Feature', properties: { name: 'Falla de El Pilar' },
                      geometry: { type: 'LineString', coordinates: [[-65.2,10.7],[-64.5,10.6],[-63.5,10.5],[-62.5,10.4],[-61.8,10.3]] } },
                    { type: 'Feature', properties: { name: 'Falla de Oca-Ancón' },
                      geometry: { type: 'LineString', coordinates: [[-73.1,11.2],[-72.0,11.4],[-71.0,11.5],[-70.2,11.6]] } },
                ],
            };
            L.geoJSON(faults, {
                style: { color: '#facc15', weight: 2, opacity: 0.8, dashArray: '6 3' },
                onEachFeature: (f, layer) => layer.bindTooltip(f.properties.name, { sticky: true }),
            }).addTo(this.faultsLayer);

            // Capa de referencia: fronteras + etiquetas (transparente, va sobre satélite)
            this.labelsLayer = L.tileLayer(
                'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
                { attribution: '&copy; ESRI', maxZoom: 19, opacity: 0.9 }
            );

            // Etiquetas + fronteras activas por defecto (sobre satélite)
            this.labelsLayer.addTo(this.map);

            // Placas y fallas activas por defecto
            this.tectonicLayer.addTo(this.map);
            this.faultsLayer.addTo(this.map);

            // Guardar referencias para switching externo
            this.baseLayers = { dark: darkLayer, sat: satelliteLayer, terrain: terrainLayer };
            this.currentBase = satelliteLayer;

            this.markersGroup = L.layerGroup().addTo(this.map);
            L.control.scale({ imperial: false }).addTo(this.map);

            this.initialized = true;
        } catch (error) {
            console.error('Error al inicializar el mapa:', error);
        }
    }

    isReady() {
        return this.initialized && this.map && this.markersGroup;
    }

    updateMap(data, highlightCallback = null) {
        if (!this.isReady() || !ValidationUtils.isValidEarthquakeData(data)) return;

        this.markersGroup.clearLayers();
        this.markerIndex = [];

        const features = data.features;
        const bounds = [];

        features.forEach((feature, index) => {
            const lat = parseFloat(feature.properties.lat);
            const lng = parseFloat(feature.properties.long);

            if (!ValidationUtils.isValidCoordinates(lat, lng)) return;

            bounds.push([lat, lng]);
            const marker = this.createMarker(feature, index, highlightCallback);
            this.markersGroup.addLayer(marker);
            this.markerIndex.push({ marker, lat, lng, feature });
        });

        if (bounds.length > 0) {
            this.map.fitBounds(bounds, { padding: [30, 30] });
        }
    }

    createMarker(feature, index, highlightCallback) {
        const lat = parseFloat(feature.properties.lat);
        const lng = parseFloat(feature.properties.long);
        const magnitude = parseFloat(feature.properties.value) || 0;

        let marker;

        if (magnitude >= 6.0) {
            const size  = magnitude >= 7.0 ? 42 : 32;
            const color = magnitude >= 7.0 ? '#ef4444' : '#FFD700';
            const glow  = magnitude >= 7.0
                ? '0 0 8px rgba(239,68,68,0.9), 0 0 16px rgba(239,68,68,0.5)'
                : '0 0 8px rgba(255,215,0,0.9), 0 0 16px rgba(255,215,0,0.5)';

            const icon = L.divIcon({
                html: `<div style="
                    width:${size}px;height:${size}px;
                    font-size:${size}px;line-height:1;
                    color:${color};
                    filter:drop-shadow(0 0 6px ${color});
                    text-shadow:${glow};
                    display:flex;align-items:center;justify-content:center;
                    animation:starPulse 1.5s ease-in-out infinite;
                ">★</div>`,
                className: '',
                iconSize: [size, size],
                iconAnchor: [size / 2, size / 2],
            });

            marker = L.marker([lat, lng], { icon });
        } else {
            const { color, radius } = MagnitudeUtils.getMarkerStyle(magnitude);
            marker = L.circleMarker([lat, lng], {
                radius,
                fillColor: color,
                color: 'rgba(255,255,255,0.3)',
                weight: 1.5,
                opacity: 1,
                fillOpacity: 0.85
            });
        }

        marker.bindPopup(this.createPopupContent(feature, index, highlightCallback), {
            maxWidth: 240,
            className: 'dark-popup'
        });

        marker.on('mouseover', function() { this.openPopup(); });

        return marker;
    }

    createPopupContent(feature, index, highlightCallback) {
        const magnitude = parseFloat(feature.properties.value) || 0;
        const cls = MagnitudeUtils.getMagnitudeClass(magnitude);
        const loc = feature.properties.addressFormatted || '-';
        const depth = feature.properties.depth || '-';
        const time = DateTimeUtils.convertTo12Hour(feature.properties.time);

        const btnHtml = highlightCallback
            ? `<button onclick="window.mapHighlightCallback(${index})" class="popup-button">Ver en lista</button>`
            : '';

        return `<div class="popup-content">
            <div class="popup-mag ${cls}">${magnitude.toFixed(1)}</div>
            <div class="popup-loc">${loc}</div>
            <div class="popup-row">
                <div class="popup-item"><strong>${feature.properties.date}</strong>fecha</div>
                <div class="popup-item"><strong>${time}</strong>hora</div>
                <div class="popup-item"><strong>${depth}</strong>prof.</div>
            </div>
            ${btnHtml}
        </div>`;
    }

    centerOn(lat, lng, zoom = 9) {
        if (!this.isReady() || isNaN(lat) || isNaN(lng)) return;
        this.map.setView([lat, lng], zoom, { animate: true });
    }

    openPopupAt(lat, lng) {
        if (!this.isReady()) return;

        const entry = this.markerIndex.find(m =>
            Math.abs(m.lat - lat) < 0.001 && Math.abs(m.lng - lng) < 0.001
        );
        if (!entry) { this.centerOn(lat, lng); return; }

        // Reset highlight on all circle markers
        this.markerIndex.forEach(({ marker }) => {
            if (marker.setStyle) {
                marker.setStyle({ weight: 1.5, color: 'rgba(255,255,255,0.3)', opacity: 1 });
            }
        });

        // Highlight selected marker
        if (entry.marker.setStyle) {
            entry.marker.setStyle({ weight: 3, color: '#ffffff', opacity: 1 });
        }

        this.map.setView([lat, lng], 9, { animate: true });
        setTimeout(() => entry.marker.openPopup(), 300);
    }

    centerOnEarthquake(feature, zoomLevel = 9) {
        const lat = parseFloat(feature.properties.lat);
        const lng = parseFloat(feature.properties.long);
        this.centerOn(lat, lng, zoomLevel);
    }

    resetView() {
        if (!this.isReady()) return;
        this.map.setView(window.MAP_CENTER || [8.0, -66.0], window.MAP_ZOOM || 6);
    }

    clearMarkers() {
        if (this.markersGroup) this.markersGroup.clearLayers();
    }

    invalidateSize() {
        if (this.isReady()) {
            setTimeout(() => this.map.invalidateSize(), 100);
        }
    }

    setBaseLayer(name) {
        if (!this.isReady()) return;
        const layer = this.baseLayers[name];
        if (!layer || layer === this.currentBase) return;
        this.map.removeLayer(this.currentBase);
        layer.addTo(this.map);
        layer.bringToBack();
        this.currentBase = layer;
        // Filtro de brillo solo en capa oscura
        const pane = this.map.getPanes().tilePane;
        if (pane) pane.style.filter = name === 'dark' ? 'brightness(0.85) saturate(0.7)' : 'none';
        // Etiquetas/fronteras solo sobre satélite y relieve
        if (name === 'dark') {
            if (this.map.hasLayer(this.labelsLayer)) this.map.removeLayer(this.labelsLayer);
        } else {
            if (!this.map.hasLayer(this.labelsLayer)) this.labelsLayer.addTo(this.map);
        }
        this.markersGroup.bringToFront();
    }

    toggleOverlay(name) {
        if (!this.isReady()) return;
        const layer = name === 'tectonic' ? this.tectonicLayer : this.faultsLayer;
        if (!layer) return;
        if (this.map.hasLayer(layer)) {
            this.map.removeLayer(layer);
            return false;
        } else {
            layer.addTo(this.map);
            return true;
        }
    }

    destroy() {
        if (this.map) {
            this.map.remove();
            this.map = null;
            this.markersGroup = null;
            this.initialized = false;
        }
    }
}

