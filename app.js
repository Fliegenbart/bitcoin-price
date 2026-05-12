const money = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});
const percent = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});

function byId(id) {
  return document.getElementById(id);
}

function toUtcDate(value) {
  const text = String(value);
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

function parseCsv(csv) {
  const [headerLine, ...lines] = csv.trim().split(/\r?\n/);
  const headers = headerLine.split(",");
  return lines.map((line) => {
    const values = line.split(",");
    return Object.fromEntries(headers.map((header, index) => [header, values[index]]));
  });
}

async function loadSummary() {
  const response = await fetch("/data/latest/summary.json");
  if (!response.ok) {
    throw new Error(`Could not load summary: ${response.status}`);
  }
  return response.json();
}

async function loadForecastRows() {
  const response = await fetch("/data/latest/forecast.csv");
  if (!response.ok) {
    throw new Error(`Could not load forecast CSV: ${response.status}`);
  }
  return parseCsv(await response.text());
}

function renderSummary(summary) {
  byId("model").textContent = summary.model;
  byId("generated").textContent = `Generated ${formatDate(summary.generated_at)}`;
  byId("lastObserved").textContent = `$${money.format(summary.last_observed_close)}`;
  byId("lastPoint").textContent = `$${money.format(summary.last_point)}`;
  byId("range").textContent = `$${money.format(summary.last_low)} - $${money.format(summary.last_high)}`;
  byId("window").textContent = `${formatDate(summary.first_timestamp)} - ${formatDate(summary.last_timestamp)}`;
  byId("m2Supply").textContent = formatUsdTrillions(summary.m2_global_supply_usd_last);
  byId("m2Growth").textContent = Number.isFinite(Number(summary.m2_growth_yoy_pct_last))
    ? `${percent.format(summary.m2_growth_yoy_pct_last)}%`
    : "-";
  byId("macroSource").innerHTML = summary.covariates?.length
    ? `Chronos input now includes <strong>${summary.covariates.join("</strong> and <strong>")}</strong> as past covariates. Latest macro point: ${formatDate(summary.macro_last_timestamp)}. Source: <a href="${summary.macro_source_url}">${summary.macro_source}</a>.`
    : "This run does not include macro covariates.";
}

function renderForecastRows(rows) {
  const body = byId("forecastRows");
  const lastRows = rows.slice(-10);
  body.innerHTML = lastRows
    .map(
      (row) => `
        <tr>
          <td>${formatDate(row.timestamp)}</td>
          <td>$${money.format(Number(row.predictions))}</td>
          <td>$${money.format(Number(row["0.1"]))}</td>
          <td>$${money.format(Number(row["0.9"]))}</td>
        </tr>
      `,
    )
    .join("");
}

async function init() {
  try {
    const [summary, rows] = await Promise.all([loadSummary(), loadForecastRows()]);
    renderSummary(summary);
    renderForecastRows(rows);
  } catch (error) {
    byId("forecastRows").innerHTML = `<tr><td colspan="4">${error.message}</td></tr>`;
  }
}

init();
