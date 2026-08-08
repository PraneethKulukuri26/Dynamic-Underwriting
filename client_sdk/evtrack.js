/**
 * AIDUS EvTrack Client SDK
 * Captures behavioral biometrics (mouse/touch trajectories) and device fingerprints.
 */

class EvTrack {
    constructor(config = {}) {
        this.endpoint = config.endpoint || 'http://localhost:8000/api/v1/biometrics';
        this.sessionToken = config.sessionToken || this._generateToken();
        this.applicantId = config.applicantId || null;
        this.batchSize = config.batchSize || 50;
        this.pollingInterval = config.pollingInterval || 150; // ms

        this.points = [];
        this.isTracking = false;
        this.trackingInterval = null;
        
        // Current state for polling
        this.currentX = 0;
        this.currentY = 0;
        this.lastEventType = 'move';
        
        this.sessionStartTime = Date.now();
    }

    _generateToken() {
        return 'sess_' + Math.random().toString(36).substr(2, 9) + Date.now().toString(36);
    }

    async init() {
        console.log(`[EvTrack] Initializing with session token: ${this.sessionToken}`);
        
        // Generate and send device fingerprint
        const fingerprint = await this._generateFingerprint();
        await this._sendFingerprint(fingerprint);

        // Start tracking
        this._attachListeners();
        this.startTracking();
        
        return this.sessionToken;
    }

    _attachListeners() {
        // Track mouse movements
        window.addEventListener('mousemove', (e) => {
            this.currentX = e.clientX;
            this.currentY = e.clientY;
            this.lastEventType = 'move';
        }, { passive: true });

        // Track clicks
        window.addEventListener('click', (e) => {
            this.currentX = e.clientX;
            this.currentY = e.clientY;
            this.lastEventType = 'click';
            this._recordPoint(); // Immediately record clicks
        }, { passive: true });

        // Track scrolling
        window.addEventListener('scroll', () => {
            this.lastEventType = 'scroll';
        }, { passive: true });

        // Touch support
        window.addEventListener('touchmove', (e) => {
            if (e.touches.length > 0) {
                this.currentX = e.touches[0].clientX;
                this.currentY = e.touches[0].clientY;
                this.lastEventType = 'touch';
            }
        }, { passive: true });
    }

    startTracking() {
        if (this.isTracking) return;
        this.isTracking = true;
        this.trackingInterval = setInterval(() => this._recordPoint(), this.pollingInterval);
    }

    stopTracking() {
        this.isTracking = false;
        if (this.trackingInterval) {
            clearInterval(this.trackingInterval);
            this.trackingInterval = null;
        }
        // Flush remaining points
        if (this.points.length > 0) {
            this._flushPoints();
        }
    }

    _recordPoint() {
        const timestampMs = Date.now() - this.sessionStartTime;
        
        this.points.push({
            x: this.currentX,
            y: this.currentY,
            timestamp_ms: timestampMs,
            event_type: this.lastEventType
        });

        // Reset event type back to move after special events
        if (this.lastEventType === 'click' || this.lastEventType === 'scroll') {
            this.lastEventType = 'move';
        }

        if (this.points.length >= this.batchSize) {
            this._flushPoints();
        }
    }

    async _flushPoints() {
        if (this.points.length === 0) return;

        const batch = [...this.points];
        this.points = []; // Clear for next batch

        try {
            await fetch(`${this.endpoint}/trajectory`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_token: this.sessionToken,
                    applicant_id: this.applicantId,
                    points: batch
                })
            });
        } catch (error) {
            console.error('[EvTrack] Failed to send trajectory batch:', error);
            // In a production SDK, we'd implement retry logic or IndexedDB buffering here
        }
    }

    async _generateFingerprint() {
        const fp = {
            session_token: this.sessionToken,
            user_agent: navigator.userAgent,
            platform: navigator.platform,
            screen_resolution: `${window.screen.width}x${window.screen.height}`,
            timezone_offset: new Date().getTimezoneOffset(),
            language: navigator.language,
            color_depth: window.screen.colorDepth,
            hardware_concurrency: navigator.hardwareConcurrency || 1,
        };

        // Canvas Hash
        try {
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            ctx.textBaseline = "top";
            ctx.font = "14px 'Arial'";
            ctx.textBaseline = "alphabetic";
            ctx.fillStyle = "#f60";
            ctx.fillRect(125,1,62,20);
            ctx.fillStyle = "#069";
            ctx.fillText("AIDUS Fingerprint 2024", 2, 15);
            ctx.fillStyle = "rgba(102, 204, 0, 0.7)";
            ctx.fillText("AIDUS Fingerprint 2024", 4, 17);
            
            const dataUrl = canvas.toDataURL();
            fp.canvas_hash = await this._sha256(dataUrl);
        } catch (e) {
            console.warn('[EvTrack] Canvas fingerprint failed', e);
        }

        // WebGL Info
        try {
            const canvas = document.createElement('canvas');
            const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
            if (gl) {
                const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
                if (debugInfo) {
                    fp.webgl_vendor = gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL);
                    fp.webgl_renderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
                    fp.webgl_hash = await this._sha256(`${fp.webgl_vendor}|${fp.webgl_renderer}`);
                }
            }
        } catch (e) {
            console.warn('[EvTrack] WebGL fingerprint failed', e);
        }

        return fp;
    }

    async _sendFingerprint(fpData) {
        try {
            const res = await fetch(`${this.endpoint}/fingerprint`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(fpData)
            });
            const data = await res.json();
            console.log(`[EvTrack] Fingerprint sent. Known device: ${data.is_known_device}`);
        } catch (error) {
            console.error('[EvTrack] Failed to send fingerprint:', error);
        }
    }

    async _sha256(message) {
        const msgBuffer = new TextEncoder().encode(message);
        const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    }

    // Server-side CAPI event trigger
    async sendCapiEvent(eventName, payload = {}) {
        const eventId = `evt_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
        
        try {
            await fetch(`${this.endpoint}/event`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    event_id: eventId,
                    event_name: eventName,
                    session_token: this.sessionToken,
                    timestamp: Math.floor(Date.now() / 1000),
                    payload: payload
                })
            });
        } catch (error) {
            console.error('[EvTrack] Failed to send CAPI event:', error);
        }
    }
}

// Export to window for browser usage
window.EvTrack = EvTrack;
