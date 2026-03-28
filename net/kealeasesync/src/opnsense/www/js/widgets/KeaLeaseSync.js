/**
 * Kea Lease Sync — Dashboard Widget
 * Table view + SVG radial network map
 */

import BaseTableWidget from "./BaseTableWidget.js";

export default class KeaLeaseSync extends BaseTableWidget {
    constructor() {
        super();
        this.resizeHandles = "e, w";
        this.currentView = 'table';
        this.hostLimit = 20;
        this.refreshInterval = 10000;
        this.statusData = null;
        this.hostsData = [];
    }

    getMarkup() {
        return `
            <div id="kealeasesync-widget">
                <div class="kls-toolbar" style="padding: 5px 10px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #ddd;">
                    <div>
                        <button class="btn btn-xs btn-default kls-view-btn" data-view="table" title="Table view">
                            <i class="fa fa-table"></i>
                        </button>
                        <button class="btn btn-xs btn-default kls-view-btn" data-view="map" title="Network map">
                            <i class="fa fa-sitemap"></i>
                        </button>
                    </div>
                    <div>
                        <select class="kls-limit" style="font-size: 11px; padding: 1px 4px;">
                            <option value="5">5</option>
                            <option value="10">10</option>
                            <option value="20" selected>20</option>
                            <option value="50">50</option>
                            <option value="0">All</option>
                        </select>
                    </div>
                    <div class="kls-status-badge" style="font-size: 11px; color: #888;"></div>
                </div>
                <div class="kls-content" style="min-height: 100px;"></div>
            </div>`;
    }

    async onWidgetReady() {
        const widget = document.getElementById('kealeasesync-widget');
        if (!widget) return;

        // View toggle
        widget.querySelectorAll('.kls-view-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.currentView = btn.dataset.view;
                widget.querySelectorAll('.kls-view-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.render();
            });
        });

        // Host limit
        widget.querySelector('.kls-limit').addEventListener('change', (e) => {
            this.hostLimit = parseInt(e.target.value, 10);
            this.render();
        });

        // Set initial active button
        widget.querySelector('[data-view="table"]').classList.add('active');

        await this.fetchData();
    }

    async onWidgetTick() {
        await this.fetchData();
    }

    async fetchData() {
        try {
            const [statusResp, hostsResp] = await Promise.all([
                $.ajax({ url: '/api/kealeasesync/service/status', type: 'GET' }),
                $.ajax({ url: '/api/kealeasesync/service/hosts', type: 'GET' })
            ]);
            this.statusData = statusResp;
            this.hostsData = hostsResp.hosts || [];
            this.render();
        } catch (e) {
            this.displayError();
        }
    }

    render() {
        const widget = document.getElementById('kealeasesync-widget');
        if (!widget) return;

        // Update status badge
        const badge = widget.querySelector('.kls-status-badge');
        if (this.statusData && this.statusData.last_sync) {
            badge.textContent = this.statusData.hosts_registered + ' hosts \u00b7 ' + this.statusData.last_sync;
        } else {
            badge.textContent = 'No sync data';
        }

        const content = widget.querySelector('.kls-content');
        if (this.currentView === 'table') {
            this.renderTable(content);
        } else {
            this.renderMap(content);
        }
    }

    renderTable(container) {
        let hosts = this.hostsData.filter(h => h.rtype === 'A');
        if (this.hostLimit > 0) {
            hosts = hosts.slice(0, this.hostLimit);
        }

        if (hosts.length === 0) {
            container.innerHTML = '<div style="padding: 20px; text-align: center; color: #888;">No hosts synced</div>';
            return;
        }

        let html = '<table class="table table-condensed table-striped" style="margin: 0;">';
        html += '<thead><tr><th>Hostname</th><th>IP</th><th>Type</th><th>Status</th></tr></thead><tbody>';

        hosts.forEach(host => {
            const name = this.escapeHtml(host.hostname);
            const ip = this.escapeHtml(host.ip);
            const typeBadge = host.type === 'static'
                ? '<span class="label label-info" style="font-size: 10px;">static</span>'
                : '<span class="label label-default" style="font-size: 10px;">dynamic</span>';
            const statusDot = host.online
                ? '<i class="fa fa-circle text-success" style="font-size: 8px;"></i>'
                : '<i class="fa fa-circle text-muted" style="font-size: 8px;"></i>';

            html += `<tr><td>${name}</td><td style="font-family: monospace; font-size: 11px;">${ip}</td><td>${typeBadge}</td><td>${statusDot}</td></tr>`;
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    }

    renderMap(container) {
        let hosts = this.hostsData.filter(h => h.rtype === 'A');
        if (this.hostLimit > 0) {
            hosts = hosts.slice(0, this.hostLimit);
        }

        if (hosts.length === 0) {
            container.innerHTML = '<div style="padding: 20px; text-align: center; color: #888;">No hosts to map</div>';
            return;
        }

        const width = container.clientWidth || 400;
        const height = Math.max(300, Math.min(width, 500));
        const cx = width / 2;
        const cy = height / 2;

        // Separate static (inner ring) and dynamic (outer ring)
        const staticHosts = hosts.filter(h => h.type === 'static');
        const dynamicHosts = hosts.filter(h => h.type === 'dynamic');

        const innerRadius = Math.min(width, height) * 0.25;
        const outerRadius = Math.min(width, height) * 0.4;

        let svg = `<svg width="${width}" height="${height}" xmlns="http://www.w3.org/2000/svg" style="display: block;">`;

        // Background circles (rings)
        svg += `<circle cx="${cx}" cy="${cy}" r="${innerRadius}" fill="none" stroke="#e0e0e0" stroke-width="1" stroke-dasharray="4,4"/>`;
        svg += `<circle cx="${cx}" cy="${cy}" r="${outerRadius}" fill="none" stroke="#e0e0e0" stroke-width="1" stroke-dasharray="4,4"/>`;

        // Gateway center
        svg += `<circle cx="${cx}" cy="${cy}" r="16" fill="#337ab7" stroke="#fff" stroke-width="2"/>`;
        svg += `<text x="${cx}" y="${cy + 4}" text-anchor="middle" fill="#fff" font-size="10" font-weight="bold">GW</text>`;

        // Draw hosts on rings
        const drawHostsOnRing = (hostList, radius, baseColor) => {
            const count = hostList.length;
            if (count === 0) return;
            const angleStep = (2 * Math.PI) / count;

            hostList.forEach((host, i) => {
                const angle = angleStep * i - Math.PI / 2;
                const x = cx + radius * Math.cos(angle);
                const y = cy + radius * Math.sin(angle);
                const color = host.online ? baseColor : '#ccc';
                const nodeRadius = 8;

                // Line to gateway
                svg += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="#e0e0e0" stroke-width="1"/>`;

                // Node circle
                svg += `<circle cx="${x}" cy="${y}" r="${nodeRadius}" fill="${color}" stroke="#fff" stroke-width="1.5">`;
                svg += `<title>${this.escapeHtml(host.hostname)} (${this.escapeHtml(host.ip)})${host.online ? ' - online' : ''}</title>`;
                svg += `</circle>`;

                // Label
                const labelY = y + nodeRadius + 12;
                const name = host.hostname.length > 10 ? host.hostname.substring(0, 9) + '\u2026' : host.hostname;
                svg += `<text x="${x}" y="${labelY}" text-anchor="middle" fill="#555" font-size="9">${this.escapeHtml(name)}</text>`;
            });
        };

        drawHostsOnRing(staticHosts, innerRadius, '#5cb85c');
        drawHostsOnRing(dynamicHosts, outerRadius, '#f0ad4e');

        // Legend
        const ly = height - 15;
        svg += `<circle cx="15" cy="${ly}" r="5" fill="#5cb85c"/><text x="25" y="${ly + 3}" font-size="10" fill="#555">Static</text>`;
        svg += `<circle cx="75" cy="${ly}" r="5" fill="#f0ad4e"/><text x="85" y="${ly + 3}" font-size="10" fill="#555">Dynamic</text>`;
        svg += `<circle cx="145" cy="${ly}" r="5" fill="#ccc"/><text x="155" y="${ly + 3}" font-size="10" fill="#555">Offline</text>`;

        svg += '</svg>';
        container.innerHTML = svg;
    }

    displayError() {
        const widget = document.getElementById('kealeasesync-widget');
        if (!widget) return;
        widget.querySelector('.kls-content').innerHTML =
            '<div style="padding: 20px; text-align: center; color: #d9534f;">Failed to load data</div>';
    }

    escapeHtml(str) {
        const div = document.createElement('div');
        div.appendChild(document.createTextNode(str || ''));
        return div.innerHTML;
    }
}
