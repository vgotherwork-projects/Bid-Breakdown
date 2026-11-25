const els = {};
["name", "ctc", "currency", "employment_type", "date_of_joining", "annual_hours", "markup_pct", "errorMsg", "metaNote", "totalBadge", "breakdownBody", "billingRate", "dojField", "resetBtn", "exportXlsxBtn", "exportPdfBtn", "clearBtn", "submitBtn", "batchFile", "batchProcessBtn", "batchExportBtn", "batchError", "batchWarn", "batchResult", "batchHead", "batchBody", "batchCount"].forEach(
    (id) => (els[id] = document.getElementById(id))
);

let lastValidPayload = null;
let lastBatchFile = null;

const DEFAULTS = {
    name: "Employee",
    ctc: 1200000,
    currency: "INR",
    employment_type: "new_hire",
    date_of_joining: "",
    annual_hours: 1880,
    markup_pct: 25,
};

let debounceTimer = null;

function toggleDoj() {
    const isExisting = els.employment_type.value === "existing";
    els.dojField.style.display = isExisting ? "" : "none";
    if (isExisting && !els.date_of_joining.value) {
        // default to ~6 years ago for a sensible starting example
        const d = new Date();
        d.setFullYear(d.getFullYear() - 6);
        els.date_of_joining.value = d.toISOString().slice(0, 10);
    }
}

function readInputs() {
    const payload = {
        name: els.name.value || "Employee",
        currency: (els.currency.value || "INR").toUpperCase().slice(0, 3),
        ctc: Number(els.ctc.value || 0),
        employment_type: els.employment_type.value,
    };
    if (els.employment_type.value === "existing" && els.date_of_joining.value) {
        payload.date_of_joining = els.date_of_joining.value;
    }
    const hours = Number(els.annual_hours.value || 0);
    if (hours > 0) payload.annual_hours = hours;
    const markup = Number(els.markup_pct.value || 0);
    if (markup >= 0) payload.markup_pct = markup;
    return payload;
}

function scheduleCalc() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(calculate, 200);
}

async function calculate() {
    const payload = readInputs();
    if (!payload.ctc || payload.ctc <= 0) {
        showError("Enter an annual CTC greater than 0.");
        setExportEnabled(false);
        return;
    }
    if (payload.employment_type === "existing" && !payload.date_of_joining) {
        showError("Select a date of joining for an existing employee.");
        setExportEnabled(false);
        return;
    }
    try {
        const res = await fetch("/bids/calculate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            throw new Error(formatApiError(body));
        }
        els.errorMsg.classList.add("hidden");
        render(await res.json());
        lastValidPayload = payload;
        setExportEnabled(true);
    } catch (err) {
        showError(err.message || "Calculation failed");
        setExportEnabled(false);
    }
}

function setExportEnabled(enabled) {
    if (els.exportXlsxBtn) els.exportXlsxBtn.disabled = !enabled;
    if (els.exportPdfBtn) els.exportPdfBtn.disabled = !enabled;
}

async function exportBreakdown(format) {
    if (!lastValidPayload) return;
    const btn = format === "xlsx" ? els.exportXlsxBtn : els.exportPdfBtn;
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = "...";
    try {
        const res = await fetch(`/bids/export/${format}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(lastValidPayload),
        });
        if (!res.ok) throw new Error("Export failed");
        const blob = await res.blob();
        const disposition = res.headers.get("Content-Disposition") || "";
        const match = disposition.match(/filename="?([^"]+)"?/);
        const filename = match ? match[1] : `breakdown.${format}`;
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (err) {
        showError(err.message || "Export failed");
    } finally {
        btn.textContent = original;
        btn.disabled = false;
    }
}

function showError(msg) {
    els.errorMsg.textContent = msg;
    els.errorMsg.classList.remove("hidden");
}

function render(b) {
    const money = (v) => formatMoney(v, b.currency);
    els.breakdownBody.innerHTML = b.rows
        .map(
            (r) => `
            <tr class="brk-tr ${r.kind}">
                <td data-label="Component">${escapeHtml(r.label)}</td>
                <td class="num" data-label="Monthly">${money(r.monthly)}</td>
                <td class="num" data-label="Annual">${money(r.annual)}</td>
                <td class="num" data-label="Per hour">${money(r.hourly)}</td>
            </tr>`
        )
        .join("");

    const grand = b.rows.find((r) => r.key === "grand_total");
    els.totalBadge.textContent = grand ? money(grand.annual) + " / yr" : "—";

    els.billingRate.classList.remove("hidden");
    els.billingRate.innerHTML = `
        <div class="br-line">
            <span>Grand total / hour</span>
            <span>${money(b.grand_total_hourly)}</span>
        </div>
        <div class="br-line strong">
            <span>Billing rate / hour <small>(+${b.markup_pct}% markup)</small></span>
            <span>${money(b.billing_rate_per_hour)}</span>
        </div>`;

    const tenure = b.employment_type === "existing"
        ? `Tenure: <strong>${b.tenure_years} yrs</strong> &middot; Gratuity tenure (rounded): <strong>${b.gratuity_years} yrs</strong> &middot; PTO: <strong>${b.pto_days} days</strong> &middot; `
        : `New hire (DOJ defaulted to ${b.effective_date_of_joining}) &middot; `;
    els.metaNote.innerHTML = `${tenure}Basic: <strong>${money(b.basic_monthly)}/mo</strong> &middot; Annual hours: <strong>${b.annual_hours}</strong>`;
}

function formatNum2(value) {
    if (value === "" || value == null) return "";
    return Number(value).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}
function formatMoney(value, currency) {
    try {
        return new Intl.NumberFormat(undefined, {
            style: "currency",
            currency,
            maximumFractionDigits: 2,
        }).format(value || 0);
    } catch {
        return `${currency} ${(value || 0).toFixed(2)}`;
    }
}
function formatApiError(body) {
    if (body && Array.isArray(body.detail)) {
        return body.detail.map((d) => `${(d.loc || []).slice(-1)}: ${d.msg}`).join("; ");
    }
    return (body && body.detail) || "Invalid input";
}
function escapeHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

els.employment_type.addEventListener("change", () => {
    toggleDoj();
    scheduleCalc();
});
["name", "ctc", "currency", "date_of_joining", "annual_hours", "markup_pct"].forEach((id) =>
    els[id].addEventListener("input", scheduleCalc)
);
els.exportXlsxBtn.addEventListener("click", () => exportBreakdown("xlsx"));
els.exportPdfBtn.addEventListener("click", () => exportBreakdown("pdf"));
els.submitBtn.addEventListener("click", calculate);
els.clearBtn.addEventListener("click", clearInputs);

function clearInputs() {
    els.name.value = "";
    els.ctc.value = "";
    els.date_of_joining.value = "";
    lastValidPayload = null;
    setExportEnabled(false);
    els.breakdownBody.innerHTML = "";
    els.billingRate.classList.add("hidden");
    els.billingRate.innerHTML = "";
    els.metaNote.innerHTML = "";
    els.totalBadge.textContent = "—";
    els.errorMsg.classList.add("hidden");
    els.name.focus();
}
els.resetBtn.addEventListener("click", () => {
    els.name.value = DEFAULTS.name;
    els.ctc.value = DEFAULTS.ctc;
    els.currency.value = DEFAULTS.currency;
    els.employment_type.value = DEFAULTS.employment_type;
    els.date_of_joining.value = "";
    els.annual_hours.value = DEFAULTS.annual_hours;
    els.markup_pct.value = DEFAULTS.markup_pct;
    toggleDoj();
    scheduleCalc();
});

// ---------- Batch upload ----------
// Wide master-table layout (one row per worker). Identity/supplier columns come
// from the uploaded file; cost components are the per-hour values we compute;
// modelled-as-zero allowances show 0.
const BATCH_COLS = [
    { label: "SL No", num: true, get: (it) => (it.sno == null ? "" : it.sno) },
    { label: "STGI-ID", get: (it) => it.stgi_id || "" },
    { label: "Agency worker Name", get: (it) => it.breakdown.name },
    { label: "Supplier", get: (it) => it.supplier || "" },
    { label: "B2B Contractor ID", get: (it) => it.b2b_id || "" },
    { label: "PO Number", get: (it) => it.po_number || "" },
    { label: "PO Rate (INR)", num2: true, get: (it) => (it.po_rate == null ? "" : it.po_rate) },
    { label: "Worker Payroll (Basic)", money: true, get: (it) => hourlyOf(it.breakdown, "basic") },
    { label: "House Rent Allowance (HRA)", money: true, get: (it) => hourlyOf(it.breakdown, "hra") },
    { label: "Gratuity", money: true, get: (it) => hourlyOf(it.breakdown, "gratuity") },
    { label: "Provident Fund (PF) - Employers Cont.", money: true, get: (it) => hourlyOf(it.breakdown, "employer_pf") },
    { label: "Bonus", money: true, get: () => 0 },
    { label: "Paid Time Off", money: true, get: (it) => hourlyOf(it.breakdown, "pto") },
    { label: "Health Insurance & Life Insurance", money: true, get: (it) => hourlyOf(it.breakdown, "medical") },
    { label: "Driver Allowance", money: true, get: () => 0 },
    { label: "Stationary Allowance", money: true, get: () => 0 },
    { label: "Meal Allowance / Coupons", money: true, get: () => 0 },
    { label: "Transport Allowance", money: true, get: (it) => hourlyOf(it.breakdown, "conveyance") },
    { label: "Internet Allowance", money: true, get: () => 0 },
    { label: "Phone Allowance", money: true, get: () => 0 },
    { label: "Vehicle / Fuel Allowance", money: true, get: () => 0 },
    { label: "Other Worker Specific Cost 1", money: true, get: (it) => hourlyOf(it.breakdown, "special_pay") },
    { label: "Other Worker Specific Cost 2", money: true, get: () => 0 },
    { label: "Supplier Contact Name", get: (it) => it.contact_name || "" },
    { label: "Supplier Contact Email", get: (it) => it.contact_email || "" },
    { label: "Supplier Contact Phone", get: (it) => it.contact_phone || "" },
];

function hourlyOf(b, key) {
    const row = (b.rows || []).find((r) => r.key === key);
    return row ? row.hourly : 0;
}

function setBatchError(msg) {
    els.batchError.textContent = msg;
    els.batchError.classList.toggle("hidden", !msg);
}

function clearBatch() {
    lastBatchFile = null;
    els.batchHead.innerHTML = "";
    els.batchBody.innerHTML = "";
    els.batchResult.classList.add("hidden");
    els.batchCount.textContent = "—";
    els.batchWarn.textContent = "";
    els.batchWarn.classList.add("hidden");
    setBatchError("");
    els.batchExportBtn.disabled = true;
}

async function batchProcess() {
    const file = els.batchFile.files[0];
    if (!file) {
        setBatchError("Choose a .xlsx or .csv file first.");
        return;
    }
    clearBatch();
    els.batchProcessBtn.disabled = true;
    const original = els.batchProcessBtn.textContent;
    els.batchProcessBtn.textContent = "Processing...";
    try {
        const form = new FormData();
        form.append("file", file);
        const res = await fetch("/bids/batch/calculate", { method: "POST", body: form });
        if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            throw new Error(formatApiError(body));
        }
        const data = await res.json();
        lastBatchFile = file;
        renderBatch(data);
        els.batchExportBtn.disabled = data.count === 0;
    } catch (err) {
        setBatchError(err.message || "Could not process the file.");
        els.batchExportBtn.disabled = true;
    } finally {
        els.batchProcessBtn.textContent = original;
        els.batchProcessBtn.disabled = false;
    }
}

function renderBatch(data) {
    els.batchCount.textContent = `${data.count} processed`;
    const isNum = (c) => c.money || c.num || c.num2;
    els.batchHead.innerHTML =
        "<tr>" +
        BATCH_COLS.map((c) => `<th class="${isNum(c) ? "num" : ""}">${escapeHtml(c.label)}</th>`).join("") +
        "</tr>";
    els.batchBody.innerHTML = data.results
        .map((it) => {
            const cur = it.breakdown.currency;
            return (
                "<tr>" +
                BATCH_COLS.map((c) => {
                    const v = c.get(it);
                    let text;
                    if (c.money) text = formatMoney(v, cur);
                    else if (c.num2) text = formatNum2(v);
                    else text = escapeHtml(String(v));
                    return `<td class="${isNum(c) ? "num" : ""}">${text}</td>`;
                }).join("") +
                "</tr>"
            );
        })
        .join("");
    els.batchResult.classList.toggle("hidden", data.results.length === 0);

    if (data.errors && data.errors.length) {
        const lines = data.errors
            .map((e) => `Row ${e.row}${e.name ? ` (${e.name})` : ""}: ${e.message}`)
            .join(" · ");
        els.batchWarn.textContent = `Skipped ${data.errors.length} row(s): ${lines}`;
        els.batchWarn.classList.remove("hidden");
    } else {
        els.batchWarn.classList.add("hidden");
    }
}

async function batchExport() {
    if (!lastBatchFile) return;
    const original = els.batchExportBtn.textContent;
    els.batchExportBtn.disabled = true;
    els.batchExportBtn.textContent = "...";
    try {
        const form = new FormData();
        form.append("file", lastBatchFile);
        const res = await fetch("/bids/batch/export", { method: "POST", body: form });
        if (!res.ok) throw new Error("Export failed");
        const blob = await res.blob();
        const disposition = res.headers.get("Content-Disposition") || "";
        const match = disposition.match(/filename="?([^"]+)"?/);
        const filename = match ? match[1] : "batch-breakdown.xlsx";
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (err) {
        setBatchError(err.message || "Export failed");
    } finally {
        els.batchExportBtn.textContent = original;
        els.batchExportBtn.disabled = false;
    }
}

if (els.batchProcessBtn) els.batchProcessBtn.addEventListener("click", batchProcess);
if (els.batchExportBtn) els.batchExportBtn.addEventListener("click", batchExport);
if (els.batchFile) els.batchFile.addEventListener("change", clearBatch);

toggleDoj();
calculate();
