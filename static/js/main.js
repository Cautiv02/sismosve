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
        this.period = 'all';
        this.sortByMag = false;

        this.init();
    }

    init() {
        this.bindEvents();
        this.loadData();
        window.mapHighlightCallback = (index) => this.uiManager.highlightEarthquake(index);
    }

    bindEvents() {
        this.uiManager.bindEvents({
            onLoadData:    () => this.loadData(),
            onExportData:  () => this.exportData(),
            onFilterChange: ({ minMag }) => { this.minMag = minMag; this.refreshDisplay(); },
            onSortChange:  (sortByMag) => { this.sortByMag = sortByMag; this.refreshDisplay(); },
            onPeriodChange: (period) => { this.period = period; this.refreshDisplay(); },
            onItemClick:   (lat, lng) => this.mapManager.centerOn(lat, lng),
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
            features = features.filter(f => {
                const dt = DateTimeUtils.parseDateTime(f.properties.date, f.properties.time);
                return dt >= cutoff;
            });
        }

        return { ...data, features };
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
