const lastUpdatedElement = document.querySelector("#last-updated");
const assetCountElement = document.querySelector("#asset-count");
const positiveCountElement = document.querySelector("#positive-count");
const headlineCountElement = document.querySelector("#headline-count");
const statusElement = document.querySelector("#status");
const recommendationStatusElement = document.querySelector("#recommendations-status");
const searchInput = document.querySelector("#asset-search");
const marketFilters = document.querySelector("#market-filters");
const assetGrid = document.querySelector("#asset-grid");
const recommendationSummary = document.querySelector("#recommendation-summary");
const recommendationList = document.querySelector("#recommendation-list");
const assetTemplate = document.querySelector("#asset-template");
const recommendationTemplate = document.querySelector("#recommendation-template");
const dashboardView = document.querySelector("#dashboard-view");
const recommendationsView = document.querySelector("#recommendations-view");
const dashboardTab = document.querySelector("#tab-dashboard");
const recommendationsTab = document.querySelector("#tab-recommendations");

const modalShell = document.querySelector("#detail-modal");
const modalBackdrop = document.querySelector("#modal-backdrop");
const modalCloseButton = document.querySelector("#modal-close");
const modalType = document.querySelector("#modal-type");
const modalTicker = document.querySelector("#modal-ticker");
const modalTitle = document.querySelector("#modal-title");
const modalSummary = document.querySelector("#modal-summary");
const modalRecommendation = document.querySelector("#modal-recommendation");
const modalConfidence = document.querySelector("#modal-confidence");
const modalTrends = document.querySelector("#modal-trends");
const modalTechnical = document.querySelector("#modal-technical");
const modalBullishScenario = document.querySelector("#modal-bullish-scenario");
const modalBearishScenario = document.querySelector("#modal-bearish-scenario");
const modalBreakdown = document.querySelector("#modal-breakdown");
const modalNews = document.querySelector("#modal-news");

const state = {
  assets: [],
  recommendations: { ranked: [], summary: {} },
  filter: "All",
  search: "",
  activeTab: "dashboard",
};

function formatDate(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Live refresh unavailable";
  }

  return parsed.toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatPrice(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: value >= 1000 ? 0 : value >= 100 ? 2 : 4,
  }).format(value);
}

function decorateChange(element, value) {
  element.textContent = formatPercent(value);
  element.classList.toggle("is-positive", Number(value) > 0);
  element.classList.toggle("is-negative", Number(value) < 0);
}

function createChip(label, active, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `filter-chip${active ? " is-active" : ""}`;
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function renderFilters(assets) {
  const groups = ["All", ...new Set(assets.map((asset) => asset.type))];
  marketFilters.replaceChildren(
    ...groups.map((label) =>
      createChip(label, label === state.filter, () => {
        state.filter = label;
        renderFilters(state.assets);
        renderAssets();
        renderRecommendations();
      })
    )
  );
}

function matchesSearch(asset) {
  if (!state.search) {
    return true;
  }

  const recommendation = asset.analysis?.recommendation || {};
  const haystack = [
    asset.name,
    asset.ticker,
    asset.type,
    asset.summary,
    recommendation.label,
    recommendation.timeframe,
    asset.analysis?.momentumSummary,
    asset.analysis?.supportZone,
    asset.analysis?.resistanceZone,
    ...(recommendation.keyReasons || []),
    ...(recommendation.risks || []),
    ...(asset.headlines || []).map((headline) => headline.title),
  ]
    .join(" ")
    .toLowerCase();

  return haystack.includes(state.search);
}

function getVisibleAssets() {
  return state.assets.filter((asset) => {
    const typeMatch = state.filter === "All" || asset.type === state.filter;
    return typeMatch && matchesSearch(asset);
  });
}

function getVisibleRecommendations() {
  return state.recommendations.ranked.filter((item) => {
    const typeMatch = state.filter === "All" || item.type === state.filter;
    return typeMatch && matchesSearch(state.assets.find((asset) => asset.ticker === item.ticker));
  });
}

function buildPath(values, width, height, padding) {
  if (!values.length) {
    return null;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = values.length > 1 ? (width - padding * 2) / (values.length - 1) : 0;

  return values
    .map((value, index) => {
      const x = padding + index * step;
      const y = height - padding - ((value - min) / range) * (height - padding * 2);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function buildArea(values, width, height, padding) {
  const line = buildPath(values, width, height, padding);
  if (!line) {
    return null;
  }

  const startX = padding;
  const endX = width - padding;
  const baseline = height - padding;
  return `${line} L ${endX} ${baseline} L ${startX} ${baseline} Z`;
}

function createSparkline(series, positive) {
  const values = (series || []).map((point) => Number(point.close)).filter(Number.isFinite);
  const wrapper = document.createElement("div");

  if (!values.length) {
    wrapper.innerHTML = "<p class='meta-copy'>Chart unavailable.</p>";
    return wrapper;
  }

  const width = 320;
  const height = 132;
  const padding = 10;
  const color = positive ? "#0b8a5b" : "#b44646";
  const area = buildArea(values, width, height, padding);
  const path = buildPath(values, width, height, padding);
  const lastValue = values[values.length - 1];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const lastX = values.length > 1 ? width - padding : width / 2;
  const lastY = height - padding - ((lastValue - min) / range) * (height - padding * 2);

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("class", "chart-svg");

  [0.2, 0.5, 0.8].forEach((ratio) => {
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    const y = (height - padding * 2) * ratio + padding;
    line.setAttribute("x1", String(padding));
    line.setAttribute("x2", String(width - padding));
    line.setAttribute("y1", y.toFixed(2));
    line.setAttribute("y2", y.toFixed(2));
    line.setAttribute("class", "chart-gridline");
    svg.append(line);
  });

  const areaPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
  areaPath.setAttribute("d", area);
  areaPath.setAttribute("class", "chart-area");
  areaPath.setAttribute("fill", color);
  svg.append(areaPath);

  const linePath = document.createElementNS("http://www.w3.org/2000/svg", "path");
  linePath.setAttribute("d", path);
  linePath.setAttribute("class", "chart-line");
  linePath.setAttribute("stroke", color);
  svg.append(linePath);

  const point = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  point.setAttribute("cx", lastX.toFixed(2));
  point.setAttribute("cy", lastY.toFixed(2));
  point.setAttribute("r", "4.5");
  point.setAttribute("class", "chart-point");
  point.setAttribute("fill", color);
  svg.append(point);

  wrapper.append(svg);
  return wrapper;
}

function createList(items) {
  const fragment = document.createDocumentFragment();
  items.forEach((item) => {
    const entry = document.createElement("li");
    entry.textContent = item;
    fragment.append(entry);
  });
  return fragment;
}

function createNewsList(headlines) {
  const fragment = document.createDocumentFragment();
  headlines.forEach((headline) => {
    const item = document.createElement("article");
    item.className = "news-item";
    item.innerHTML = `
      <p class="news-item-meta">${headline.source} • ${headline.publishedRelative}</p>
      <a class="news-item-copy" href="${headline.link}" target="_blank" rel="noreferrer">${headline.title}</a>
    `;
    fragment.append(item);
  });
  return fragment;
}

function createAnalysisChip(label, value, extraClass = "") {
  const chip = document.createElement("span");
  chip.className = `analysis-chip${extraClass ? ` ${extraClass}` : ""}`;
  chip.textContent = `${label}: ${value}`;
  return chip;
}

function buildSummaryCardCopy(title, item, extraText) {
  if (item) {
    return {
      heading: `${item.ticker} • ${item.label || item.name}`,
      copy: `Score ${item.score}/100 • Confidence ${item.confidence}/100`,
    };
  }

  if (title === "Overall tone") {
    return {
      heading: extraText,
      copy: "This is the aggregate read across the ranked watchlist.",
    };
  }

  return {
    heading: "Open a ranked card",
    copy: extraText,
  };
}

function createChartPanel(chartView) {
  const section = document.createElement("section");
  section.className = "chart-panel";

  const labelRow = document.createElement("div");
  labelRow.className = "chart-label-row";
  labelRow.innerHTML = `<p>${chartView.title}</p><span>${chartView.label}</span>`;

  const surface = document.createElement("div");
  surface.className = "chart-surface";

  if (chartView.status !== "ok") {
    surface.innerHTML = `<p class="meta-copy">${chartView.message || "Chart unavailable."}</p>`;
  } else {
    surface.replaceChildren(createSparkline(chartView.series, Number(chartView.performancePercent) >= 0));
  }

  section.append(labelRow, surface);
  return section;
}

function createBreakdownCards(items) {
  return items.map((item) => {
    const card = document.createElement("article");
    card.className = "breakdown-card";
    card.innerHTML = `
      <p class="signal-label">${item.name}</p>
      <strong>${item.score}/${item.max}</strong>
      <p>${item.detail}</p>
    `;
    return card;
  });
}

function openDetail(asset) {
  const recommendation = asset.analysis.recommendation;
  modalType.textContent = asset.type;
  modalTicker.textContent = asset.ticker;
  modalTitle.textContent = asset.name;
  modalSummary.textContent = asset.summary;
  modalRecommendation.textContent = `${recommendation.label} • ${recommendation.score}/100 • ${recommendation.timeframe}`;
  modalConfidence.textContent = `Confidence ${recommendation.confidence}/100`;

  modalTrends.replaceChildren(
    createAnalysisChip("1D", asset.analysis.trendDirections["1D"]),
    createAnalysisChip("1W", asset.analysis.trendDirections["1W"]),
    createAnalysisChip("1M", asset.analysis.trendDirections["1M"])
  );

  const technicalLines = [
    `Momentum: ${asset.analysis.momentumSummary}`,
    `Support: ${asset.analysis.supportZone}`,
    `Resistance: ${asset.analysis.resistanceZone}`,
    `Volatility: ${asset.analysis.volatilityLevel}${asset.analysis.volatilityValue ? ` (${asset.analysis.volatilityValue})` : ""}`,
    `Breakout / breakdown: ${asset.analysis.breakoutBreakdownRisk} — ${asset.analysis.breakoutBreakdownDetail}`,
    `Trend quality: ${asset.analysis.trendQuality}`,
    `High / low position: ${asset.analysis.highLowPosition}`,
    `Volume: ${asset.analysis.volumeSummary}`,
    `News alignment: ${asset.analysis.priceNewsAlignment}`,
  ];

  modalTechnical.replaceChildren(
    ...technicalLines.map((line) => {
      const paragraph = document.createElement("p");
      paragraph.textContent = line;
      return paragraph;
    })
  );

  modalBullishScenario.textContent = asset.analysis.bullishScenario;
  modalBearishScenario.textContent = asset.analysis.bearishScenario;
  modalBreakdown.replaceChildren(...createBreakdownCards(asset.analysis.scoringBreakdown));
  modalNews.replaceChildren(createNewsList(asset.headlines));

  modalShell.hidden = false;
  document.body.style.overflow = "hidden";
  modalCloseButton.focus();
}

function closeDetail() {
  modalShell.hidden = true;
  document.body.style.overflow = "";
}

function createAssetCard(asset) {
  const fragment = assetTemplate.content.cloneNode(true);
  const chartGrid = fragment.querySelector('[data-field="chartGrid"]');
  const assetNotice = fragment.querySelector('[data-field="assetNotice"]');
  const analysisStrip = fragment.querySelector('[data-field="analysisStrip"]');

  fragment.querySelector('[data-field="type"]').textContent = asset.type;
  fragment.querySelector('[data-field="ticker"]').textContent = asset.ticker;
  fragment.querySelector('[data-field="name"]').textContent = asset.name;
  fragment.querySelector('[data-field="price"]').textContent = formatPrice(asset.currentPrice);
  fragment.querySelector('[data-field="priceMeta"]').textContent = asset.priceContext || "Latest available market snapshot";
  fragment.querySelector('[data-field="summary"]').textContent = asset.summary;
  fragment.querySelector('[data-field="newsSourceCount"]').textContent = `${asset.headlines.length} headlines`;
  fragment.querySelector('[data-field="recommendationLabel"]').textContent = asset.analysis.recommendation.label;

  decorateChange(fragment.querySelector('[data-field="dailyChange"]'), asset.dailyChangePercent);
  decorateChange(fragment.querySelector('[data-field="weeklyChange"]'), asset.weeklyChangePercent);
  decorateChange(fragment.querySelector('[data-field="monthlyChange"]'), asset.monthlyChangePercent);

  analysisStrip.replaceChildren(
    createAnalysisChip("1D", asset.analysis.trendDirections["1D"]),
    createAnalysisChip("1W", asset.analysis.trendDirections["1W"]),
    createAnalysisChip("1M", asset.analysis.trendDirections["1M"]),
    createAnalysisChip("Momentum", asset.analysis.momentumSummary),
    createAnalysisChip("Volatility", asset.analysis.volatilityLevel)
  );

  chartGrid.replaceChildren(...asset.chartViews.map(createChartPanel));

  if (asset.notice) {
    assetNotice.hidden = false;
    assetNotice.textContent = asset.notice;
  }

  fragment.querySelector('[data-field="bullishSignals"]').replaceChildren(createList(asset.bullishSignals));
  fragment.querySelector('[data-field="bearishSignals"]').replaceChildren(createList(asset.bearishSignals));
  fragment.querySelector('[data-field="newsList"]').replaceChildren(createNewsList(asset.headlines));
  fragment.querySelector('[data-field="openDetail"]').addEventListener("click", () => openDetail(asset));

  return fragment;
}

function createSummaryCard(title, item, extraText) {
  const copy = buildSummaryCardCopy(title, item, extraText);
  const card = document.createElement("article");
  card.className = "summary-card card";
  card.innerHTML = `
    <p class="signal-label">${title}</p>
    <h3>${copy.heading}</h3>
    <p>${copy.copy}</p>
  `;
  return card;
}

function createRecommendationCard(item) {
  const asset = state.assets.find((entry) => entry.ticker === item.ticker);
  const fragment = recommendationTemplate.content.cloneNode(true);
  const metaStrip = fragment.querySelector('[data-field="metaStrip"]');
  const breakdown = fragment.querySelector('[data-field="breakdown"]');

  fragment.querySelector('[data-field="type"]').textContent = item.type;
  fragment.querySelector('[data-field="ticker"]').textContent = item.ticker;
  fragment.querySelector('[data-field="name"]').textContent = item.name;
  fragment.querySelector('[data-field="score"]').textContent = `${item.score}/100`;
  fragment.querySelector('[data-field="scoreMeta"]').textContent =
    `${item.label} • Confidence ${item.confidence}/100 • ${item.timeframe}`;

  metaStrip.replaceChildren(
    createAnalysisChip("Risk / reward", item.riskRewardScore),
    createAnalysisChip("Support", asset.analysis.supportZone),
    createAnalysisChip("Resistance", asset.analysis.resistanceZone),
    createAnalysisChip("Trend", asset.analysis.trendQuality)
  );

  breakdown.replaceChildren(...createBreakdownCards(item.scoringBreakdown));
  fragment.querySelector('[data-field="keyReasons"]').replaceChildren(createList(item.keyReasons));
  fragment.querySelector('[data-field="risks"]').replaceChildren(createList(item.risks));
  fragment.querySelector('[data-field="strengthen"]').replaceChildren(createList(item.strengthen));
  fragment.querySelector('[data-field="weaken"]').replaceChildren(createList(item.weaken));
  fragment.querySelector('[data-field="openDetail"]').addEventListener("click", () => openDetail(asset));

  return fragment;
}

function renderAssets() {
  const assets = getVisibleAssets();

  if (!assets.length) {
    const empty = document.createElement("article");
    empty.className = "empty-state card";
    empty.innerHTML = "<h3>No matching assets</h3><p>Try a broader search or change the market filter.</p>";
    assetGrid.replaceChildren(empty);
    statusElement.textContent = "No assets matched the current filter.";
    return;
  }

  assetGrid.replaceChildren(...assets.map(createAssetCard));
  statusElement.textContent = `${assets.length} asset${assets.length === 1 ? "" : "s"} shown with charts, technical context, and recent news.`;
}

function renderRecommendations() {
  const ranked = getVisibleRecommendations();
  const summary = state.recommendations.summary;

  if (!ranked.length) {
    const empty = document.createElement("article");
    empty.className = "empty-state card";
    empty.innerHTML = "<h3>No matching recommendations</h3><p>Try a broader search or change the market filter.</p>";
    recommendationList.replaceChildren(empty);
    recommendationSummary.replaceChildren();
    recommendationStatusElement.textContent = "No ranked assets matched the current filter.";
    return;
  }

  recommendationSummary.replaceChildren(
    createSummaryCard("Best setup", summary.bestSetup),
    createSummaryCard("Worst setup", summary.worstSetup),
    createSummaryCard("Best risk / reward", summary.bestRiskReward),
    createSummaryCard("Highest risk", summary.highestRisk),
    createSummaryCard("Strongest crypto", summary.strongestCrypto),
    createSummaryCard("Strongest stock", summary.strongestStock),
    createSummaryCard("Overall tone", null, summary.overallMarketTone),
    createSummaryCard("How to read", null, "Open any ranked card for full technical detail.")
  );

  recommendationList.replaceChildren(...ranked.map(createRecommendationCard));
  recommendationStatusElement.textContent = `${ranked.length} ranked asset${ranked.length === 1 ? "" : "s"} shown from strongest to weakest.`;
}

function setActiveTab(tab) {
  state.activeTab = tab;
  const dashboardActive = tab === "dashboard";
  dashboardView.hidden = !dashboardActive;
  recommendationsView.hidden = dashboardActive;
  dashboardTab.classList.toggle("is-active", dashboardActive);
  recommendationsTab.classList.toggle("is-active", !dashboardActive);
  dashboardTab.setAttribute("aria-selected", String(dashboardActive));
  recommendationsTab.setAttribute("aria-selected", String(!dashboardActive));
}

async function loadDashboard() {
  try {
    const response = await fetch("./api/dashboard");
    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }

    const payload = await response.json();
    state.assets = payload.assets || [];
    state.recommendations = payload.recommendations || { ranked: [], summary: {} };

    const positiveCount = state.assets.filter(
      (asset) => asset.analysis?.recommendation?.score >= 64
    ).length;
    const headlineCount = state.assets.reduce((total, asset) => total + (asset.headlines || []).length, 0);

    lastUpdatedElement.textContent = `Updated ${formatDate(payload.generatedAt)}`;
    assetCountElement.textContent = String(state.assets.length);
    positiveCountElement.textContent = String(positiveCount);
    headlineCountElement.textContent = String(headlineCount);

    renderFilters(state.assets);
    renderAssets();
    renderRecommendations();
  } catch (error) {
    lastUpdatedElement.textContent = "Live refresh failed.";
    assetCountElement.textContent = "0";
    positiveCountElement.textContent = "0";
    headlineCountElement.textContent = "0";
    statusElement.textContent = "Could not load the dashboard data.";
    recommendationStatusElement.textContent = "Could not load the recommendation data.";
    assetGrid.innerHTML =
      "<article class='empty-state card'><h3>Dashboard unavailable</h3><p>Run <code>python3 server.py</code> and refresh the page.</p></article>";
    recommendationList.innerHTML =
      "<article class='empty-state card'><h3>Recommendations unavailable</h3><p>The ranking engine depends on the local API response.</p></article>";
  }
}

searchInput.addEventListener("input", (event) => {
  state.search = event.target.value.trim().toLowerCase();
  renderAssets();
  renderRecommendations();
});

dashboardTab.addEventListener("click", () => setActiveTab("dashboard"));
recommendationsTab.addEventListener("click", () => setActiveTab("recommendations"));
modalCloseButton.addEventListener("click", closeDetail);
modalBackdrop.addEventListener("click", closeDetail);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !modalShell.hidden) {
    closeDetail();
  }
});

setActiveTab("dashboard");

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./service-worker.js").catch(() => {});
  });
}

loadDashboard();
