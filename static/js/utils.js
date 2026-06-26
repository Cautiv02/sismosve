export class DateTimeUtils {
    static parseDateTime(date, time) {
        try {
            const [day, month, year] = date.split('-');
            const [hours, minutes] = time.split(':');
            return new Date(year, month - 1, day, hours, minutes);
        } catch {
            return new Date(0);
        }
    }

    static convertTo12Hour(time24) {
        try {
            const [hours, minutes] = time24.split(':');
            const hour24 = parseInt(hours, 10);
            const hour12 = hour24 === 0 ? 12 : hour24 > 12 ? hour24 - 12 : hour24;
            const ampm = hour24 >= 12 ? 'PM' : 'AM';
            return `${hour12}:${minutes} ${ampm}`;
        } catch {
            return time24;
        }
    }

    static getRelativeTime(date, time) {
        try {
            const eventDt = this.parseDateTime(date, time);
            // Corregir diferencia entre timezone del browser y VET (UTC-4)
            const VET_OFFSET_MIN = 240; // VET = UTC-4 → getTimezoneOffset() = 240
            const correctionMs = (VET_OFFSET_MIN - new Date().getTimezoneOffset()) * 60000;
            const eventEpoch = eventDt.getTime() + correctionMs;
            const diffMs = Date.now() - eventEpoch;
            if (diffMs < 0) return 'ahora';
            const mins = Math.floor(diffMs / 60000);
            if (mins < 1)  return 'hace <1 min';
            if (mins < 60) return `hace ${mins} min`;
            const hrs = Math.floor(mins / 60);
            const remMin = mins % 60;
            if (hrs < 24)  return remMin > 0 ? `hace ${hrs}h ${remMin}min` : `hace ${hrs}h`;
            const days = Math.floor(hrs / 24);
            return `hace ${days}d`;
        } catch {
            return '';
        }
    }

    static getLatestEarthquake(features) {
        return features.reduce((latest, current) => {
            if (!latest) return current;
            const currentDT = this.parseDateTime(current.properties.date, current.properties.time);
            const latestDT  = this.parseDateTime(latest.properties.date,  latest.properties.time);
            return currentDT > latestDT ? current : latest;
        }, null);
    }
}

export class MagnitudeUtils {
    static getMagnitudeClass(magnitude) {
        if (magnitude >= 3.5) return 'high';
        if (magnitude >= 2.5) return 'medium';
        return 'low';
    }

    static getMarkerStyle(magnitude) {
        if (magnitude >= 3.5) return { color: '#D85A30', radius: 13 };
        if (magnitude >= 2.5) return { color: '#EF9F27', radius: 9 };
        return { color: '#4ecf9e', radius: 6 };
    }
}

export class FileUtils {
    static downloadJSON(data, filename) {
        const dataStr  = JSON.stringify(data, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(dataBlob);
        link.download = filename;
        link.click();
        URL.revokeObjectURL(link.href);
    }

    static generateFilename(prefix, extension = 'json') {
        const today = new Date().toISOString().split('T')[0];
        return `${prefix}_${today}.${extension}`;
    }
}

export class ValidationUtils {
    static isValidEarthquakeData(data) {
        return data &&
               typeof data === 'object' &&
               Array.isArray(data.features);
    }

    static hasEarthquakes(data) {
        return this.isValidEarthquakeData(data) && data.features.length > 0;
    }

    static isValidCoordinates(lat, lng) {
        return !isNaN(lat) && !isNaN(lng) &&
               lat >= -90 && lat <= 90 &&
               lng >= -180 && lng <= 180;
    }
}
