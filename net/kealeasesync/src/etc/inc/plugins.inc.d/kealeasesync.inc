<?php

/*
 * Copyright (C) 2024 kim@kimlab.ch
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
 * AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 * AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
 * OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 */

function kealeasesync_services()
{
    $services = array();

    $mdl = new \OPNsense\KeaLeaseSync\KeaLeaseSync();
    $services[] = array(
        'description' => gettext('Kea Lease DNS Sync'),
        'configd' => array(
            'restart' => array('kealeasesync run'),
        ),
        'name' => 'kealeasesync',
        'nocheck' => true,
    );

    return $services;
}

function kealeasesync_cron()
{
    $jobs = [];

    $mdl = new \OPNsense\KeaLeaseSync\KeaLeaseSync();
    if ((string)$mdl->general->enabled == '1') {
        $interval = str_replace('i', '', (string)$mdl->general->scanInterval);
        if (empty($interval) || $interval == '0') {
            $interval = '1';
        }
        $minutes = $interval == '1' ? '*' : '*/' . $interval;
        $jobs[]['autocron'] = ['/usr/local/sbin/configctl kealeasesync run', $minutes];
    }

    return $jobs;
}

function kealeasesync_configure()
{
    return array(
        'bootup' => array('kealeasesync_configure_do'),
    );
}

function kealeasesync_configure_do($verbose = false)
{
    $mdl = new \OPNsense\KeaLeaseSync\KeaLeaseSync();
    if ((string)$mdl->general->enabled == '1') {
        if ($verbose) {
            echo 'Configuring Kea Lease Sync...';
        }
        configd_run('template reload OPNsense/KeaLeaseSync');
        if ($verbose) {
            echo "done.\n";
        }
    }
}
