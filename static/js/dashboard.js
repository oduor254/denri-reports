const FLAG_ICONS = {
  risk: "\u{1F534}",
  positive: "\u{1F7E2}",
  watch: "⚠️",
  key: "\u{1F511}",
  escalation: "\u{1F6A8}",
  context: "\u{1F5D3}",
};

function toneClass(dir) {
  return `tone-${dir || "neutral"}`;
}

const PERIOD_TITLES = { day: "DAILY", week: "WEEKLY", month: "MONTHLY" };

function renderBanner(meta) {
  document.getElementById("banner-title").textContent =
    `${PERIOD_TITLES[meta.period_type] || ""} SALES PERFORMANCE REPORT`;
  document.getElementById("banner-period").textContent =
    `${meta.period_label} | ${meta.date_range} (${meta.days} day${meta.days === 1 ? "" : "s"})`;
  document.getElementById("banner-compared").textContent = `Compared to: ${meta.compared_to}`;
}

function renderKpiCards(elId, cards) {
  const el = document.getElementById(elId);
  el.innerHTML = cards.map(card => `
    <div class="kpi-card">
      <div class="kpi-label">${card.label}</div>
      <div class="kpi-value">${card.value}</div>
      <div class="kpi-sub ${toneClass(card.tone)}">${card.sub}</div>
    </div>
  `).join("");
}

function renderContext(note) {
  document.getElementById("context-callout").innerHTML =
    `<strong>${FLAG_ICONS.context} PERIOD CONTEXT</strong><br>${note}`;
}

function renderComparisonTable(tbodyEl, rows) {
  tbodyEl.innerHTML = rows.map(row => `
    <tr>
      <td class="col-metric">${row.metric}</td>
      <td class="col-value">${row.current}</td>
      <td class="col-value">${row.previous}</td>
      <td class="col-change ${toneClass(row.dir)}">${row.change}</td>
    </tr>
  `).join("");
}

function renderMeetingNote(elId, note) {
  document.getElementById(elId).innerHTML = `\u{1F4CB} ${note}`;
}

function renderExecSummary(execSummary) {
  document.getElementById("exec-narrative").textContent = execSummary.narrative;

  renderComparisonTable(document.querySelector("#exec-table tbody"), execSummary.metrics);

  const flagsEl = document.getElementById("exec-flags");
  flagsEl.innerHTML = execSummary.flags.map(flag => `
    <div class="flag flag-${flag.kind}">
      <span>${FLAG_ICONS[flag.kind] || ""}</span>
      <span>${flag.text}</span>
    </div>
  `).join("");

  renderMeetingNote("exec-meeting-note", execSummary.meeting_note);
}

function renderCustomerMetrics(customerMetrics) {
  document.getElementById("customer-summary").textContent = customerMetrics.summary;

  renderComparisonTable(document.querySelector("#customer-table tbody"), customerMetrics.comparison);

  const freqBody = document.querySelector("#frequency-table tbody");
  freqBody.innerHTML = customerMetrics.frequency.map(row => `
    <tr>
      <td class="col-metric">${row.band}</td>
      <td class="col-value">${row.count}</td>
      <td class="col-value">${row.pct}</td>
      <td class="col-read read-${row.band.startsWith("6+") ? "vip" : row.band.startsWith("3-5") ? "target" : "neutral"}">${row.read}</td>
    </tr>
  `).join("");

  const channelBody = document.querySelector("#channel-table tbody");
  channelBody.innerHTML = customerMetrics.channels.map(row => `
    <tr class="${row.channel === "TOTAL" ? "row-total" : ""}">
      <td class="col-metric">${row.channel}</td>
      <td class="col-value">${row.orders}</td>
      <td class="col-value">${row.share}</td>
      <td class="col-value">${row.avg_spend}</td>
      <td class="col-note">${row.note}</td>
    </tr>
  `).join("");

  renderMeetingNote("customer-meeting-note", customerMetrics.meeting_note);
}

function renderStoreTable(rows) {
  const table = document.getElementById("store-table");
  const tbody = table.querySelector("tbody");
  const totalRow = rows.find(r => r.shop === "TOTAL");
  const shopRows = rows.filter(r => r.shop !== "TOTAL");

  let sortKey = table.dataset.sortKey || "current_raw";
  let sortDir = table.dataset.sortDir || "desc";

  const sorted = [...shopRows].sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    const cmp = typeof av === "string" ? av.localeCompare(bv) : av - bv;
    return sortDir === "asc" ? cmp : -cmp;
  });

  const renderRow = row => `
    <tr class="${row.shop === "TOTAL" ? "row-total" : ""}">
      <td class="col-metric">${row.shop}</td>
      <td class="col-value">${row.current}</td>
      <td class="col-value">${row.previous}</td>
      <td class="col-change ${toneClass(row.dir)}">${row.change}</td>
      <td class="col-value ${toneClass(row.dir)}">${row.change_pct}</td>
      <td class="col-value">${row.new}</td>
      <td class="col-value">${row.repeat}</td>
      <td class="col-value">${row.repeat_rate}</td>
    </tr>
  `;

  tbody.innerHTML = sorted.map(renderRow).join("") + (totalRow ? renderRow(totalRow) : "");

  table.querySelectorAll("th.sortable").forEach(th => {
    th.classList.toggle("sort-active", th.dataset.key === sortKey);
    th.dataset.sortDir = th.dataset.key === sortKey ? sortDir : "";
  });
}

function initStoreTableSorting(rows) {
  const table = document.getElementById("store-table");
  table.querySelectorAll("th.sortable").forEach(th => {
    th.onclick = () => {
      const key = th.dataset.key;
      const rawKey = key === "shop" ? "shop" : `${key}_raw`;
      const isSameCol = table.dataset.sortKey === rawKey;
      table.dataset.sortKey = rawKey;
      table.dataset.sortDir = isSameCol && table.dataset.sortDir === "desc" ? "asc" : "desc";
      renderStoreTable(rows);
    };
  });
}

function renderStorePerformance(storePerformance) {
  document.getElementById("store-summary").textContent = storePerformance.summary;

  initStoreTableSorting(storePerformance.rows);
  renderStoreTable(storePerformance.rows);

  const mixBody = document.querySelector("#channel-mix-table tbody");
  mixBody.innerHTML = storePerformance.channel_mix.map(row => `
    <tr class="${row.shop === "TOTAL" ? "row-total" : ""}">
      <td class="col-metric">${row.shop}</td>
      <td class="col-value">${row.walkin}</td>
      <td class="col-value">${row.walkin_sales}</td>
      <td class="col-value">${row.online}</td>
      <td class="col-value">${row.online_sales}</td>
      <td class="col-value">${row.activation}</td>
      <td class="col-value">${row.activation_sales}</td>
      <td class="col-value">${row.total}</td>
      <td class="col-value">${row.total_sales}</td>
      <td class="col-value">${row.online_pct}</td>
    </tr>
  `).join("");

  const retentionWrap = document.getElementById("store-retention-wrap");
  if (storePerformance.monthly_retention) {
    retentionWrap.hidden = false;
    attachSortableTable(
      document.getElementById("store-retention-table"),
      () => storePerformance.monthly_retention,
      row => `
        <tr class="${row.shop === "TOTAL" ? "row-total" : ""}">
          <td class="col-metric">${row.shop}</td>
          <td class="col-value">${row.current}</td>
          <td class="col-value">${row.current_sales}</td>
          <td class="col-value">${row.previous}</td>
          <td class="col-value">${row.previous_sales}</td>
          <td class="col-change ${toneClass(row.dir)}">${row.change}</td>
          <td class="col-value">${row.repeat}</td>
          <td class="col-value">${row.repeat_sales}</td>
          <td class="col-value">${row.repeat_rate}</td>
          <td class="col-value">${row.retention}</td>
          <td class="col-value">${row.retention_sales}</td>
          <td class="col-value">${row.retention_rate}</td>
        </tr>
      `,
      { defaultKey: "current_raw", isTotalRow: row => row.shop === "TOTAL" }
    );
  } else {
    retentionWrap.hidden = true;
  }

  renderMeetingNote("store-meeting-note", storePerformance.meeting_note);
}

// Fixed categorical order (palette slots 1-3) - Female/Male/Corporate
// always map to the same series color, so identity stays consistent across
// reloads regardless of which shops have Corporate activity that period.
const GENDER_SERIES = {
  female: { css: "series-1", color: "var(--series-1)" },
  male: { css: "series-2", color: "var(--series-2)" },
  corporate: { css: "series-3", color: "var(--series-3)" },
};

function renderGenderRatio(ratio) {
  const el = document.getElementById("gender-ratio");
  if (!ratio) {
    el.textContent = "";
    return;
  }
  el.innerHTML = `<strong>${ratio.ratio_text}</strong> — ${ratio.female_pct} Female / ${ratio.male_pct} Male overall`;
}

function renderGenderLocationTable(columns, rows) {
  const table = document.getElementById("gender-location-table");
  const totalRow = rows.find(r => r.shop === "TOTAL");
  const shopRows = rows.filter(r => r.shop !== "TOTAL");

  const theadRow = `<tr>
    <th class="col-metric sortable" data-key="shop">Shop</th>
    ${columns.map(c => `
      <th class="col-value sortable" data-key="${c.toLowerCase()}_raw">${c}</th>
      <th class="col-value sortable" data-key="${c.toLowerCase()}_pct_raw">${c} %</th>
    `).join("")}
    <th class="col-value sortable" data-key="total_raw">Total</th>
  </tr>`;
  table.querySelector("thead").innerHTML = theadRow;

  const renderRow = row => `
    <tr class="${row.shop === "TOTAL" ? "row-total" : ""}">
      <td class="col-metric">${row.shop}</td>
      ${columns.map(c => {
        const key = c.toLowerCase();
        return `<td class="col-value">${row[key]}</td><td class="col-value">${row[`${key}_pct`]}</td>`;
      }).join("")}
      <td class="col-value">${row.total}</td>
    </tr>
  `;

  function draw() {
    const key = table.dataset.sortKey || "total_raw";
    const dir = table.dataset.sortDir || "desc";
    const sorted = [...shopRows].sort((a, b) => {
      const av = a[key], bv = b[key];
      const cmp = typeof av === "string" ? av.localeCompare(bv) : av - bv;
      return dir === "asc" ? cmp : -cmp;
    });
    table.querySelector("tbody").innerHTML = sorted.map(renderRow).join("") + (totalRow ? renderRow(totalRow) : "");
    table.querySelectorAll("th.sortable").forEach(th => {
      th.classList.toggle("sort-active", th.dataset.key === key);
      th.dataset.sortDir = th.dataset.key === key ? dir : "";
    });
  }

  table.querySelectorAll("th.sortable").forEach(th => {
    th.onclick = () => {
      const isSame = table.dataset.sortKey === th.dataset.key;
      table.dataset.sortKey = th.dataset.key;
      table.dataset.sortDir = isSame && table.dataset.sortDir === "desc" ? "asc" : "desc";
      draw();
    };
  });

  draw();
}

// Multiple side-by-side chart panels. Each panel independently isolates a
// series (click its legend item) and picks its own chart type - state lives
// here so re-renders (sorting the table, reloading data) don't reset what the
// user set up. Deliberately no pie/donut (part-to-whole reads worse than a
// stacked bar) and no 3D (perspective distorts magnitude - see the dataviz
// skill's anti-patterns) - "Stacked %", "Stacked count", and "Grouped bars"
// cover the legitimate ways to look at this composition-plus-magnitude data.
const CHART_TYPES = [
  { value: "stacked-pct", label: "Stacked bar (%)" },
  { value: "stacked-count", label: "Stacked bar (count)" },
  { value: "grouped", label: "Grouped bars" },
];

let genderVizCards = [{ id: 1, isolated: null, chartType: "stacked-pct" }];
let genderVizNextId = 2;
let genderVizData = { columns: [], rows: [] };

// --- Custom hover tooltip (shared by every chart segment/bar) ---

function ensureVizTooltip() {
  let el = document.getElementById("viz-tooltip");
  if (!el) {
    el = document.createElement("div");
    el.id = "viz-tooltip";
    el.className = "viz-tooltip";
    el.hidden = true;
    document.body.appendChild(el);
  }
  return el;
}

function showVizTooltip(evt, html) {
  const el = ensureVizTooltip();
  el.innerHTML = html;
  el.hidden = false;
  positionVizTooltip(evt);
}

function positionVizTooltip(evt) {
  const el = document.getElementById("viz-tooltip");
  if (!el || el.hidden) return;
  const pad = 14;
  let x = evt.clientX + pad;
  let y = evt.clientY + pad;
  const rect = el.getBoundingClientRect();
  if (x + rect.width > window.innerWidth) x = evt.clientX - rect.width - pad;
  if (y + rect.height > window.innerHeight) y = evt.clientY - rect.height - pad;
  el.style.left = `${x}px`;
  el.style.top = `${y}px`;
}

function hideVizTooltip() {
  const el = document.getElementById("viz-tooltip");
  if (el) el.hidden = true;
}

function wireVizTooltips(container) {
  container.querySelectorAll("[data-tooltip]").forEach(el => {
    el.addEventListener("mouseenter", evt => showVizTooltip(evt, el.dataset.tooltip));
    el.addEventListener("mousemove", positionVizTooltip);
    el.addEventListener("mouseleave", hideVizTooltip);
  });
}

function vizTooltipHtml(shop, gender, count, pct) {
  return `<strong>${shop}</strong><br>${gender}: ${count} (${pct})`;
}

// --- Row renderers, one per chart type ---

function renderStackedRow(row, columns, isolated, widthBasis) {
  const segments = columns.map(c => {
    const key = c.toLowerCase();
    const pct = row[`${key}_pct_raw`] || 0;
    const width = widthBasis === "pct" ? pct : (row[`${key}_width`] || 0);
    const series = GENDER_SERIES[key];
    const isDimmed = isolated && isolated !== key;
    const showLabel = !isDimmed && pct >= 8;
    const tip = vizTooltipHtml(row.shop, c, row[key], row[`${key}_pct`]);
    return `<div class="stack-segment ${series.css} ${isDimmed ? "dimmed" : ""}" style="width:${width}%;${isDimmed ? "" : `background:${series.color}`}"
              data-tooltip="${tip.replace(/"/g, "&quot;")}">${showLabel ? row[`${key}_pct`] : ""}</div>`;
  }).join("");

  return `
    <div class="stack-row">
      <span class="stack-label" title="${row.shop}">${row.shop}</span>
      <div class="stack-track">${segments}</div>
      <span class="stack-total">${row.total}</span>
    </div>
  `;
}

function renderGroupedRow(row, columns, isolated, maxValue) {
  const bars = columns.map(c => {
    const key = c.toLowerCase();
    const raw = row[`${key}_raw`] || 0;
    const width = maxValue ? (raw / maxValue) * 100 : 0;
    const series = GENDER_SERIES[key];
    const isDimmed = isolated && isolated !== key;
    const tip = vizTooltipHtml(row.shop, c, row[key], row[`${key}_pct`]);
    return `
      <div class="grouped-bar-track">
        <div class="grouped-bar ${series.css} ${isDimmed ? "dimmed" : ""}" style="width:${Math.max(width, raw > 0 ? 2 : 0)}%;${isDimmed ? "" : `background:${series.color}`}"
             data-tooltip="${tip.replace(/"/g, "&quot;")}"></div>
      </div>
    `;
  }).join("");

  return `
    <div class="stack-row grouped">
      <span class="stack-label" title="${row.shop}">${row.shop}</span>
      <div class="grouped-track">${bars}</div>
      <span class="stack-total">${row.total}</span>
    </div>
  `;
}

function renderGenderVizCard(card, columns, rows) {
  const legend = columns.map(c => {
    const key = c.toLowerCase();
    const active = card.isolated === key;
    return `
      <button type="button" class="legend-item ${active ? "active" : ""}" data-card="${card.id}" data-series="${key}">
        <span class="legend-swatch" style="background:${GENDER_SERIES[key].color}"></span>
        ${c}
      </button>
    `;
  }).join("");

  const bars = rows.filter(r => r.shop !== "TOTAL");
  const total = rows.find(r => r.shop === "TOTAL");
  const chartRows = total ? [total, ...bars] : bars;

  let bodyRows;
  if (card.chartType === "grouped") {
    const maxValue = Math.max(...chartRows.flatMap(row => columns.map(c => row[`${c.toLowerCase()}_raw`] || 0)), 1);
    bodyRows = chartRows.map(row => renderGroupedRow(row, columns, card.isolated, maxValue)).join("");
  } else {
    if (card.chartType === "stacked-count") {
      // Grand total is the 100%-width reference, so every shop's bar length
      // reflects its share of the whole (and TOTAL itself fills the track).
      const grandTotal = (total && total.total_raw) || Math.max(...bars.map(row => row.total_raw || 0), 1);
      chartRows.forEach(row => {
        const scale = grandTotal ? ((row.total_raw || 0) / grandTotal) * 100 : 0;
        columns.forEach(c => {
          const key = c.toLowerCase();
          row[`${key}_width`] = (row[`${key}_pct_raw`] || 0) * (scale / 100);
        });
      });
    }
    bodyRows = chartRows.map(row => renderStackedRow(row, columns, card.isolated, card.chartType === "stacked-pct" ? "pct" : "count")).join("");
  }

  const removeBtn = card.id === genderVizCards[0].id
    ? ""
    : `<button type="button" class="viz-remove" data-remove="${card.id}" aria-label="Remove visual">✕</button>`;

  const typeOptions = CHART_TYPES.map(t => `<option value="${t.value}" ${t.value === card.chartType ? "selected" : ""}>${t.label}</option>`).join("");

  return `
    <figure class="viz-card" data-card-root="${card.id}">
      <div class="viz-card-head">
        <figcaption class="viz-caption">Gender mix by location${card.isolated ? ` — ${card.isolated} isolated` : ""}</figcaption>
        <div class="viz-card-controls">
          <select class="viz-chart-select" data-card-type="${card.id}" aria-label="Chart type">${typeOptions}</select>
          ${removeBtn}
        </div>
      </div>
      <div class="viz-legend">${legend}</div>
      <div class="stacked-bars">${bodyRows}</div>
    </figure>
  `;
}

function renderGenderVizRow() {
  const { columns, rows } = genderVizData;
  const container = document.getElementById("gender-viz-row");

  const cardsHtml = genderVizCards.map(card => renderGenderVizCard(card, columns, rows)).join("");
  container.innerHTML = `${cardsHtml}<button type="button" class="viz-add-card" id="gender-viz-add">+ Add visual</button>`;

  container.querySelectorAll(".legend-item").forEach(btn => {
    btn.onclick = () => {
      const cardId = Number(btn.dataset.card);
      const series = btn.dataset.series;
      const card = genderVizCards.find(c => c.id === cardId);
      card.isolated = card.isolated === series ? null : series;
      renderGenderVizRow();
    };
  });

  container.querySelectorAll("[data-card-type]").forEach(select => {
    select.onchange = () => {
      const cardId = Number(select.dataset.cardType);
      const card = genderVizCards.find(c => c.id === cardId);
      card.chartType = select.value;
      renderGenderVizRow();
    };
  });

  container.querySelectorAll("[data-remove]").forEach(btn => {
    btn.onclick = () => {
      const cardId = Number(btn.dataset.remove);
      genderVizCards = genderVizCards.filter(c => c.id !== cardId);
      renderGenderVizRow();
    };
  });

  document.getElementById("gender-viz-add").onclick = () => {
    genderVizCards.push({ id: genderVizNextId++, isolated: null, chartType: "stacked-pct" });
    renderGenderVizRow();
  };

  wireVizTooltips(container);
}

function renderGenderChart(columns, rows) {
  genderVizData = { columns, rows };
  renderGenderVizRow();
}

function renderGenderPerformance(genderPerformance) {
  document.getElementById("gender-summary").textContent = genderPerformance.summary;

  const overallBody = document.querySelector("#gender-overall-table tbody");
  overallBody.innerHTML = genderPerformance.overall.map(row => `
    <tr>
      <td class="col-metric">${row.gender}</td>
      <td class="col-value">${row.count}</td>
      <td class="col-value">${row.pct}</td>
      <td class="col-change ${toneClass(row.dir)}">${row.change}</td>
    </tr>
  `).join("");

  renderGenderRatio(genderPerformance.ratio);

  const { columns, rows } = genderPerformance.by_location;
  renderGenderLocationTable(columns, rows);
  renderGenderChart(columns, rows);

  renderMeetingNote("gender-meeting-note", genderPerformance.meeting_note);
}

// Generic sortable-table wiring: click a th.sortable[data-key] to sort the
// tbody by that field (numeric or string), toggling asc/desc; a row matching
// isTotalRow (if given) always stays pinned to the bottom. Reusable across any
// table shaped like ours (Store Performance and Gender by Location predate
// this helper with their own copies - new tables should use this instead).
function attachSortableTable(table, getRows, renderRow, { defaultKey, defaultDir = "desc", isTotalRow = () => false } = {}) {
  function draw() {
    const rows = getRows();
    const totalRow = rows.find(isTotalRow);
    const dataRows = rows.filter(r => !isTotalRow(r));
    const key = table.dataset.sortKey || defaultKey;
    const dir = table.dataset.sortDir || defaultDir;

    const sorted = [...dataRows].sort((a, b) => {
      const av = a[key], bv = b[key];
      const cmp = typeof av === "string" ? av.localeCompare(bv) : av - bv;
      return dir === "asc" ? cmp : -cmp;
    });

    table.querySelector("tbody").innerHTML = sorted.map(renderRow).join("") + (totalRow ? renderRow(totalRow) : "");
    table.querySelectorAll("th.sortable").forEach(th => {
      th.classList.toggle("sort-active", th.dataset.key === key);
      th.dataset.sortDir = th.dataset.key === key ? dir : "";
    });
  }

  table.querySelectorAll("th.sortable").forEach(th => {
    th.onclick = () => {
      const isSame = table.dataset.sortKey === th.dataset.key;
      table.dataset.sortKey = th.dataset.key;
      table.dataset.sortDir = isSame && table.dataset.sortDir === "desc" ? "asc" : "desc";
      draw();
    };
  });

  draw();
}

function renderTrafficRow(row) {
  return `
    <tr class="${row.shop === "TOTAL" ? "row-total" : ""}">
      <td class="col-metric">${row.shop}</td>
      <td class="col-value">${row.walkin_purchased}</td>
      <td class="col-value">${row.walkin_total}</td>
      <td class="col-value">${row.conv_rate}</td>
      <td class="col-value">${row.online}</td>
      <td class="col-value">${row.activation}</td>
      <td class="col-value">${row.total_customers}</td>
    </tr>
  `;
}

function renderTraffic(traffic) {
  document.getElementById("traffic-summary").textContent = traffic.summary;

  const gapEl = document.getElementById("traffic-gap-callout");
  if (traffic.data_gap_note) {
    gapEl.hidden = false;
    gapEl.innerHTML = `<strong>⚠️ DATA GAP</strong><br>${traffic.data_gap_note}`;
  } else {
    gapEl.hidden = true;
  }

  attachSortableTable(
    document.getElementById("traffic-table"),
    () => traffic.rows,
    renderTrafficRow,
    { defaultKey: "walkin_total_raw", isTotalRow: row => row.shop === "TOTAL" }
  );

  renderMeetingNote("traffic-meeting-note", traffic.meeting_note);
}

function renderRevenueAnalysis(revenueAnalysis) {
  document.getElementById("revenue-summary").textContent = revenueAnalysis.summary;

  renderKpiCards("revenue-kpi-cards", revenueAnalysis.kpi_cards);
  renderComparisonTable(document.querySelector("#revenue-table tbody"), revenueAnalysis.comparison);

  document.querySelector("#revenue-bridge-table tbody").innerHTML = revenueAnalysis.bridge.map(row => `
    <tr>
      <td class="col-metric">${row.period}</td>
      <td class="col-value">${row.revenue}</td>
      <td class="col-value">${row.customers}</td>
      <td class="col-value">${row.avg_spend}</td>
      <td class="col-change ${toneClass(row.dir)}">${row.trend}</td>
    </tr>
  `).join("");

  renderMeetingNote("revenue-meeting-note", revenueAnalysis.meeting_note);
}

function renderDataQuality(dataQuality) {
  document.getElementById("dq-summary").textContent = dataQuality.summary;

  document.querySelector("#dq-table tbody").innerHTML = dataQuality.comparison.map(row => `
    <tr>
      <td class="col-metric">${row.metric}</td>
      <td class="col-value">${row.current}</td>
      <td class="col-value">${row.current_pct}</td>
      <td class="col-value">${row.previous}</td>
      <td class="col-value">${row.previous_pct}</td>
      <td class="col-change ${toneClass(row.dir)}">${row.change}</td>
    </tr>
  `).join("");

  const storeNumberTable = document.getElementById("dq-store-number-table");
  const storeNumberEmpty = document.getElementById("dq-store-number-empty");
  if (dataQuality.store_number_by_shop.length > 0) {
    storeNumberTable.hidden = false;
    storeNumberEmpty.hidden = true;
    storeNumberTable.querySelector("tbody").innerHTML = dataQuality.store_number_by_shop.map(row => `
      <tr>
        <td class="col-metric">${row.shop}</td>
        <td class="col-value">${row.unique_numbers}</td>
        <td class="col-value">${row.occurrences}</td>
      </tr>
    `).join("");
  } else {
    storeNumberTable.hidden = true;
    storeNumberEmpty.hidden = false;
  }

  document.getElementById("dq-score-note").innerHTML = `<strong>🔑 KYC SCORE</strong><br>${dataQuality.score_note}`;
  renderMeetingNote("dq-meeting-note", dataQuality.meeting_note);
}

function renderFeedback(feedback) {
  document.getElementById("feedback-summary").textContent = feedback.summary;

  document.querySelector("#feedback-table tbody").innerHTML = feedback.comparison.map(row => `
    <tr>
      <td class="col-metric">${row.metric}</td>
      <td class="col-value">${row.current}</td>
      <td class="col-value">${row.previous}</td>
      <td class="col-value ${toneClass(row.dir)}">${row.change}</td>
      <td class="col-status"><span class="status-badge tone-${row.status_tone}">${row.status}</span></td>
    </tr>
  `).join("");

  const targetEl = document.getElementById("feedback-target-note");
  if (feedback.target) {
    targetEl.hidden = false;
    const badge = feedback.target.status
      ? `<span class="status-badge tone-${feedback.target.status_tone}">${feedback.target.status}</span> `
      : "";
    targetEl.innerHTML = `<strong>🎯 TARGET</strong> ${badge}<br>${feedback.target.note}`;
  } else {
    targetEl.hidden = true;
  }

  document.querySelector("#feedback-store-table tbody").innerHTML = feedback.store_breakdown.map(row => `
    <tr class="${row.shop === "TOTAL" ? "row-total" : ""}">
      <td class="col-metric">${row.shop}</td>
      <td class="col-value">${row.current}</td>
      <td class="col-value">${row.previous}</td>
      <td class="col-change ${toneClass(row.dir)}">${row.change}</td>
    </tr>
  `).join("");

  const linksTable = document.getElementById("feedback-links-table");
  if (feedback.feedback_links && feedback.feedback_links.length > 0) {
    attachSortableTable(
      linksTable,
      () => feedback.feedback_links,
      row => `
        <tr class="${row.shop === "TOTAL" ? "row-total" : ""}">
          <td class="col-metric">${row.shop}</td>
          <td class="col-value">${row.links_sent}</td>
          <td class="col-value">${row.online}</td>
          <td class="col-value">${row.achv_pct}</td>
          <td class="col-value">${row.gap}</td>
          <td class="col-status"><span class="status-badge tone-${row.status_tone}">${row.status}</span></td>
          <td class="col-value">${row.walkins}</td>
        </tr>
      `,
      { defaultKey: "sent_raw", isTotalRow: row => row.shop === "TOTAL" }
    );
  }

  renderMeetingNote("feedback-meeting-note", feedback.meeting_note);
}

const DEPT_META = {
  marketing: { label: "Marketing", icon: "\u{1F4E2}" },
  sales: { label: "Sales", icon: "\u{1F4B0}" },
  production: { label: "Production", icon: "\u{1F4E6}" },
  data: { label: "Data", icon: "\u{1F5C4}️" },
};

const PRIORITY_TONE = { CRITICAL: "critical", HIGH: "warning", MEDIUM: "neutral", WIN: "good" };

function renderDeptCard(key, dept) {
  const meta = DEPT_META[key];

  if (dept.unavailable) {
    return `
      <div class="dept-card">
        <h3>${meta.icon} ${meta.label}</h3>
        <p class="dept-summary">${dept.summary}</p>
        <p class="dept-gap-note">${dept.note}</p>
      </div>
    `;
  }

  const items = dept.items.map(item => `
    <li>
      <span class="status-badge tone-${PRIORITY_TONE[item.priority]}">${item.priority}</span>
      <span>${item.text}</span>
    </li>
  `).join("");

  return `
    <div class="dept-card">
      <h3>${meta.icon} ${meta.label}</h3>
      <p class="dept-summary">${dept.summary}</p>
      ${items ? `<ul class="dept-items">${items}</ul>` : ""}
    </div>
  `;
}

function renderPriorities(priorities, periodType) {
  document.getElementById("priorities-title").textContent =
    `${PERIOD_TITLES[periodType] ? PERIOD_TITLES[periodType].charAt(0) + PERIOD_TITLES[periodType].slice(1).toLowerCase() : ""} Summary & Key Notes`;

  document.getElementById("priorities-grid").innerHTML =
    Object.keys(DEPT_META).map(key => renderDeptCard(key, priorities[key])).join("");
}

function addDays(isoDate, days) {
  const d = new Date(`${isoDate}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function getFilters() {
  const params = new URLSearchParams(window.location.search);
  return { period: params.get("period") || "week", date: params.get("date") || null };
}

function setFilters(filters, meta) {
  const params = new URLSearchParams();
  params.set("period", filters.period);
  if (filters.date) params.set("date", filters.date);
  const query = params.toString();
  window.history.pushState({}, "", query ? `?${query}` : window.location.pathname);
  fetchAndRender(meta);
}

function initFilterBar(meta) {
  const filters = getFilters();

  document.querySelectorAll(".filter-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.period === meta.period_type);
    btn.onclick = () => setFilters({ period: btn.dataset.period, date: null });
  });

  const dateInput = document.getElementById("filter-date");
  dateInput.min = meta.min_date;
  dateInput.max = meta.max_date;
  dateInput.value = meta.start;
  dateInput.onchange = () => setFilters({ period: meta.period_type, date: dateInput.value });

  const prevBtn = document.getElementById("filter-prev");
  const nextBtn = document.getElementById("filter-next");
  prevBtn.disabled = meta.start <= meta.min_date;
  nextBtn.disabled = meta.end >= meta.max_date;
  prevBtn.onclick = () => setFilters({ period: meta.period_type, date: addDays(meta.start, -1) });
  nextBtn.onclick = () => setFilters({ period: meta.period_type, date: addDays(meta.end, 1) });

  document.getElementById("filter-latest").onclick = () => setFilters({ period: meta.period_type, date: null });

  document.getElementById("filter-refresh").onclick = handleRefreshClick;

  document.getElementById("export-docx").onclick = () => {
    window.location.href = `/api/export/docx?period=${meta.period_type}&date=${meta.start}`;
  };
  document.getElementById("export-xlsx").onclick = () => {
    window.location.href = `/api/export/xlsx?period=${meta.period_type}&date=${meta.start}`;
  };
}

async function handleRefreshClick() {
  const btn = document.getElementById("filter-refresh");
  const icon = document.getElementById("filter-refresh-icon");
  btn.disabled = true;
  icon.classList.add("spinning");
  try {
    await fetch("/api/refresh", { method: "POST" });
  } catch (err) {
    // Ignore - still try to reload with whatever the server has.
  }
  await fetchAndRender();
  btn.disabled = false;
  icon.classList.remove("spinning");
}

async function fetchAndRender() {
  const loading = document.getElementById("loading");
  const errorEl = document.getElementById("error");
  const report = document.getElementById("report");

  try {
    const params = new URLSearchParams(window.location.search);
    const res = await fetch(`/api/report?${params.toString()}`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || `Request failed (${res.status})`);
    }
    const data = await res.json();

    renderBanner(data.meta);
    initFilterBar(data.meta);
    renderKpiCards("kpi-strip", data.kpi_strip);
    renderContext(data.context_note);
    renderExecSummary(data.exec_summary);
    renderCustomerMetrics(data.customer_metrics);
    renderStorePerformance(data.store_performance);
    renderGenderPerformance(data.gender_performance);
    renderTraffic(data.traffic);
    renderRevenueAnalysis(data.revenue_analysis);
    renderDataQuality(data.data_quality);
    renderFeedback(data.feedback);
    renderPriorities(data.priorities, data.meta.period_type);

    loading.hidden = true;
    errorEl.hidden = true;
    report.hidden = false;
  } catch (err) {
    loading.hidden = true;
    errorEl.hidden = false;
    errorEl.textContent = `Failed to load report: ${err.message}`;
  }
}

window.addEventListener("popstate", () => fetchAndRender());

fetchAndRender();
