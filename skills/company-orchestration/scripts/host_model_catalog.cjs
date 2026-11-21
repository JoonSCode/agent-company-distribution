'use strict';
// Metadata only. Installed Orca internal API, deliberately version bounded.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = '/Applications/Orca.app/Contents/Resources/app.asar.unpacked/out';
const reviewedVersions = ['1.4.245', '1.4.261', '1.4.263', '1.4.268'];
const coherentCatalog = 'agent-session.coherent-model-catalog.v1';
const modelEfforts = 'agent-session.model-catalog.model-efforts.v1';
const savedOnlyCatalog = 'agent-session.model-catalog.saved-only.v1';

// Function-only seams: no CLI/env/module-path injection, no host load on import.
function transport(call, save, now, receipts) {
  return async function(method, params, file) {
    const started_at = now();
    const response = await call(method, params, {timeoutMs: 90000});
    receipts.push({method, params, started_at, received_at: now(), ...save(file, response)});
    return response;
  };
}

async function status(call) {
  const value = await call('status.get', {}, 'status.json');
  const {appVersion, runtimeId, capabilities} = value.result ?? {};
  if (value.ok !== true || !reviewedVersions.includes(appVersion) ||
      typeof runtimeId !== 'string' || !runtimeId || runtimeId !== value._meta?.runtimeId ||
      !Array.isArray(capabilities) || !capabilities.includes(coherentCatalog) ||
      (appVersion === '1.4.268' &&
        [modelEfforts, savedOnlyCatalog].some(capability => !capabilities.includes(capability)))) {
    throw new Error('Unreviewed host version or missing coherent catalog capability');
  }
  return value;
}

async function catalog(call, parseParams, worktree, hostStatus) {
  // 1.4.268 can return partial progress even with waitForListing. A saved-only
  // read avoids starting a listing and can expose a settled workspace observation.
  const savedOnly = hostStatus.result.appVersion === '1.4.268';
  const params = parseParams({agent: 'codex', worktree, ...(savedOnly ? {savedOnly: true} : {})});
  async function read(request, file) {
    const response = await call('agentSession.modelCatalog', request, file);
    if (response.ok !== true || response._meta?.runtimeId !== hostStatus._meta.runtimeId) {
      throw new Error('Catalog unsuccessful or runtime changed');
    }
    return response;
  }
  const response = await read(params, 'response-1.json');
  if (!savedOnly && response.result?.listingInProgress === true) {
    return read(parseParams({...params, waitForListing: true}), 'response-2.json');
  }
  return response;
}

async function collect({worktree, call, parseParams, save, now, receipts = []}) {
  const invoke = transport(call, save, now, receipts);
  const hostStatus = await status(invoke);
  await catalog(invoke, parseParams, worktree, hostStatus);
  // Complete parsed RuntimeClient envelopes, not a raw socket capture or proof
  // of provider pagination completeness. The Python validator remains separate.
  return {format: 'company-host-catalog-metadata/v1',
    runtime_id: hostStatus._meta.runtimeId, app_version: hostStatus.result.appVersion,
    worktree, receipts};
}

function runCLI(directory, worktree) {
  if (!directory || !worktree || !/^id:[^:]+::\/.+/.test(worktree)) {
    throw new Error('Expected unused output directory and exact host-listed id:<repo>::<path>');
  }
  fs.mkdirSync(directory, {mode: 0o700}); // Exclusive; failed attempts are never overwritten.
  const receipts = [];
  function save(name, value) {
    const bytes = Buffer.from(JSON.stringify(value, null, 2) + '\n');
    fs.writeFileSync(path.join(directory, name), bytes, {flag: 'wx', mode: 0o600});
    return {file: name, sha256: crypto.createHash('sha256').update(bytes).digest('hex')};
  }
  async function main() {
    const currentLayout = fs.existsSync(root + '/cli/runtime/client.js');
    const {RuntimeClient} = require(root + (currentLayout ? '/cli/runtime/client.js' : '/cli/runtime-client.js'));
    const {ModelCatalogParams} = require(root + (currentLayout
      ? '/shared/rpc-contract/structured-agent-session/structured-agent-session-params.js'
      : '/shared/rpc-contract/structured-agent-session-params.js'));
    const client = new RuntimeClient(undefined, 90000, null, null);
    const manifest = await collect({worktree, receipts, save,
      now: () => new Date().toISOString(),
      call: (method, params, options) => client.call(method, params, options),
      parseParams: value => ModelCatalogParams.parse(value)});
    save('manifest.json', manifest);
  }
  return main().catch(error => {
    save('failure.json', {message: String(error.message), code: error.code ?? null,
      ...(error.response === undefined ? {} : {response: error.response}), receipts});
    console.error('Catalog metadata collection failed; inspect private failure.json');
    process.exitCode = 1;
  });
}

module.exports = {transport, status, catalog, collect, runCLI};
if (require.main === module) runCLI(...process.argv.slice(2));
