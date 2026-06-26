import { DateTimeUtils, MagnitudeUtils, FileUtils } from './utils.js';

export class UIManager {
    constructor() {
        this.elements = {
            statusBar:          document.getElementById('statusBar'),
            loadBtn:            document.getElementById('loadData'),
            exportBtn:          document.getElementById('exportData'),
            lastUpdateText:     document.getElementById('lastUpdateText'),
            totalCount:         document.getElementById('totalCount'),
            maxMagnitude:       document.getElementById('maxMagnitude'),
            maxMagLocation:     document.getElementById('maxMagLocation'),
            avgMagnitude:       document.getElementById('avgMagnitude'),
            lastEarthquake:     document.getElementById('lastEarthquake'),
            lastEarthquakeTime: document.getElementById('lastEarthquakeTime'),
            earthquakeList:     document.getElementById('earthquakeList'),
            magFilter:          document.getElementById('magFilter'),
            magFilterVal:       document.getElementById('magFilterVal'),
            sortToggle:         document.getElementById('sortToggle'),
        };
        this.sortByMag = false;
        this._onItemClick = null;
    }

    showLoading(message = 'Cargando...') {
        const sb = this.elements.statusBar;
        sb.textContent = message;
        sb.className = 'status-bar visible loading';
        this.elements.loadBtn.disabled = true;
    }

    showSuccess(message) {
        const sb = this.elements.statusBar;
        sb.textContent = message;
        sb.className = 'status-bar visible success';
        this.elements.loadBtn.disabled = false;
        setTimeout(() => { sb.className = 'status-bar'; }, 3000);
    }

    showError(message) {
        const sb = this.elements.statusBar;
        sb.textContent = message;
        sb.className = 'status-bar visible error';
        this.elements.loadBtn.disabled = false;
        setTimeout(() => { sb.className = 'status-bar'; }, 5000);
    }

    updateLastUpdateTime() {
        const now = new Date();
        const h = now.getHours().toString().padStart(2, '0');
        const m = now.getMinutes().toString().padStart(2, '0');
        if (this.elements.lastUpdateText) {
            this.elements.lastUpdateText.textContent = `Actualizado ${h}:${m}`;
        }
    }

    updateStats(data) {
        const features = data.features;
        this.elements.totalCount.textContent = features.length;

        const mags = features.map(f => parseFloat(f.properties.value) || 0);
        const maxMag = mags.length ? Math.max(...mags) : 0;
        const avgMag = mags.length ? mags.reduce((a, b) => a + b, 0) / mags.length : 0;

        this.elements.maxMagnitude.textContent = maxMag.toFixed(1);
        this.elements.avgMagnitude.textContent = avgMag.toFixed(1);

        const biggest = features.reduce((best, f) => {
            const m = parseFloat(f.properties.value) || 0;
            return (!best || m > (parseFloat(best.properties.value) || 0)) ? f : best;
        }, null);

        if (biggest && this.elements.maxMagLocation) {
            const loc = biggest.properties.addressFormatted || '';
            this.elements.maxMagLocation.textContent = loc.split(',')[0] || loc;
        }

        const latest = DateTimeUtils.getLatestEarthquake(features);
        if (latest) {
            this.elements.lastEarthquake.textContent =
                (latest.properties.addressFormatted || '-').split(',')[0];
            this.elements.lastEarthquakeTime.textContent =
                `${latest.properties.date} - ${DateTimeUtils.convertTo12Hour(latest.properties.time)}`;
        }

        this.updateLastUpdateTime();
    }

    renderEarthquakes(data, minMag = 0, sortByMag = false) {
        const features = data.features.filter(
            f => (parseFloat(f.properties.value) || 0) >= minMag
        );

        if (features.length === 0) {
            const msg = data.features.length === 0
                ? 'Recopilando datos, vuelve en unos minutos...'
                : `Sin sismos con magnitud >= ${minMag.toFixed(1)}`;
            this.elements.earthquakeList.innerHTML =
                `<div style="padding:24px;text-align:center;color:var(--text3);font-size:13px">${msg}</div>`;
            return;
        }

        const sorted = [...features].sort((a, b) => {
            if (sortByMag) {
                return (parseFloat(b.properties.value) || 0) - (parseFloat(a.properties.value) || 0);
            }
            return DateTimeUtils.parseDateTime(b.properties.date, b.properties.time) -
                   DateTimeUtils.parseDateTime(a.properties.date, a.properties.time);
        });

        this.elements.earthquakeList.innerHTML = sorted.map((feature, i) => {
            const mag = parseFloat(feature.properties.value) || 0;
            const cls = MagnitudeUtils.getMagnitudeClass(mag);
            const loc = feature.properties.addressFormatted || '-';
            const depth = feature.properties.depth || '-';
            const time = DateTimeUtils.convertTo12Hour(feature.properties.time);

            const rel = DateTimeUtils.getRelativeTime(feature.properties.date, feature.properties.time);
            return `<div class="earthquake-item" role="listitem" data-idx="${i}" data-lat="${feature.properties.lat}" data-lng="${feature.properties.long}">
                <div class="eq-mag-badge ${cls}">${mag.toFixed(1)}</div>
                <div class="eq-info">
                    <div class="eq-loc">${loc}</div>
                    <div class="eq-meta">${feature.properties.date} - ${time}</div>
                    ${rel ? `<div class="eq-rel-time">${rel}</div>` : ''}
                </div>
                <div class="eq-depth">${depth}<span>prof.</span></div>
            </div>`;
        }).join('');

        this.elements.earthquakeList.querySelectorAll('.earthquake-item').forEach(el => {
            el.addEventListener('click', () => {
                document.querySelectorAll('.earthquake-item').forEach(e => e.classList.remove('active'));
                el.classList.add('active');
                if (this._onItemClick) {
                    this._onItemClick(parseFloat(el.dataset.lat), parseFloat(el.dataset.lng));
                }
            });
        });
    }

    highlightEarthquake(index) {
        const items = document.querySelectorAll('.earthquake-item');
        if (items[index]) {
            items[index].scrollIntoView({ behavior: 'smooth', block: 'center' });
            document.querySelectorAll('.earthquake-item').forEach(e => e.classList.remove('active'));
            items[index].classList.add('active');
        }
    }

    exportData(data) {
        const filename = FileUtils.generateFilename('sismos_ve');
        FileUtils.downloadJSON(data, filename);
    }

    bindEvents(callbacks) {
        if (this.elements.loadBtn && callbacks.onLoadData) {
            this.elements.loadBtn.addEventListener('click', callbacks.onLoadData);
        }
        if (this.elements.exportBtn && callbacks.onExportData) {
            this.elements.exportBtn.addEventListener('click', callbacks.onExportData);
        }
        if (this.elements.magFilter) {
            this.elements.magFilter.addEventListener('input', e => {
                const val = parseFloat(e.target.value);
                if (this.elements.magFilterVal) this.elements.magFilterVal.textContent = val.toFixed(1);
                if (callbacks.onFilterChange) callbacks.onFilterChange({ minMag: val });
            });
        }
        if (this.elements.sortToggle) {
            this.elements.sortToggle.addEventListener('click', () => {
                this.sortByMag = !this.sortByMag;
                this.elements.sortToggle.textContent = this.sortByMag ? 'Fecha' : 'Magnitud';
                if (callbacks.onSortChange) callbacks.onSortChange(this.sortByMag);
            });
        }
        document.querySelectorAll('.pill[data-period]').forEach(pill => {
            pill.addEventListener('click', () => {
                document.querySelectorAll('.pill[data-period]').forEach(p => p.classList.remove('active'));
                pill.classList.add('active');
                if (callbacks.onPeriodChange) callbacks.onPeriodChange(pill.dataset.period);
            });
        });
        if (callbacks.onItemClick) {
            this._onItemClick = callbacks.onItemClick;
        }
    }
}
