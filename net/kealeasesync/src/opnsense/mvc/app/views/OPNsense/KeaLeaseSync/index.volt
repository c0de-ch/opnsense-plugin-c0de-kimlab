{#
 # Copyright (C) 2024 kim@kimlab.ch
 # All rights reserved.
 #}

<script>
    $(document).ready(function () {
        var data_get_map = {'frm_GeneralSettings': '/api/kealeasesync/settings/get'};
        mapDataToFormUI(data_get_map).done(function () {
            formatTokenizersUI();
            $('.selectpicker').selectpicker('refresh');
        });

        updateServiceControlUI('kealeasesync');

        // Save settings
        $("#saveAct").click(function () {
            saveFormToEndpoint('/api/kealeasesync/settings/set', 'frm_GeneralSettings', function () {
                $("#saveAct_progress").addClass("fa fa-spinner fa-pulse");
                ajaxCall('/api/kealeasesync/service/apply', {}, function (data, status) {
                    $("#saveAct_progress").removeClass("fa fa-spinner fa-pulse");
                    updateServiceControlUI('kealeasesync');
                    loadStatus();
                });
            });
        });

        // Sync now
        $("#syncNow").click(function () {
            $("#syncNow_progress").addClass("fa fa-spinner fa-pulse");
            ajaxCall('/api/kealeasesync/service/sync', {}, function (data, status) {
                $("#syncNow_progress").removeClass("fa fa-spinner fa-pulse");
                loadStatus();
                loadHosts();
            });
        });

        // Tab handlers
        $('a[data-toggle="tab"]').on('shown.bs.tab', function (e) {
            var target = $(e.target).attr("href");
            if (target === '#status') {
                loadStatus();
                loadHosts();
            } else if (target === '#log') {
                loadLog();
            }
        });

        function loadStatus() {
            ajaxGet('/api/kealeasesync/service/status', {}, function (data, status) {
                if (data.status === 'unknown') {
                    $("#sync_status").html('<div class="alert alert-info">No sync has been run yet.</div>');
                    return;
                }
                var html = '<table class="table table-condensed">';
                html += '<tr><td><strong>Last Sync</strong></td><td>' + (data.last_sync || 'Never') + '</td></tr>';
                html += '<tr><td><strong>Hosts Registered</strong></td><td>' + (data.hosts_registered || 0) + '</td></tr>';
                html += '<tr><td><strong>Hosts Removed</strong></td><td>' + (data.hosts_removed || 0) + '</td></tr>';
                html += '<tr><td><strong>Static Reservations</strong></td><td>' + (data.static_count || 0) + '</td></tr>';
                html += '<tr><td><strong>Dynamic Leases</strong></td><td>' + (data.dynamic_count || 0) + '</td></tr>';
                html += '<tr><td><strong>Duration</strong></td><td>' + (data.duration || '-') + '</td></tr>';
                html += '</table>';
                $("#sync_status").html(html);
            });
        }

        function loadHosts() {
            ajaxGet('/api/kealeasesync/service/hosts', {}, function (data, status) {
                if (!data.hosts || data.hosts.length === 0) {
                    $("#hosts_table").html('<div class="alert alert-info">No hosts synced yet.</div>');
                    return;
                }
                var html = '<table class="table table-striped table-condensed">';
                html += '<thead><tr><th>Hostname</th><th>IP Address</th><th>Type</th><th>Status</th></tr></thead>';
                html += '<tbody>';
                $.each(data.hosts, function (i, host) {
                    var typeBadge = host.type === 'static'
                        ? '<span class="label label-info">static</span>'
                        : '<span class="label label-default">dynamic</span>';
                    var statusIcon = host.online
                        ? '<i class="fa fa-circle text-success"></i> online'
                        : '<i class="fa fa-circle text-danger"></i> offline';
                    html += '<tr>';
                    html += '<td>' + $('<span>').text(host.hostname).html() + '</td>';
                    html += '<td>' + $('<span>').text(host.ip).html() + '</td>';
                    html += '<td>' + typeBadge + '</td>';
                    html += '<td>' + statusIcon + '</td>';
                    html += '</tr>';
                });
                html += '</tbody></table>';
                $("#hosts_table").html(html);
            });
        }

        function loadLog() {
            ajaxGet('/api/kealeasesync/service/log', {}, function (data, status) {
                if (!data.log) {
                    $("#log_content").text('No log entries found.');
                    return;
                }
                $("#log_content").text(data.log);
            });
        }
    });
</script>

<ul class="nav nav-tabs" data-tabs="tabs" id="maintabs">
    <li class="active"><a data-toggle="tab" href="#settings">{{ lang._('Settings') }}</a></li>
    <li><a data-toggle="tab" href="#status">{{ lang._('Status') }}</a></li>
    <li><a data-toggle="tab" href="#log">{{ lang._('Log') }}</a></li>
</ul>

<div class="tab-content content-box">
    <!-- Settings Tab -->
    <div id="settings" class="tab-pane fade in active">
        <div class="content-box" style="padding-bottom: 1.5em;">
            {{ partial("layout_partials/base_form", ['fields': generalForm, 'id': 'frm_GeneralSettings']) }}
            <div class="col-md-12">
                <hr />
                <button class="btn btn-primary" id="saveAct" type="button">
                    <b>{{ lang._('Save') }}</b> <i id="saveAct_progress"></i>
                </button>
                <button class="btn btn-default" id="syncNow" type="button">
                    <b>{{ lang._('Sync Now') }}</b> <i id="syncNow_progress"></i>
                </button>
            </div>
        </div>
    </div>

    <!-- Status Tab -->
    <div id="status" class="tab-pane fade">
        <div class="content-box" style="padding-bottom: 1.5em;">
            <div class="col-md-12">
                <h3>{{ lang._('Sync Status') }}</h3>
                <div id="sync_status">
                    <div class="alert alert-info">{{ lang._('Click the Status tab to load current status.') }}</div>
                </div>
                <hr />
                <h3>{{ lang._('Synced Hosts') }}</h3>
                <div id="hosts_table">
                    <div class="alert alert-info">{{ lang._('Click the Status tab to load hosts.') }}</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Log Tab -->
    <div id="log" class="tab-pane fade">
        <div class="content-box" style="padding-bottom: 1.5em;">
            <div class="col-md-12">
                <h3>{{ lang._('Recent Log Entries') }}</h3>
                <pre id="log_content" style="max-height: 500px; overflow-y: auto;">{{ lang._('Click the Log tab to load entries.') }}</pre>
            </div>
        </div>
    </div>
</div>
