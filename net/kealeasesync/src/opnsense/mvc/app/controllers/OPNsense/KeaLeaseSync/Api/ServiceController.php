<?php

/*
 * Copyright (C) 2024 kim@c0de.ch
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

namespace OPNsense\KeaLeaseSync\Api;

use OPNsense\Base\ApiControllerBase;
use OPNsense\Core\Backend;

class ServiceController extends ApiControllerBase
{
    /**
     * Run sync now
     */
    public function syncAction()
    {
        if ($this->request->isPost()) {
            $backend = new Backend();
            $response = trim($backend->configdRun('kealeasesync run'));
            return array('status' => 'ok', 'response' => $response);
        }
        return array('status' => 'failed', 'message' => 'POST required');
    }

    /**
     * Apply settings (regenerate template + run sync)
     */
    public function applyAction()
    {
        if ($this->request->isPost()) {
            $backend = new Backend();
            $backend->configdRun('template reload OPNsense/KeaLeaseSync');
            $response = trim($backend->configdRun('kealeasesync run'));
            return array('status' => 'ok', 'response' => $response);
        }
        return array('status' => 'failed', 'message' => 'POST required');
    }

    /**
     * Get sync status
     */
    public function statusAction()
    {
        $backend = new Backend();
        $response = $backend->configdRun('kealeasesync status');
        $data = json_decode(trim($response), true);
        if ($data === null) {
            return array('status' => 'unknown', 'message' => 'No status available');
        }
        return $data;
    }

    /**
     * Get synced hosts
     */
    public function hostsAction()
    {
        $backend = new Backend();
        $response = $backend->configdRun('kealeasesync hosts');
        $data = json_decode(trim($response), true);
        if ($data === null) {
            return array('hosts' => array());
        }
        return $data;
    }

    /**
     * Get recent log entries
     */
    public function logAction()
    {
        $backend = new Backend();
        $response = $backend->configdRun('kealeasesync log');
        return array('log' => trim($response));
    }
}
