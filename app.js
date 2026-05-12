const money = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});
const percent = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});
const chartViewBox = {
  width: 1100,
  height: 620,
  left: 80,
  right: 40,
  top: 72,
  bottom: 115,
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

async function loadHistoryRows() {
  const response = await fetch("/data/latest/history_tail.csv");
  if (!response.ok) {
    return [];
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

function tooltipHtml(point) {
  const range =
    Number.isFinite(point.low) && Number.isFinite(point.high)
      ? `<span>10-90%: $${money.format(point.low)} - $${money.format(point.high)}</span>`
      : "";
  return `
    <strong>${point.kind} · ${formatDate(point.timestamp)}</strong>
    <span>Price: $${money.format(point.value)}</span>
    ${range}
  `;
}

function setupChartHover(historyRows, forecastRows) {
  const chart = byId("forecastChart");
  const image = byId("forecastChartImage");
  const crosshair = byId("chartCrosshair");
  const tooltip = byId("chartTooltip");
  if (!chart || !image || !crosshair || !tooltip) return;

  const points = [
    ...historyRows.map((row) => chartPoint(row.timestamp, row.close, "History")),
    ...forecastRows.map((row) =>
      chartPoint(row.timestamp, row.predictions ?? row["0.5"], "Forecast", row["0.1"], row["0.9"]),
    ),
  ]
    .filter(Boolean)
    .sort((a, b) => a.time - b.time);

  if (!points.length) return;

  const firstTime = points[0].time;
  const lastTime = points[points.length - 1].time;
  const totalTime = Math.max(lastTime - firstTime, 1);
  const plotWidth = chartViewBox.width - chartViewBox.left - chartViewBox.right;

  const pointX = (time) => chartViewBox.left + ((time - firstTime) / totalTime) * plotWidth;
  const hide = () => {
    crosshair.hidden = true;
    tooltip.hidden = true;
  };
  const nearestPoint = (targetTime) => {
    let best = points[0];
    let bestDistance = Math.abs(points[0].time - targetTime);
    for (const point of points) {
      const distance = Math.abs(point.time - targetTime);
      if (distance < bestDistance) {
        best = point;
        bestDistance = distance;
      }
    }
    return best;
  };

  chart.addEventListener("pointermove", (event) => {
    const imageRect = image.getBoundingClientRect();
    const chartRect = chart.getBoundingClientRect();
    if (!imageRect.width) return;

    const localSvgX = ((event.clientX - imageRect.left) / imageRect.width) * chartViewBox.width;
    const clampedSvgX = Math.min(
      chartViewBox.width - chartViewBox.right,
      Math.max(chartViewBox.left, localSvgX),
    );
    const targetTime = firstTime + ((clampedSvgX - chartViewBox.left) / plotWidth) * totalTime;
    const point = nearestPoint(targetTime);
    const xSvg = pointX(point.time);
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

  chart.addEventListener("pointerleave", hide);
  chart.addEventListener("pointercancel", hide);
  window.addEventListener("resize", hide);
}

async function init() {
  try {
    const [summary, rows, historyRows] = await Promise.all([loadSummary(), loadForecastRows(), loadHistoryRows()]);
    renderSummary(summary);
    renderForecastRows(rows);
    setupChartHover(historyRows, rows);
  } catch (error) {
    byId("forecastRows").innerHTML = `<tr><td colspan="4">${error.message}</td></tr>`;
  }
}

init();
