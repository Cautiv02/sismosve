import { ApiService, DataManager } from './api-service.js';
import { UIManager } from './ui-manager.js';
import { MapManager } from './map-manager.js';
import { DateTimeUtils } from './utils.js';

export class SismosApp {
    constructor() {
        this.apiService = new ApiService();
        this.dataManager = new DataManager(this.apiService);
        this.uiManager = new UIManager();
        this.mapManager = new MapManager();

        this.isLoading = false;
        this.minMag = 0;
        this.period = '24h';
        this.sortByMag = false;

        this.init();
    }

    init() {
        this.bindEvents();
        this.bindMapControls();
        this.loadData();
        window.mapHighlightCallback = (index) => this.uiManager.highlightEarthquake(index);
    }

    bindMapControls() {
        const baseBtns = { layerDark: 'dark', layerSat: 'sat', layerTerrain: 'terrain' };
        Object.entries(baseBtns).forEach(([id, name]) => {
            const btn = document.getElementById(id);
            if (!btn) return;
            btn.addEventListener('click', () => {
                this.mapManager.setBaseLayer(name);
                Object.keys(baseBtns).forEach(k => document.getElementById(k)?.classList.remove('active'));
                btn.classList.add('active');
            });
        });

        ['layerTectonic', 'layerFaults'].forEach(id => {
            const btn = document.getElementById(id);
            if (!btn) return;
            const overlay = id === 'layerTectonic' ? 'tectonic' : 'faults';
            btn.addEventListener('click', () => {
                const on = this.mapManager.toggleOverlay(overlay);
                btn.classList.toggle('active', on);
            });
        });
    }

    bindEvents() {
        this.uiManager.bindEvents({
            onLoadData:    () => this.loadData(),
            onExportData:  () => this.exportData(),
            onFilterChange: ({ minMag }) => { this.minMag = minMag; this.refreshDisplay(); },
            onSortChange:  (sortByMag) => { this.sortByMag = sortByMag; this.refreshDisplay(); },
            onPeriodChange: (period) => { this.period = period; this._updatePeriodLabel(); this.refreshDisplay(); },
            onItemClick:   (lat, lng) => this.mapManager.openPopupAt(lat, lng),
        });
    }

    getFilteredData() {
        const data = this.dataManager.getCurrentData();
        if (!data) return null;

        let features = [...data.features];

        if (this.period !== 'all') {
            const now = new Date();
            const ms = this.period === '24h' ? 86400000 : 604800000;
            const cutoff = new Date(now - ms);
            // Réplicas: M>=4.0 ocurridas después del evento principal del 24-06-2026 18:04
            const aftershockCutoff = new Date(2026, 5, 24, 18, 4);
            features = features.filter(f => {
                const dt  = DateTimeUtils.parseDateTime(f.properties.date, f.properties.time);
                const mag = parseFloat(f.properties.value) || 0;
                return dt >= cutoff || (mag >= 4.0 && dt >= aftershockCutoff);
            });
        }

        return { ...data, features };
    }

    _getPeriodLabel() {
        if (this.period === '24h') return 'últimas 24h + réplicas M4+';
        if (this.period === '7d')  return 'últimos 7 días + réplicas M4+';
        return 'todos los eventos';
    }

    _updatePeriodLabel() {
        const el = document.getElementById('totalPeriodLabel');
        if (el) el.textContent = this._getPeriodLabel();
    }

    refreshDisplay() {
        const data = this.getFilteredData();
        if (!data) return;
        this.uiManager.updateStats(data);
        this.uiManager.renderEarthquakes(data, this.minMag, this.sortByMag);
        this.mapManager.updateMap(data, (index) => this.uiManager.highlightEarthquake(index));
    }

    async loadData() {
        if (this.isLoading) return;
        this.isLoading = true;
        this.uiManager.showLoading('Obteniendo datos de FUNVISIS...');

        try {
            const data = await this.dataManager.loadData();
            this.updateUI();
            this.uiManager.showSuccess(`${this.dataManager.getEarthquakeCount()} sismos cargados`);
        } catch (error) {
            console.error('Error al cargar los datos:', error);
            this.uiManager.showError('Error al cargar datos. Reintenta.');
            await this.handleFallbackData();
        } finally {
            this.isLoading = false;
        }
    }

    async handleFallbackData() {
        try {
            await this.dataManager.loadFallbackData();
            this.updateUI();
            this.uiManager.showSuccess(`Datos de respaldo (${this.dataManager.getEarthquakeCount()} sismos)`);
        } catch {
            this.uiManager.showError('API no disponible.');
        }
    }

    updateUI() {
        const data = this.getFilteredData();
        if (!data?.features) return;
        this._updatePeriodLabel();
        this.uiManager.updateStats(data);
        this.uiManager.renderEarthquakes(data, this.minMag, this.sortByMag);
        this.mapManager.updateMap(data, (index) => this.uiManager.highlightEarthquake(index));
    }

    exportData() {
        const data = this.dataManager.getCurrentData();
        if (!data) { this.uiManager.showError('No hay datos para exportar'); return; }
        this.uiManager.exportData(data);
    }

    getAppState() {
        return {
            hasData: this.dataManager.hasData(),
            earthquakeCount: this.dataManager.getEarthquakeCount(),
            isLoading: this.isLoading,
            mapReady: this.mapManager.isReady()
        };
    }

    destroy() {
        this.mapManager.destroy();
        window.mapHighlightCallback = null;
    }
}

let app;

document.addEventListener('DOMContentLoaded', () => {
    try {
        app = new SismosApp();
        window.sismosApp = app;
        console.log('SismosVE inicializado');
    } catch (error) {
        console.error('Error al inicializar:', error);
    }
});

export default app;
