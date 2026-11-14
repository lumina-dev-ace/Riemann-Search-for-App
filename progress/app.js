"use strict";

const REPOSITORY = "lumina-dev-ace/Riemann-Search-for-App";
const MAX_DOCUMENT_BYTES = 16 * 1024 * 1024;
const INDEX_LIMIT = 10n ** 37n;
const ALLOWED_STATUS = new Set(["verified", "certified_interval_rechecked"]);
const validatedRecordCache = new Map();
let currentManifestCommit = null;
let renderInFlight = false;
const el = (id) => document.getElementById(id);

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function parseJsonNoDuplicateKeys(text) {
  let position = 0;
  const whitespace = () => { while (/\s/.test(text[position] || "")) position += 1; };
  const stringToken = () => {
    const start = position++;
    while (position < text.length) {
      if (text[position] === "\\") { position += 2; continue; }
      if (text[position++] === '"') return JSON.parse(text.slice(start, position));
    }
    throw new Error("Malformed JSON string");
  };
  const value = () => {
    whitespace();
    const character = text[position];
    if (character === '"') { stringToken(); return; }
    if (character === "{") {
      position += 1; whitespace();
      const keys = new Set();
      if (text[position] === "}") { position += 1; return; }
      while (position < text.length) {
        whitespace();
        if (text[position] !== '"') throw new Error("Malformed JSON object key");
        const key = stringToken();
        if (keys.has(key)) throw new Error(`Duplicate JSON key: ${key}`);
        keys.add(key); whitespace();
        if (text[position++] !== ":") throw new Error("Malformed JSON object separator");
        value(); whitespace();
        const separator = text[position++];
        if (separator === "}") return;
        if (separator !== ",") throw new Error("Malformed JSON object delimiter");
      }
      throw new Error("Unclosed JSON object");
    }
    if (character === "[") {
      position += 1; whitespace();
      if (text[position] === "]") { position += 1; return; }
      while (position < text.length) {
        value(); whitespace();
        const separator = text[position++];
        if (separator === "]") return;
        if (separator !== ",") throw new Error("Malformed JSON array delimiter");
      }
      throw new Error("Unclosed JSON array");
    }
    const literal = /^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/.exec(text.slice(position));
    if (!literal) throw new Error("Malformed JSON value");
    position += literal[0].length;
  };
  value(); whitespace();
  if (position !== text.length) throw new Error("Unexpected content after JSON document");
  return JSON.parse(text);
}

function validIndex(value, label) {
  if (typeof value !== "string" || !/^(0|[1-9][0-9]*)$/.test(value)) throw new Error(`${label} is not an exact decimal index`);
  const index = BigInt(value);
  if (index <= 0n || index >= INDEX_LIMIT) throw new Error(`${label} is outside the supported FLINT range`);
  return index;
}

async function sha256(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((part) => part.toString(16).padStart(2, "0")).join("");
}

async function checkDocumentIntegrity(document, label) {
  const integrity = document.integrity;
  if (!integrity || integrity.algorithm !== "sha256" || !/^[0-9a-f]{64}$/.test(integrity.sha256 || "")) throw new Error(`${label} has no valid SHA-256 record`);
  const copy = { ...document };
  delete copy.integrity;
  const digest = await sha256(new TextEncoder().encode(canonical(copy)));
  if (digest !== integrity.sha256) throw new Error(`${label} SHA-256 check failed`);
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store", headers: { Accept: "application/json" } });
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  const bytes = await readBoundedBody(response);
  return { bytes, value: parseJsonNoDuplicateKeys(new TextDecoder().decode(bytes)) };
}

async function readBoundedBody(response) {
  const declared = Number(response.headers.get("content-length") || 0);
  if (declared > MAX_DOCUMENT_BYTES) throw new Error("A GitHub data document exceeds the safe 16 MiB download limit");
  if (!response.body || !response.body.getReader) {
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.byteLength > MAX_DOCUMENT_BYTES) throw new Error("A GitHub data document exceeds the safe 16 MiB download limit");
    return bytes;
  }
  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_DOCUMENT_BYTES) {
      await reader.cancel();
      throw new Error("A GitHub data document exceeds the safe 16 MiB download limit");
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return bytes;
}

async function validateRecordFile(reference) {
  const expectedPath = reference.record_path;
  if (typeof expectedPath !== "string" || !/^data\/ranges\/[A-Za-z0-9._-]+\.json$/.test(expectedPath)) throw new Error("A range references an unsafe research-record path");
  const cached = validatedRecordCache.get(reference.sha256);
  if (cached) {
    if (cached.start !== reference.start_index || cached.end !== reference.end_index || cached.status !== reference.verification_status || cached.contributor !== reference.contributor_id) throw new Error(`Cached research-record metadata does not match ${expectedPath}`);
    return;
  }
  const response = await fetch(`https://raw.githubusercontent.com/${REPOSITORY}/${currentManifestCommit}/${expectedPath}`, { cache: "no-store", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`A referenced research record is missing (${expectedPath})`);
  const bytes = await readBoundedBody(response);
  if (await sha256(bytes) !== reference.sha256) throw new Error(`Research record integrity failed (${expectedPath})`);
  const record = parseJsonNoDuplicateKeys(new TextDecoder().decode(bytes));
  await checkDocumentIntegrity(record, "Research record");
  if (record.schema_version !== 1 || record.record_type !== "riemannsearch-zero-range" || !Array.isArray(record.results) || !record.results.length) throw new Error(`Research record schema is invalid (${expectedPath})`);
  const computation = record.computation || {};
  const verification = record.verification || {};
  if ((!String(computation.backend || "").toLowerCase().includes("flint") && !String(computation.backend || "").toLowerCase().includes("arb")) || !computation.backend_version || !computation.algorithm || !Number.isInteger(computation.precision_digits) || computation.precision_digits < 2) throw new Error(`Computation metadata is invalid (${expectedPath})`);
  if (!String(verification.method || "").toLowerCase().includes("arb") || !Number.isInteger(verification.precision_digits) || verification.precision_digits < 2 || !ALLOWED_STATUS.has(verification.status) || typeof verification.interval_verification !== "boolean") throw new Error(`Verification metadata is invalid (${expectedPath})`);
  const first = validIndex(record.start_index, "Record start_index");
  const last = validIndex(record.end_index, "Record end_index");
  let expected = first;
  const statuses = new Set();
  const intervalFlags = [];
  for (const result of record.results) {
    if (validIndex(result.zero_index, "Result zero_index") !== expected) throw new Error(`Results are missing or repeat an index (${expectedPath})`);
    expected += 1n;
    if (!["real_part", "imag_part", "residual", "verification_residual", "computed_at"].every((key) => typeof result[key] === "string" && result[key].length > 0)) throw new Error(`A result is missing computed numerical fields (${expectedPath})`);
    if (!ALLOWED_STATUS.has(result.verification_status) || !String(result.verification_method || "").toLowerCase().includes("arb")) throw new Error(`A result lacks eligible Arb recheck metadata (${expectedPath})`);
    if (!Number.isInteger(result.precision_digits) || result.precision_digits < 2 || !Number.isInteger(result.verification_precision_digits) || result.verification_precision_digits < 2) throw new Error(`A result has invalid precision metadata (${expectedPath})`);
    for (const key of ["computation_time_ms", "verification_time_ms"]) {
      if (result[key] !== null && (typeof result[key] !== "string" || !/^(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?$/.test(result[key]))) throw new Error(`A result has an invalid ${key} (${expectedPath})`);
    }
    if (typeof result.certified_interval !== "boolean") throw new Error(`A result has an invalid interval flag (${expectedPath})`);
    if (result.certified_interval && !(result.real_enclosure && result.imag_enclosure)) throw new Error(`A result claims an interval without its enclosures (${expectedPath})`);
    statuses.add(result.verification_status);
    intervalFlags.push(result.certified_interval);
  }
  if (BigInt(record.results[0].zero_index) !== first || BigInt(record.results.at(-1).zero_index) !== last) throw new Error(`Record endpoints do not match its result list (${expectedPath})`);
  if (last.toString() !== reference.end_index || first.toString() !== reference.start_index) throw new Error(`Manifest endpoints do not match ${expectedPath}`);
  if (record.contributor_id !== reference.contributor_id) throw new Error(`Contributor metadata does not match ${expectedPath}`);
  if (statuses.size !== 1 || !statuses.has(verification.status) || verification.interval_verification !== intervalFlags.every(Boolean)) throw new Error(`Range verification summary does not match its results (${expectedPath})`);
  if (verification.status !== reference.verification_status) throw new Error(`Range verification status does not match ${expectedPath}`);
  validatedRecordCache.set(reference.sha256, {
    start: first.toString(), end: last.toString(), status: verification.status,
    contributor: record.contributor_id,
  });
}

async function fetchLatestManifest() {
  const query = `https://api.github.com/repos/${REPOSITORY}/commits?path=data%2Fglobal_manifest.json&sha=main&per_page=1`;
  const { value: commits } = await fetchJson(query);
  const commit = Array.isArray(commits) && commits[0] && commits[0].sha;
  if (typeof commit !== "string" || !/^[0-9a-f]{40,64}$/.test(commit)) {
    const error = new Error("No published global manifest commit was found in the repository");
    error.status = 404;
    throw error;
  }
  currentManifestCommit = commit;
  const { value: manifest } = await fetchJson(`https://raw.githubusercontent.com/${REPOSITORY}/${commit}/data/global_manifest.json?refresh=${Date.now()}`);
  return { manifest, commit };
}

async function validateManifest(manifest) {
  if (!manifest || manifest.schema_version !== 1 || manifest.network_id !== "riemannsearch-global-research") throw new Error("The global manifest schema or network ID is unsupported");
  if (!new Set(["initialized", "uninitialized"]).has(manifest.status)) throw new Error("The global manifest has an invalid initialization status");
  await checkDocumentIntegrity(manifest, "Global manifest");
  if (!Array.isArray(manifest.accepted_ranges) || !Array.isArray(manifest.publication_history)) throw new Error("The global manifest ranges or history are invalid");
  if (manifest.status === "uninitialized") {
    if (manifest.first_required_index !== null || manifest.global_checkpoint_index !== null || manifest.accepted_ranges.length || manifest.publication_history.length) throw new Error("An uninitialized manifest cannot claim progress");
    return { initialized: false, first: null, checkpoint: null, ranges: [] };
  }
  const first = validIndex(manifest.first_required_index, "first_required_index");
  let next = first;
  const paths = new Set();
  for (const range of manifest.accepted_ranges) {
    const start = validIndex(range.start_index, "Range start_index");
    const end = validIndex(range.end_index, "Range end_index");
    if (start !== next || end < start || paths.has(range.record_path) || !/^[0-9a-f]{64}$/.test(range.sha256 || "") || !ALLOWED_STATUS.has(range.verification_status)) throw new Error("Accepted global coverage contains a gap, overlap, duplicate, or invalid hash");
    paths.add(range.record_path);
    await validateRecordFile(range);
    next = end + 1n;
  }
  const checkpoint = manifest.accepted_ranges.length ? (next - 1n).toString() : null;
  if (manifest.global_checkpoint_index !== checkpoint) throw new Error("Global checkpoint does not equal the final consecutive published result");
  if (manifest.accepted_ranges.length && manifest.publication_history.length < manifest.accepted_ranges.length) throw new Error("Publication history is incomplete");
  return { initialized: true, first, checkpoint, ranges: manifest.accepted_ranges, next };
}

function groupExactIndex(value) {
  return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function setStatus(text, kind) {
  const status = el("network-status");
  status.textContent = text;
  status.className = `status status-${kind}`;
}

function renderWaiting(message, details, failed = false) {
  const checkpoint = el("checkpoint");
  checkpoint.textContent = message;
  checkpoint.className = `checkpoint ${failed ? "error" : "waiting"}`;
  el("checkpoint-explanation").textContent = details;
  el("range-count").textContent = "—";
  el("verified-count").textContent = "—";
  el("contributor-count").textContent = "—";
  el("last-updated").textContent = "Last published update: —";
  el("history-list").replaceChildren();
  el("history-empty").hidden = false;
}

function renderHistory(ranges) {
  const list = el("history-list");
  list.replaceChildren();
  const recent = [...ranges].reverse().slice(0, 8);
  el("history-empty").hidden = recent.length > 0;
  for (const range of recent) {
    const item = document.createElement("li");
    const text = document.createElement("strong");
    text.textContent = `${groupExactIndex(range.start_index)} – ${groupExactIndex(range.end_index)}`;
    const date = document.createElement("small");
    date.textContent = `${range.contributor_id} · ${range.verification_status.replaceAll("_", " ")}`;
    item.append(text, date);
    list.append(item);
  }
}

async function render() {
  if (renderInFlight) return;
  renderInFlight = true;
  try {
    const { manifest, commit } = await fetchLatestManifest();
    const state = await validateManifest(manifest);
    el("range-count").textContent = String(state.ranges.length);
    el("verified-count").textContent = String(state.ranges.filter((range) => ALLOWED_STATUS.has(range.verification_status)).length);
    el("contributor-count").textContent = String(new Set(state.ranges.map((range) => range.contributor_id)).size);
    el("last-updated").textContent = `Last published update: ${manifest.last_updated_at ? new Date(manifest.last_updated_at).toLocaleString() : "No range published yet"}`;
    renderHistory(state.ranges);
    if (!state.initialized) {
      renderWaiting("Research network awaiting initialization.", "No starting index or completed range has been published.");
      setStatus("Awaiting initialization", "waiting");
      return;
    }
    if (state.ranges.length === 0) {
      renderWaiting("No accepted research ranges yet.", `Network initialized. First required zero index: ${groupExactIndex(manifest.first_required_index)}. This boundary is not a computed result.`);
      el("range-count").textContent = "0";
      el("verified-count").textContent = "0";
      el("contributor-count").textContent = "0";
      el("last-updated").textContent = "Last published update: Network initialization only";
      setStatus("Initialized · awaiting first range", "waiting");
    } else {
      const checkpoint = el("checkpoint");
      checkpoint.textContent = groupExactIndex(state.checkpoint);
      checkpoint.className = "checkpoint";
      el("checkpoint-explanation").textContent = `Highest consecutively accepted zero index, beginning at ${groupExactIndex(manifest.first_required_index)}. Every referenced range and result index passed the published integrity and Arb-metadata checks.`;
      setStatus("Manifest and records validated", "live");
    }
    const source = el("source-commit");
    const link = document.createElement("a");
    link.href = `https://github.com/${REPOSITORY}/commit/${commit}`;
    link.rel = "noreferrer";
    link.textContent = `Manifest commit: ${commit.slice(0, 12)}`;
    source.replaceChildren(link);
  } catch (error) {
    if (error.status === 404) {
      renderWaiting("Research network awaiting initialization.", "The repository has no published global manifest yet.");
      setStatus("No manifest published", "waiting");
    } else {
      renderWaiting("Current research data is unavailable.", `No checkpoint is shown because current data could not be validated: ${error.message}`, true);
      setStatus("Validation or retrieval failed", "error");
    }
    el("source-commit").textContent = "Manifest: not verified";
  } finally {
    renderInFlight = false;
  }
}

render();
setInterval(() => { if (!document.hidden) render(); }, 5 * 60 * 1000);
