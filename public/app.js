// Plain JavaScript, no libraries. Two tabs: claims checker and stock health.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const rupees = (n) => (n == null ? "–" : "Rs " + Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
let samples = [];

// ---------------------------------------------------------------- tabs
document.querySelectorAll(".tab").forEach((btn) =>
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".panel").forEach((p) => (p.hidden = p.id !== btn.dataset.tab));
    if (btn.dataset.tab === "stock") loadStock();
  })
);

// ---------------------------------------------------------------- claims checker
async function loadSamples() {
  try {
    samples = await (await fetch("/api/samples")).json();
    $("sample").innerHTML = '<option value="">Choose an email…</option>' +
      samples.map((e, i) => `<option value="${i}">${esc(e.email_id)} · ${esc(e.from_name)} · ${esc(e.subject)}</option>`).join("");
  } catch {
    $("sample").innerHTML = '<option value="">Could not load the sample emails</option>';
  }
}

$("sample").addEventListener("change", () => {
  const e = samples[$("sample").value];
  if (!e) return;
  $("email").value = e.body;
  $("sender").value = e.stockist_code_by_mailbox_rule;
  const [d, m, y] = e.received_date.split("-");
  $("day").value = `${y}-${m}-${d}`;
});

$("run").addEventListener("click", async () => {
  const out = $("result");
  if (!$("email").value.trim()) { out.innerHTML = '<p class="state error">Paste an email first.</p>'; return; }
  $("run").disabled = true;
  out.innerHTML = '<p class="state">Reading the email and checking each claim line… usually 3 to 10 seconds.</p>';
  try {
    const res = await fetch("/api/claim", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email_text: $("email").value, sender_code: $("sender").value, claim_date: $("day").value || null }),
    });
    const body = await res.json();
    if (!res.ok || body.error) throw new Error(body.error || `Server error ${res.status}`);
    out.innerHTML = renderClaim(body);
  } catch (err) {
    out.innerHTML = `<p class="state error">Could not check this email: ${esc(err.message)}</p>`;
  } finally {
    $("run").disabled = false;
  }
});

function renderClaim(r) {
  const cls = r.decision.split(" ")[0];
  let html = `<div class="decision ${cls}"><strong>${esc(r.decision)}</strong>${esc(r.reason)}
    <div class="owner">Decides: a Commercial Finance claims executive (Neha Bansal's team). Model calls: ${r.model_calls ?? 0}</div></div>`;
  (r.errors || []).forEach((e) => (html += `<p class="state error">${esc(e)}</p>`));
  (r.lines || []).forEach((ln) => {
    html += `<div class="line"><h3>Line ${ln.line}: ${esc(ln.decision)}</h3>
      <div>${esc(ln.product)} · batch ${esc(ln.batch_no)} · ${ln.quantity ?? "?"} packs · value ${rupees(ln.value_inr)}</div>
      <div class="scroll"><table><thead><tr><th>Check</th><th>Result</th><th>Why</th><th>Source</th></tr></thead><tbody>
      ${ln.checks.map((c) => `<tr><td>${esc(c.rule)}</td><td><span class="badge b-${c.result}">${esc(c.result)}</span></td><td>${esc(c.detail)}</td><td>${esc(c.source)}</td></tr>`).join("")}
      </tbody></table></div>
      ${ln.evidence.length ? `<h2>Evidence rows</h2><div class="scroll"><table><thead><tr><th>File</th><th>Line</th><th>What it shows</th></tr></thead><tbody>
      ${ln.evidence.map((e) => `<tr><td>${esc(e.file)}</td><td>${e.line}</td><td>${esc(e.what)}</td></tr>`).join("")}</tbody></table></div>` : ""}
    </div>`;
  });
  (r.statuses || []).forEach((s) => {
    html += `<div class="line">${esc(s.text)}${s.evidence ? ` <span class="owner">(${esc(s.evidence.file)} line ${s.evidence.line})</span>` : ""}</div>`;
  });
  html += `<h2>Draft reply to the stockist</h2><pre>${esc(r.reply)}</pre>`;
  if (r.read) html += `<details><summary>What the model read from the email</summary><pre>${esc(JSON.stringify(r.read, null, 2))}</pre></details>`;
  return html;
}

// ---------------------------------------------------------------- stock health
let stockLoaded = false;
async function loadStock() {
  if (stockLoaded) return;
  const out = $("stock-out");
  try {
    const s = await (await fetch("/api/stock")).json();
    stockLoaded = true;
    out.innerHTML = `
      <div class="card"><strong>Month-end ${esc(s.as_of)}.</strong> The network holds ${s.national_cover_months} months of cover in total,
        inside the 2-month target, but it sits in the wrong places. <span class="owner">Decides: Kavita Rao's planners; Subhajit Banerjee for Kolkata.</span></div>
      <h2>By C&amp;F</h2>
      <div class="scroll"><table><thead><tr><th>C&amp;F</th><th>Stock (Rs cr)</th><th>Months of cover</th><th>SKUs at zero (of 36)</th>
        <th>Above 2-month cover (Rs cr)</th><th>Below 2-month cover (Rs cr)</th><th>Off-FEFO picks, ${esc(s.fefo_months)}</th><th>Stock under 60% shelf life (Rs lakh)</th></tr></thead><tbody>
      ${s.cfas.map((c) => `<tr><td>${esc(c.cnf_code)} ${esc(c.city)}</td><td>${c.stock_cr}</td>
        <td class="${c.cover_months < 0.5 || c.cover_months > 3 ? "hot" : ""}">${c.cover_months}</td>
        <td class="${c.skus_at_zero > 10 ? "hot" : ""}">${c.skus_at_zero}</td><td>${c.above_target_cr}</td><td>${c.below_target_cr}</td>
        <td class="${c.off_fefo_pct > 5 ? "hot" : ""}">${c.off_fefo_pct}%</td><td class="${c.aged_lakh > 50 ? "hot" : ""}">${c.aged_lakh}</td></tr>`).join("")}
      </tbody></table></div>
      <h2>Short at one C&amp;F, more than 2 months at another (${s.wrong_place.length} SKUs)</h2>
      <div class="scroll"><table><thead><tr><th>SKU</th><th>Product</th><th>Short at</th><th>Long at</th><th>Packs that could move</th></tr></thead><tbody>
      ${s.wrong_place.map((w) => `<tr><td>${esc(w.sku_code)}</td><td>${esc(w.product)}</td><td>${esc(w.short_at)}</td><td>${esc(w.long_at)}</td><td>${w.packs_to_move.toLocaleString("en-IN")}</td></tr>`).join("")}
      </tbody></table></div>
      <h2>Largest lots under 60% shelf life (cannot be billed under CO-POL-014 s7.1)</h2>
      <div class="scroll"><table><thead><tr><th>C&amp;F</th><th>Product</th><th>Batch</th><th>Expiry</th><th>Packs</th><th>Shelf life left</th><th>Rs lakh</th></tr></thead><tbody>
      ${s.aged_lots.map((a) => `<tr><td>${esc(a.cnf_code)}</td><td>${esc(a.product)}</td><td>${esc(a.batch_no)}</td><td>${esc(a.expiry)}</td><td>${a.packs.toLocaleString("en-IN")}</td><td>${a.shelf_life_left_pct}%</td><td>${a.value_lakh}</td></tr>`).join("")}
      </tbody></table></div>`;
  } catch (err) {
    out.innerHTML = `<p class="state error">Could not load stock health: ${esc(err.message)}</p>`;
  }
}

$("day").value = new Date().toISOString().slice(0, 10);
loadSamples();
