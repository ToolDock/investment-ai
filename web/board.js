/* 今日の米国市場 ── market.json を読んでページを組み立てる。
 *
 * チャートは build_static.py が Plotly の Figure をそのままJSONにしたもの。
 * 触るとしたら applyChartTheme()（色・フォント）と、
 * 各 render〜()（文言・並び）くらいで足りるようにしてある。
 */
(function () {
  "use strict";

  var DATA_URL = "./market.json";
  var PLOT_CONFIG = { displayModeBar: false, responsive: true, locale: "ja" };

  function cssVar(name, fallback) {
    var value = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (value || "").trim() || fallback;
  }

  /* Plotlyは図の中に色を持つので、CSS変数から文字色だけ流し込む */
  function applyChartTheme(figure) {
    var color = cssVar("--chart-font-color", "#3d4348");
    figure.layout = figure.layout || {};
    figure.layout.font = Object.assign({}, figure.layout.font, { color: color });
    figure.layout.autosize = true;
    delete figure.layout.width;
    delete figure.layout.height;   /* 高さはCSS側（.tile__chart など）で決める */
    return figure;
  }

  /* 入れ子のレイアウトに置かれても崩れないよう、器のサイズ変化に追従させる */
  var observer = window.ResizeObserver ? new ResizeObserver(function (entries) {
    entries.forEach(function (entry) { Plotly.Plots.resize(entry.target); });
  }) : null;

  function plot(elementId, figure) {
    var el = typeof elementId === "string" ? document.getElementById(elementId) : elementId;
    if (!el || !figure) { return; }
    applyChartTheme(figure);
    Plotly.newPlot(el, figure.data, figure.layout, PLOT_CONFIG).then(function () {
      if (observer) { observer.observe(el); }
    });
  }

  function directionClass(direction) {
    return direction > 0 ? "up" : (direction < 0 ? "down" : "flat");
  }

  function setText(root, selector, text) {
    var el = root.querySelector(selector);
    if (el) { el.textContent = text == null ? "" : text; }
  }

  /* data-bind="a.b" の要素にまとめて値を入れる */
  function bind(scope, path, value) {
    var nodes = document.querySelectorAll('[data-bind="' + path + '"]');
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].textContent = value == null ? "" : value;
    }
  }

  /* ── 1・2段目：タイル ─────────────────────── */
  function renderRows(rows, figures) {
    var host = document.getElementById("rows");
    var rowTpl = document.getElementById("tpl-row");
    var tileTpl = document.getElementById("tpl-tile");
    var pending = [];

    rows.forEach(function (row) {
      var section = rowTpl.content.cloneNode(true);
      setText(section, ".row__title", row.title);
      var tileHost = section.querySelector(".row__tiles");

      row.tiles.forEach(function (tile) {
        var node = tileTpl.content.cloneNode(true);
        var article = node.querySelector(".tile");
        article.dataset.symbol = tile.symbol;
        article.dataset.direction = String(tile.direction);
        setText(node, ".tile__label", tile.label);
        setText(node, ".tile__price", tile.price_text);
        setText(node, ".tile__change", tile.arrow + " " + tile.change_text);
        setText(node, ".tile__session", tile.session + " のセッション");

        var chart = node.querySelector(".tile__chart");
        chart.id = "chart-tile-" + tile.slug;
        pending.push([chart.id, figures.tiles[tile.symbol]]);
        tileHost.appendChild(node);
      });

      host.appendChild(section);
    });

    pending.forEach(function (item) { plot(item[0], item[1]); });
  }

  /* ── 3段目：基準価額 ─────────────────────── */
  function renderFund(fund, figure) {
    var section = document.getElementById("fund");
    if (!fund) { section.hidden = true; return; }

    bind(section, "fund.nav_text", fund.nav_text);
    bind(section, "fund.date_text", fund.date_text);
    bind(section, "fund.start_date_text", fund.start_date_text);
    bind(section, "fund.change_line", fund.arrow + " " + fund.change_text);
    bind(section, "fund.ytd_text", signed(fund.ytd_pct) + "%");
    bind(section, "fund.from_peak_text", signed(fund.from_peak_pct) + "%");
    bind(section, "fund.peak_text", Math.round(fund.peak).toLocaleString("ja-JP"));

    colorize(section.querySelector('[data-bind="fund.change_line"]'), fund.direction);
    colorize(section.querySelector('[data-bind="fund.ytd_text"]'), sign(fund.ytd_pct));
    plot("chart-nav", figure);
  }

  function sign(value) { return value > 0 ? 1 : (value < 0 ? -1 : 0); }

  function signed(value) {
    return (value > 0 ? "+" : "") + value.toFixed(2);
  }

  function colorize(el, direction) {
    if (!el) { return; }
    el.classList.remove("up", "down", "flat");
    el.classList.add(directionClass(direction));
  }

  /* ── 4段目・5段目 ────────────────────────── */
  function renderDrawdown(drawdown, figure) {
    bind(document, "drawdown.title", drawdown.title);
    bind(document, "drawdown.note", drawdown.note);
    plot("chart-drawdown", figure);
  }

  function renderFearGreed(fg, figure) {
    var card = document.querySelector(".meter--fg");
    if (!fg) { card.hidden = true; return; }
    bind(document, "fear_greed.note", fg.note);

    var host = document.getElementById("fg-history");
    host.innerHTML = "";
    fg.history.forEach(function (item) {
      var wrap = document.createElement("div");
      wrap.className = "meter__history-item";
      var label = document.createElement("span");
      label.className = "meter__history-label";
      label.textContent = item.label;
      var value = document.createElement("span");
      value.className = "meter__history-value";
      value.textContent = item.value == null ? "—" : Math.round(item.value);
      wrap.appendChild(label);
      wrap.appendChild(value);
      host.appendChild(wrap);
    });

    plot("chart-fg", figure);
  }

  function renderVix(vix, figure) {
    var card = document.querySelector(".meter--vix");
    if (!vix) { card.hidden = true; return; }
    bind(document, "vix.note", vix.note);
    plot("chart-vix", figure);
  }

  function renderFooter(sources, disclaimer) {
    var host = document.getElementById("sources");
    host.innerHTML = "";
    sources.forEach(function (text) {
      var li = document.createElement("li");
      li.textContent = text;
      host.appendChild(li);
    });
    bind(document, "disclaimer", disclaimer);
  }

  /* ── 起動 ───────────────────────────────── */
  function render(data) {
    document.title = data.title;
    bind(document, "title", data.title);
    bind(document, "generated_at_text", data.generated_at_text);
    bind(document, "fund_chart_title", data.fund_chart_title);
    var time = document.querySelector("time[data-bind]");
    if (time) { time.dateTime = data.generated_at; }

    renderRows(data.rows, data.figures);
    renderFund(data.fund, data.figures.nav);
    renderDrawdown(data.drawdown, data.figures.drawdown);
    renderFearGreed(data.fear_greed, data.figures.fear_greed);
    renderVix(data.vix, data.figures.vix);
    renderFooter(data.sources, data.disclaimer);
  }

  function fail(message) {
    var el = document.getElementById("error");
    el.hidden = false;
    el.textContent = "データを読み込めませんでした: " + message;
  }

  fetch(DATA_URL, { cache: "no-cache" })
    .then(function (res) {
      if (!res.ok) { throw new Error(res.status + " " + res.statusText); }
      return res.json();
    })
    .then(render)
    .catch(function (e) { fail(e.message); });

  /* OSのテーマが切り替わったら、チャートの文字色も追従させる */
  if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
      var color = cssVar("--chart-font-color", "#3d4348");
      document.querySelectorAll(".js-plotly-plot").forEach(function (el) {
        Plotly.relayout(el, { "font.color": color });
      });
    });
  }
})();
