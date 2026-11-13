const byId = (id) => document.getElementById(id);
const fmtCount = (value) => Number(value || 0).toLocaleString("en-US");
const fmtIndex = (value) => {
  if (value === null || value === undefined) return "—";
  try { return BigInt(String(value)).toLocaleString("en-US"); }
  catch { return String(value); }
};
const fmtDate = (value) => {
  if (!value) return "Not initialized";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unknown" : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }) + " UTC";
};
const safeText = (element, value) => { element.textContent = value; };

async function loadDashboard() {
  try {
    const response = await fetch("data/index.json", { cache: "no-store" });
    if (!response.ok) throw new Error("Dashboard data is unavailable");
    const data = await response.json();
    const checkpoint = data.checkpoint || {};
    const initialized = checkpoint.status === "initialized";

    safeText(byId("network-status"), initialized ? "Checkpoint initialized · data loaded" : "Research network awaiting initialization");
    byId("status-dot").classList.toggle("ready", initialized);
    safeText(byId("checkpoint-value"), initialized ? fmtIndex(checkpoint.highest_verified_index) : "Awaiting first verified sequence");
    safeText(byId("checkpoint-note"), initialized
      ? "All indices up to this point are represented in the accepted verified sequence."
      : "No starting index has been assumed. The first checkpoint will be set only after real contiguous records are reviewed.");
    safeText(byId("updated-at"), fmtDate(checkpoint.updated_utc));
    safeText(byId("record-count"), fmtCount(data.record_count));
    safeText(byId("entry-count"), fmtCount(data.entry_count));
    safeText(byId("verified-count"), fmtCount(data.arb_verified_entry_count));
    safeText(byId("contributor-count"), fmtCount(data.contributor_count));

    const list = byId("records-list");
    list.replaceChildren();
    if (!Array.isArray(data.recent_records) || data.recent_records.length === 0) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "No research records have been published yet.";
      list.append(empty);
      return;
    }
    for (const record of data.recent_records) {
      const row = document.createElement("article");
      row.className = "record-row";
      const left = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = record.record_id;
      const meta = document.createElement("div");
      meta.className = "record-meta";
      meta.textContent = (record.contributor || "Contributor") + " · " + fmtDate(record.created_utc);
      left.append(title, meta);
      const right = document.createElement("div");
      right.className = "record-range";
      right.textContent = "#" + fmtIndex(record.start_index) + "–#" + fmtIndex(record.end_index) + " · " + fmtCount(record.verified_count) + " verified";
      row.append(left, right);
      list.append(row);
    }
  } catch (error) {
    safeText(byId("network-status"), "Dashboard data could not be loaded");
    safeText(byId("checkpoint-note"), error.message || "Check the repository data and try again.");
    byId("status-dot").classList.remove("ready");
  }
}

loadDashboard();
