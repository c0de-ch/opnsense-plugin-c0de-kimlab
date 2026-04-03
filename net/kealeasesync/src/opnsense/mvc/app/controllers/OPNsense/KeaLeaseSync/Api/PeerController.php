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
use OPNsense\KeaLeaseSync\KeaLeaseSync;

/**
 * Peer-facing API controller — authenticates via shared API key (X-API-Key header)
 * instead of OPNsense user credentials.
 */
class PeerController extends ApiControllerBase
{
    /**
     * Validate shared API key instead of standard OPNsense auth
     */
    public function beforeExecuteRoute($dispatcher)
    {
        $this->response->setContentType('application/json', 'UTF-8');

        $apiKey = $this->request->getHeader('X-API-Key');

        $model = new KeaLeaseSync();
        $configuredKey = (string)$model->general->peerApiKey;

        if (empty($apiKey) || empty($configuredKey) || !hash_equals($configuredKey, $apiKey)) {
            $this->response->setStatusCode(403);
            $this->response->setJsonContent(['status' => 'error', 'message' => 'Invalid API key']);
            $this->response->send();
            return false;
        }
    }

    /**
     * Return hosts for peer sync
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
}
