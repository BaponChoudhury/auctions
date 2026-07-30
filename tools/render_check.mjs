// Execute the artifact's own script against a minimal DOM and assert it renders.
import { readFileSync } from "node:fs";

const html = readFileSync(process.argv[2], "utf8");
const payload = html.match(
  /<script id="payload" type="application\/json">([\s\S]*?)<\/script>/)[1];
const code = html.match(/<script>\r?\n([\s\S]*?)<\/script>/)[1];

const store = {};
const el = (id) => (store[id] ??= {
  innerHTML: "", textContent: "", dataset: {},
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

const checks = [
  ["table rows rendered", n === 55, n],
  ["status bars rendered", (status.match(/status-row/g) || []).length === 6],
  ["count label", store.count.textContent === "55 lots", store.count.textContent],
  ["money formatted with separators", rows.includes("£575,000")],
  ["uplift pill signed", rows.includes(">+156%<")],
  ["postcode stripped from address", rows.includes("Development Site at Forum Road/Gala Way, Nottingham<")],
  ["postcode shown separately", rows.includes('<div class="pc">NG5 9RW</div>')],
  ["type label mapped", rows.includes(">Land / other<")],
  ["condition underscores humanised", rows.includes("full refurb") || rows.includes("light refurb")],
  ["no literal undefined/NaN", !/undefined|NaN/.test(rows)],
];

const widths = [...status.matchAll(/width:([\d.]+)%/g)].map((m) => +m[1]);
checks.push(
  ["all bar widths within 0-100%", widths.length === 6 && widths.every((w) => w > 0 && w <= 100),
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
