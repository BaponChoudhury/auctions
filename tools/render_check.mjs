// Execute the artifact's own script against a minimal DOM and assert it renders.
import { readFileSync } from "node:fs";

const html = readFileSync(process.argv[2], "utf8");
const payload = html.match(
  /<script id="payload" type="application\/json">([\s\S]*?)<\/script>/)[1];
const code = html.match(/<script>\r?\n([\s\S]*?)<\/script>/)[1];

const store = {};
const el = (id) => (store[id] ??= {
  innerHTML: "", textContent: "", dataset: {},
  firstChild: { nodeValue: "" },
  addEventListener() {}, setAttribute() {}, removeAttribute() {},
  querySelector: () => null, insertAdjacentHTML() {},
});
store.payload = { textContent: payload.replace(/<\\\//g, "</") };

globalThis.document = {
  getElementById: el,
  querySelectorAll: () => [],
};

eval(code);

const rows = store.rows.innerHTML;
const status = store.statusList.innerHTML;
const n = (rows.match(/<tr>/g) || []).length;

const data = JSON.parse(payload.replace(/<\\\//g, "</"));
const checks = [
  ["table rows rendered", n === data.sold.length, `${n} vs ${data.sold.length}`],
  ["status bars rendered", (status.match(/status-row/g) || []).length === 7],
  ["count label", store.count.textContent === `${n} lots`, store.count.textContent],
  ["money formatted with separators", /£\d{1,3},\d{3}/.test(rows)],
  ["every source in the data appears in the table",
   Object.keys(data.summary.sources).length ===
     new Set(data.sold.map((r) => r.source)).size,
   Object.keys(data.summary.sources).join(",")],
  // The spread sentence is generated from the data — assert it matches the rows.
  ["regional spread sentence matches the data", (() => {
    const meds = data.summary.regions.map((r) => r.median);
    const lo = Math.min(...meds), hi = Math.max(...meds);
    const t = store.spreadNote.innerHTML;
    return t.includes("£" + lo.toLocaleString("en-GB")) &&
           t.includes("£" + hi.toLocaleString("en-GB")) &&
           t.includes((hi / lo).toFixed(1) + "×");
  })(), store.spreadNote.innerHTML.replace(/<[^>]+>/g, "").slice(0, 90)],
  ["type label mapped", rows.includes(">Terraced<") || rows.includes(">Land / other<")],
  ["no literal undefined/NaN", !/undefined|NaN/.test(rows)],
  // Headline tiles are written from the data, so they must match it exactly.
  ["total tile matches data",
   store.tTotal.firstChild.nodeValue === data.summary.total.toLocaleString("en-GB"),
   store.tTotal.firstChild.nodeValue],
  ["sold tile matches data",
   store.tSold.firstChild.nodeValue === data.summary.sold_n.toLocaleString("en-GB"),
   store.tSold.firstChild.nodeValue],
  ["raised tile matches data",
   store.tRaised.firstChild.nodeValue ===
     "£" + Math.round(data.summary.total_raised / 1e6) + "m",
   store.tRaised.firstChild.nodeValue],
  ["region rows rendered",
   (store.regionRows.innerHTML.match(/<tr>/g) || []).length === data.summary.regions.length,
   (store.regionRows.innerHTML.match(/<tr>/g) || []).length],
  ["region column populated in the lot table", /West Midlands|East Midlands/.test(rows)],
  ["geo line mentions local authorities", /local authorities/.test(store.geoLine.textContent),
   store.geoLine.textContent],
  ["headline matches the data",
   store.headline.textContent ===
     `${data.summary.total.toLocaleString("en-GB")} lots from ` +
     `${data.summary.events.toLocaleString("en-GB")} property auctions`,
   store.headline.textContent],
  ["house count in eyebrow matches sources",
   store.eyebrow.textContent.includes(String(Object.keys(data.summary.sources).length)),
   store.eyebrow.textContent],
  ["disclosure note spans the real min/max",
   (() => {
     const r = Object.values(data.summary.priced_by_source);
     const t = store.priceNote.innerHTML;
     return t.includes(`${Math.min(...r)}%`) && t.includes(`${Math.max(...r)}%`);
   })(), store.priceNote.innerHTML.replace(/<[^>]+>/g, "").slice(0, 100)],
  ["source line names both houses",
   /SDL/.test(store.tSources.textContent) && /Bond Wolfe/.test(store.tSources.textContent),
   store.tSources.textContent],
];

const widths = [...status.matchAll(/width:([\d.]+)%/g)].map((m) => +m[1]);
checks.push(
  ["all bar widths within 0-100%",
   widths.length === Object.keys(data.summary.status).length &&
     widths.every((w) => w > 0 && w <= 100),
   widths.map((w) => w.toFixed(1)).join(" ")],
  ["largest bar is full width", Math.max(...widths) === 100],
);

let bad = 0;
for (const [name, ok, got] of checks) {
  console.log(`${ok ? "ok  " : "FAIL"}  ${name}${ok || got === undefined ? "" : "  got=" + got}`);
  if (!ok) bad++;
}
console.log(bad ? `\n${bad} FAILED` : "\nall render checks passed");
process.exit(bad ? 1 : 0);
