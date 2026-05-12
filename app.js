const money = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});
const percent = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});
const compactMoney = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  notation: "compact",
});
const chartViewBox = {
  width: 1100,
  height: 620,
  left: 80,
  right: 40,
  top: 72,
  bottom: 115,
};
const state = {
  manifest: null,
  selectedScale: "linear",
  selectedScenario: "macro_all",
  summaries: {},
  forecasts: {},
  historyRows: [],
  hoverPoints: [],
};
const covariateLabels = {
  m2_global_supply_usd: "Global M2 Supply",
  m2_growth_yoy_pct: "M2 Growth YoY",
  g4_global_liquidity_usd: "G4 Global Liquidity",
  fed_net_liquidity_usd: "Fed Net Liquidity",
  dxy_inverse: "DXY inverse",
  fear_greed_index: "Fear & Greed",
  usdt_supply_net_change_usd: "USDT net supply change",
  usdt_supply_mint_proxy_usd: "USDT mint proxy",
  usdt_supply_burn_proxy_usd: "USDT burn proxy",
};

function byId(id) {
  return document.getElementById(id);
}

function toUtcDate(value) {
  const text = String(value).trim().replace(" ", "T");
  if (/([zZ]|[+-]\d{2}:?\d{2})$/.test(text)) {
    return new Date(text);
  }
  return new Date(`${text}Z`);
}

function formatDate(value) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  }).format(toUtcDate(value));
}

function formatUsdTrillions(value) {
  if (!Number.isFinite(Number(value))) return "-";
  return `$${money.format(Number(value) / 1_000_000_000_000)}T`;
}

function formatUsd(value) {
  if (!Number.isFinite(Number(value))) return "-";
  return `$${money.format(Number(value))}`;
}

function cleanSignedZero(value) {
  const numericValue = Number(value);
  return Object.is(numericValue, -0) ? 0 : numericValue;
}

function formatUsdCompact(value) {
  const numericValue = cleanSignedZero(value);
  if (!Number.isFinite(numericValue)) return "-";
  return `$${compactMoney.format(numericValue)}`;
}

function formatUsdDelta(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return "-";
  const sign = numericValue > 0 ? "+" : numericValue < 0 ? "-" : "";
  return `${sign}$${money.format(Math.abs(numericValue))}`;
}

function formatUsdCompactDelta(value) {
  const numericValue = cleanSignedZero(value);
  if (!Number.isFinite(numericValue)) return "-";
  const sign = numericValue > 0 ? "+" : numericValue < 0 ? "-" : "";
  return `${sign}$${compactMoney.format(Math.abs(numericValue))}`;
}

function setDeltaText(element, value) {
  element.textContent = formatUsdDelta(value);
  element.classList.toggle("delta-positive", Number(value) > 0);
  element.classList.toggle("delta-negative", Number(value) < 0);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function covariateLabel(column) {
  return covariateLabels[column] || column;
}

function covariateList(columns) {
  return columns.length ? columns.map(covariateLabel).join(", ") : "BTC close price only";
}

function latestMacroValue(summary, column) {
  return summary?.macro_latest_values?.[column] ?? summary?.[`${column}_last`];
}

function parseCsv(csv) {
  const [headerLine, ...lines] = csv.trim().split(/\r?\n/);
  const headers = headerLine.split(",");
  return lines.map((line) => {
    const values = line.split(",");
    return Object.fromEntries(headers.map((header, index) => [header, values[index]]));
  });
}

async function loadJson(path, label) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Could not load ${label}: ${response.status}`);
  }
  return response.json();
}

async function loadCsv(path, label) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Could not load ${label}: ${response.status}`);
  }
  return parseCsv(await response.text());
}

async function loadHistoryRows() {
  const response = await fetch("/data/latest/history_tail.csv");
  if (!response.ok) {
    return [];
  }
  return parseCsv(await response.text());
}

async function getScenarioSummary(key) {
  if (!state.summaries[key]) {
    const scenario = state.manifest.scenarios[key];
    state.summaries[key] = await loadJson(scenario.summary, `${scenario.label} summary`);
  }
  return state.summaries[key];
}

async function getScenarioForecast(key) {
  if (!state.forecasts[key]) {
    const scenario = state.manifest.scenarios[key];
    state.forecasts[key] = await loadCsv(scenario.forecast, `${scenario.label} forecast`);
  }
  return state.forecasts[key];
}

function scenarioKeyFromControls() {
  const covariates = [...(state.manifest.coreCovariates || [])];
  if (byId("toggleM2Supply").checked) covariates.push("m2_global_supply_usd");
  if (byId("toggleM2Growth").checked) covariates.push("m2_growth_yoy_pct");
  const wanted = covariates.join("|");
  return Object.entries(state.manifest.scenarios).find(([, scenario]) => scenario.covariates.join("|") === wanted)?.[0];
}

function syncCovariateControls(scenario) {
  byId("toggleM2Supply").checked = scenario.covariates.includes("m2_global_supply_usd");
  byId("toggleM2Growth").checked = scenario.covariates.includes("m2_growth_yoy_pct");
}

function renderSummary(summary, scenario) {
  const baseline = state.summaries[state.manifest.baseline];
  const fullMacro = state.summaries[state.manifest.default];
  const macroSummary = fullMacro || summary;

  byId("model").textContent = summary.model;
  byId("generated").textContent = `Generated ${formatDate(summary.generated_at)}`;
  byId("lastObserved").textContent = formatUsd(summary.last_observed_close);
  byId("lastPoint").textContent = formatUsd(summary.last_point);
  byId("range").textContent = `${formatUsd(summary.last_low)} - ${formatUsd(summary.last_high)}`;
  byId("window").textContent = `${formatDate(summary.first_timestamp)} - ${formatDate(summary.last_timestamp)}`;
  byId("m2Supply").textContent = formatUsdTrillions(latestMacroValue(macroSummary, "m2_global_supply_usd"));
  byId("m2Growth").textContent = Number.isFinite(Number(latestMacroValue(macroSummary, "m2_growth_yoy_pct")))
    ? `${percent.format(latestMacroValue(macroSummary, "m2_growth_yoy_pct"))}%`
    : "-";
  byId("g4Liquidity").textContent = formatUsdTrillions(latestMacroValue(macroSummary, "g4_global_liquidity_usd"));
  byId("fedLiquidity").textContent = formatUsdTrillions(latestMacroValue(macroSummary, "fed_net_liquidity_usd"));
  byId("dxyInverse").textContent = Number.isFinite(Number(latestMacroValue(macroSummary, "dxy_inverse")))
    ? Number(latestMacroValue(macroSummary, "dxy_inverse")).toFixed(4)
    : "-";
  byId("fearGreed").textContent = Number.isFinite(Number(latestMacroValue(macroSummary, "fear_greed_index")))
    ? Number(latestMacroValue(macroSummary, "fear_greed_index")).toFixed(0)
    : "-";
  byId("usdtNet").textContent = formatUsdCompactDelta(latestMacroValue(macroSummary, "usdt_supply_net_change_usd"));
  byId("usdtMintBurn").textContent = `${formatUsdCompact(latestMacroValue(macroSummary, "usdt_supply_mint_proxy_usd"))} / ${formatUsdCompact(latestMacroValue(macroSummary, "usdt_supply_burn_proxy_usd"))}`;
  byId("coreInputs").textContent = covariateList(state.manifest.coreCovariates || []);
  byId("scenarioName").textContent = scenario.label;
  setDeltaText(byId("deltaBaseline"), Number(summary.last_point) - Number(baseline.last_point));
  setDeltaText(byId("deltaFull"), Number(summary.last_point) - Number(fullMacro.last_point));

  const activeInputs = scenario.covariates.length ? scenario.covariates : state.manifest.coreCovariates || [];
  const sourceLinks = Object.entries(macroSummary.macro_sources || {})
    .filter(([column]) => activeInputs.includes(column))
    .map(([, url]) => url)
    .filter((url, index, urls) => urls.indexOf(url) === index)
    .map((url) => `<a href="${escapeHtml(url)}">${escapeHtml(new URL(url).hostname || url)}</a>`)
    .join(", ");
  const sourceSentence = sourceLinks ? ` Sources: ${sourceLinks}.` : "";
  byId("macroSource").innerHTML = scenario.covariates.length
    ? `Active Chronos input includes <strong>${escapeHtml(covariateList(scenario.covariates))}</strong>. Model-aligned macro point: ${formatDate(macroSummary.macro_aligned_end || macroSummary.history_end || macroSummary.macro_last_timestamp)}.${sourceSentence}`
    : `Active Chronos input uses BTC close prices only. Model-aligned macro point for comparison: ${formatDate(macroSummary.macro_aligned_end || macroSummary.history_end || macroSummary.macro_last_timestamp)}.${sourceSentence}`;
}

function renderForecastRows(rows) {
  const body = byId("forecastRows");
  const lastRows = rows.slice(-10);
  body.innerHTML = lastRows
    .map(
      (row) => `
        <tr>
          <td>${formatDate(row.timestamp)}</td>
          <td>${formatUsd(row.predictions)}</td>
          <td>${formatUsd(row["0.1"])}</td>
          <td>${formatUsd(row["0.9"])}</td>
        </tr>
      `,
    )
    .join("");
}

function renderScenarioRows() {
  const body = byId("scenarioRows");
  const baseline = state.summaries[state.manifest.baseline];
  body.innerHTML = Object.entries(state.manifest.scenarios)
    .map(([key, scenario]) => {
      const summary = state.summaries[key];
      const delta = Number(summary.last_point) - Number(baseline.last_point);
      const selected = key === state.selectedScenario ? ' class="is-selected"' : "";
      return `
        <tr${selected}>
          <td>${scenario.label}</td>
          <td>${formatUsd(summary.last_point)}</td>
          <td>${formatUsdDelta(delta)}</td>
          <td>${formatUsd(summary.last_low)} - ${formatUsd(summary.last_high)}</td>
          <td>${covariateList(scenario.covariates)}</td>
        </tr>
      `;
    })
    .join("");
}

function chartPoint(timestamp, value, kind, low, high) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return null;
  return {
    timestamp,
    time: toUtcDate(timestamp).getTime(),
    value: numericValue,
    low: Number(low),
    high: Number(high),
    kind,
  };
}

function updateHoverPoints(forecastRows) {
  state.hoverPoints = [
    ...state.historyRows.map((row) => chartPoint(row.timestamp, row.close, "History")),
    ...forecastRows.map((row) =>
      chartPoint(row.timestamp, row.predictions ?? row["0.5"], "Forecast", row["0.1"], row["0.9"]),
    ),
  ]
    .filter(Boolean)
    .sort((a, b) => a.time - b.time);
}

function tooltipHtml(point) {
  const range =
    Number.isFinite(point.low) && Number.isFinite(point.high)
      ? `<span>10-90%: ${formatUsd(point.low)} - ${formatUsd(point.high)}</span>`
      : "";
  return `
    <strong>${point.kind} · ${formatDate(point.timestamp)}</strong>
    <span>Price: ${formatUsd(point.value)}</span>
    ${range}
  `;
}

function hideChartReadout() {
  byId("chartCrosshair").hidden = true;
  byId("chartTooltip").hidden = true;
}

function setupChartHover() {
  const chart = byId("forecastChart");
  const image = byId("forecastChartImage");
  const crosshair = byId("chartCrosshair");
  const tooltip = byId("chartTooltip");
  if (!chart || !image || !crosshair || !tooltip) return;

  chart.addEventListener("pointermove", (event) => {
    const points = state.hoverPoints;
    if (!points.length) return;

    const firstTime = points[0].time;
    const lastTime = points[points.length - 1].time;
    const totalTime = Math.max(lastTime - firstTime, 1);
    const plotWidth = chartViewBox.width - chartViewBox.left - chartViewBox.right;
    const imageRect = image.getBoundingClientRect();
    const chartRect = chart.getBoundingClientRect();
    if (!imageRect.width) return;

    const localSvgX = ((event.clientX - imageRect.left) / imageRect.width) * chartViewBox.width;
    const clampedSvgX = Math.min(
      chartViewBox.width - chartViewBox.right,
      Math.max(chartViewBox.left, localSvgX),
    );
    const targetTime = firstTime + ((clampedSvgX - chartViewBox.left) / plotWidth) * totalTime;
    let point = points[0];
    let bestDistance = Math.abs(points[0].time - targetTime);
    for (const candidate of points) {
      const distance = Math.abs(candidate.time - targetTime);
      if (distance < bestDistance) {
        point = candidate;
        bestDistance = distance;
      }
    }

    const xSvg = chartViewBox.left + ((point.time - firstTime) / totalTime) * plotWidth;
    const xPixel = imageRect.left - chartRect.left + (xSvg / chartViewBox.width) * imageRect.width;
    crosshair.style.left = `${xPixel}px`;
    crosshair.hidden = false;

    tooltip.innerHTML = tooltipHtml(point);
    tooltip.hidden = false;
    const tooltipWidth = tooltip.offsetWidth || 220;
    const tooltipLeft = Math.min(
      Math.max(xPixel - tooltipWidth / 2, 8),
      Math.max(8, chartRect.width - tooltipWidth - 8),
    );
    tooltip.style.left = `${tooltipLeft}px`;
    tooltip.style.top = `${(chartViewBox.top / chartViewBox.height) * imageRect.height + 10}px`;
  });

  chart.addEventListener("pointerleave", hideChartReadout);
  chart.addEventListener("pointercancel", hideChartReadout);
  window.addEventListener("resize", hideChartReadout);
}

function updateChartImage() {
  const scenario = state.manifest.scenarios[state.selectedScenario];
  const image = byId("forecastChartImage");
  const source = state.selectedScale === "log" ? scenario.logSvg : scenario.svg;
  image.src = source;
  image.alt =
    state.selectedScale === "log"
      ? `${scenario.label} BTCUSDT forecast on a logarithmic y-axis`
      : `${scenario.label} BTCUSDT forecast on a linear y-axis`;
  hideChartReadout();
}

function setupScaleToggle() {
  const buttons = [...document.querySelectorAll("[data-chart-scale]")];
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedScale = button.dataset.chartScale;
      buttons.forEach((item) => {
        const isActive = item === button;
        item.classList.toggle("is-active", isActive);
        item.setAttribute("aria-pressed", String(isActive));
      });
      updateChartImage();
    });
  });
}

function setupCovariateToggles() {
  const controls = [byId("toggleM2Supply"), byId("toggleM2Growth")];
  controls.forEach((control) => {
    control.addEventListener("change", () => {
      const key = scenarioKeyFromControls();
      if (key) selectScenario(key);
    });
  });
}

async function selectScenario(key) {
  const scenario = state.manifest.scenarios[key];
  if (!scenario) return;

  state.selectedScenario = key;
  syncCovariateControls(scenario);
  const [summary, rows] = await Promise.all([getScenarioSummary(key), getScenarioForecast(key)]);
  renderSummary(summary, scenario);
  renderForecastRows(rows);
  renderScenarioRows();
  updateHoverPoints(rows);
  updateChartImage();
}

async function init() {
  try {
    const [manifest, historyRows] = await Promise.all([loadJson("/data/latest/scenarios.json", "scenario manifest"), loadHistoryRows()]);
    state.manifest = manifest;
    state.historyRows = historyRows;
    await Promise.all(Object.keys(manifest.scenarios).map((key) => getScenarioSummary(key)));
    setupChartHover();
    setupScaleToggle();
    setupCovariateToggles();
    await selectScenario(manifest.default);
  } catch (error) {
    byId("forecastRows").innerHTML = `<tr><td colspan="4">${error.message}</td></tr>`;
    byId("scenarioRows").innerHTML = `<tr><td colspan="5">${error.message}</td></tr>`;
  }
}

init();
