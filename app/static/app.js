(() => {
  const form = document.getElementById("search-form");
  const searchBtn = document.getElementById("search-btn");
  const exportBtn = document.getElementById("export-btn");
  const statusEl = document.getElementById("status");
  const tbody = document.getElementById("results-body");
  const resultsCount = document.getElementById("results-count");
  const quotaUsedEl = document.getElementById("quota-used");
  const quotaRemainingEl = document.getElementById("quota-remaining");
  const table = document.getElementById("results-table");
  const daysInput = document.getElementById("published_after_days");
  const requireGateCheckbox = document.getElementById("require_small_or_new");
  const gateHint = document.getElementById("gate-hint");

  const historyBody = document.getElementById("history-body");
  const historyRefreshBtn = document.getElementById("history-refresh-btn");

  const growthModal = document.getElementById("growth-modal");
  const growthCloseBtn = document.getElementById("growth-close-btn");
  const growthTitle = document.getElementById("growth-title");
  const growthChartWrap = document.getElementById("growth-chart-wrap");
  const growthBody = document.getElementById("growth-body");

  let currentResults = [];
  let sortKey = "score";
  let sortDir = -1; // -1 = desc, 1 = asc

  function showStatus(kind, html) {
    statusEl.hidden = false;
    statusEl.className = `status ${kind}`;
    statusEl.innerHTML = html;
  }

  function fmtInt(n) {
    if (n === null || n === undefined) return "—";
    return Number(n).toLocaleString("uk-UA");
  }

  function fmtFloat(n, digits = 1) {
    if (n === null || n === undefined) return "—";
    return Number(n).toLocaleString("uk-UA", { maximumFractionDigits: digits });
  }

  function updateQuotaBadge(used, remaining) {
    if (used !== undefined && used !== null) quotaUsedEl.textContent = fmtInt(used);
    if (remaining !== undefined && remaining !== null) quotaRemainingEl.textContent = fmtInt(remaining);
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleDateString("uk-UA");
    } catch {
      return iso;
    }
  }

  // YouTube інколи віддає назви відео з "сирими" HTML-сутностями в тексті
  // (напр. буквально "Cat&#39;s ..." замість "Cat's ...") — декодуємо перед показом,
  // інакше на сторінці видно технічний код замість символу.
  const _entityDecoder = document.createElement("textarea");
  function decodeEntities(s) {
    if (s === null || s === undefined) return s;
    _entityDecoder.innerHTML = String(s);
    return _entityDecoder.value;
  }

  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  // ---------- Форма: chips для періоду, чекбокс гейта ----------

  document.querySelectorAll(".chip[data-days]").forEach((chip) => {
    chip.addEventListener("click", () => {
      daysInput.value = chip.dataset.days;
      syncActiveChip();
    });
  });

  function syncActiveChip() {
    document.querySelectorAll(".chip[data-days]").forEach((chip) => {
      chip.classList.toggle("active", chip.dataset.days === daysInput.value);
    });
  }
  daysInput.addEventListener("input", syncActiveChip);
  syncActiveChip();

  requireGateCheckbox.addEventListener("change", () => {
    gateHint.style.display = requireGateCheckbox.checked ? "inline" : "none";
  });

  // ---------- Таблиця результатів ----------

  function renderTable() {
    if (!currentResults.length) {
      tbody.innerHTML = `<tr><td colspan="12" class="empty">Нічого не знайдено за цими фільтрами. Спробуй послабити пороги або інші ключові слова.</td></tr>`;
      resultsCount.textContent = "";
      return;
    }

    const sorted = [...currentResults].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "string") return sortDir * av.localeCompare(bv);
      return sortDir * (av - bv);
    });

    tbody.innerHTML = sorted
      .map((c) => {
        const kwPills = c.matched_keywords
          .map((k) => `<span class="kw-pill">${escapeHtml(k)}</span>`)
          .join("");
        const typeBadge =
          c.top_video_is_short === null || c.top_video_is_short === undefined
            ? ""
            : c.top_video_is_short
            ? `<span class="type-badge short">Short</span>`
            : `<span class="type-badge long">Long</span>`;
        const topVideo = c.top_video_url
          ? `${typeBadge}<a href="${c.top_video_url}" target="_blank" rel="noopener">${escapeHtml(decodeEntities(c.top_video_title || "відео"))}</a><br><span class="muted">${fmtInt(c.top_video_views)} переглядів</span>`
          : "—";
        return `
        <tr>
          <td><a href="${c.url}" target="_blank" rel="noopener">${escapeHtml(decodeEntities(c.title))}</a></td>
          <td>${escapeHtml(c.country || "—")}</td>
          <td class="num">${fmtFloat(c.age_months)}</td>
          <td class="num">${fmtInt(c.video_count)}</td>
          <td class="num">${fmtInt(c.subscriber_count)}</td>
          <td class="num">${fmtInt(c.total_view_count)}</td>
          <td class="num">${fmtInt(c.views_per_video)}</td>
          <td class="num">${fmtFloat(c.views_per_subscriber, 2)}</td>
          <td class="num"><span class="badge-score">${fmtFloat(c.score, 2)}</span></td>
          <td>${topVideo}</td>
          <td>${kwPills}</td>
          <td><button type="button" class="icon-btn growth-btn" data-channel-id="${c.channel_id}" data-channel-title="${escapeHtml(decodeEntities(c.title))}">📈</button></td>
        </tr>`;
      })
      .join("");

    resultsCount.textContent = `${currentResults.length} канал(ів)`;

    tbody.querySelectorAll(".growth-btn").forEach((btn) => {
      btn.addEventListener("click", () => openGrowthModal(btn.dataset.channelId, btn.dataset.channelTitle));
    });
  }

  table.querySelectorAll("thead th[data-key]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.key;
      if (sortKey === key) {
        sortDir *= -1;
      } else {
        sortKey = key;
        sortDir = -1;
      }
      renderTable();
    });
  });

  function collectFormData() {
    const fd = new FormData(form);
    const keywords = fd
      .get("keywords")
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);

    const optInt = (name) => {
      const v = fd.get(name);
      return v === "" || v === null ? null : Number(v);
    };

    return {
      keywords,
      region_code: fd.get("region_code"),
      published_after_days: optInt("published_after_days"),
      pages_per_keyword: Number(fd.get("pages_per_keyword")),
      video_type: fd.get("video_type"),
      min_views_per_video: optInt("min_views_per_video"),
      min_video_views: optInt("min_video_views"),
      max_video_count: Number(fd.get("max_video_count")),
      max_channel_age_months: Number(fd.get("max_channel_age_months")),
      require_small_or_new: fd.get("require_small_or_new") === "on",
      min_subscribers: optInt("min_subscribers"),
      max_subscribers: optInt("max_subscribers"),
    };
  }

  function fillForm(params) {
    document.getElementById("keywords").value = (params.keywords || []).join("\n");
    document.getElementById("region_code").value = params.region_code || "US";
    daysInput.value = params.published_after_days ?? 0;
    syncActiveChip();
    document.getElementById("video_type").value = params.video_type || "all";
    document.getElementById("pages_per_keyword").value = params.pages_per_keyword || 1;
    document.getElementById("min_views_per_video").value = params.min_views_per_video ?? "";
    document.getElementById("min_video_views").value = params.min_video_views ?? "";
    document.getElementById("max_video_count").value = params.max_video_count ?? 30;
    document.getElementById("max_channel_age_months").value = params.max_channel_age_months ?? 12;
    document.getElementById("min_subscribers").value = params.min_subscribers ?? "";
    document.getElementById("max_subscribers").value = params.max_subscribers ?? "";
    requireGateCheckbox.checked = params.require_small_or_new !== false;
    requireGateCheckbox.dispatchEvent(new Event("change"));
  }

  async function runSearch(payload) {
    searchBtn.disabled = true;
    searchBtn.textContent = "⏳ Шукаю…";
    showStatus("info", "Звертаюсь до YouTube API, це може зайняти кілька секунд…");

    try {
      const res = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ? JSON.stringify(err.detail) : `HTTP ${res.status}`);
      }

      const data = await res.json();
      currentResults = data.results;
      updateQuotaBadge(data.quota_used_today, data.quota_remaining);
      exportBtn.disabled = currentResults.length === 0;
      renderTable();

      if (data.warnings && data.warnings.length) {
        showStatus("warn", "⚠️ " + data.warnings.map(escapeHtml).join("<br>"));
      } else {
        showStatus(
          "info",
          `Готово: перевірено ${data.channels_scanned} унікальних каналів, підійшло ${currentResults.length}.`
        );
      }
    } catch (err) {
      showStatus("error", "❌ " + escapeHtml(err.message || String(err)));
    } finally {
      searchBtn.disabled = false;
      searchBtn.textContent = "🔍 Шукати ніші";
      loadHistory();
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = collectFormData();
    if (!payload.keywords.length) {
      showStatus("error", "Введи хоча б одне ключове слово.");
      return;
    }
    await runSearch(payload);
  });

  exportBtn.addEventListener("click", () => {
    if (!currentResults.length) return;
    const headers = [
      "title", "url", "country", "age_months", "video_count", "subscriber_count",
      "total_view_count", "views_per_video", "views_per_subscriber", "score",
      "top_video_title", "top_video_url", "matched_keywords",
    ];
    const rows = currentResults.map((c) =>
      headers
        .map((h) => {
          let v = h === "matched_keywords" ? c[h].join("; ") : c[h];
          if (v === null || v === undefined) v = "";
          if (h === "title" || h === "top_video_title") v = decodeEntities(v);
          v = String(v).replaceAll('"', '""');
          return `"${v}"`;
        })
        .join(",")
    );
    const csv = [headers.join(","), ...rows].join("\r\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `youtube_niches_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  });

  // ---------- Історія пошуків ----------

  async function loadHistory() {
    try {
      const res = await fetch("/api/history?limit=50");
      if (!res.ok) return;
      const items = await res.json();
      renderHistoryTable(items);
    } catch {
      // тихо ігноруємо — історія не критична для основного функціоналу
    }
  }

  function renderHistoryTable(items) {
    if (!items.length) {
      historyBody.innerHTML = `<tr><td colspan="7" class="empty">Історія порожня.</td></tr>`;
      return;
    }
    historyBody.innerHTML = items
      .map((it) => {
        const period = it.published_after_days ? `${it.published_after_days} дн.` : "без обмеження";
        return `
        <tr>
          <td>${fmtDate(it.created_at)}</td>
          <td>${escapeHtml(it.keywords.join(", "))}</td>
          <td>${escapeHtml(it.region_code)}</td>
          <td>${period}</td>
          <td class="num">${fmtInt(it.results_count)}</td>
          <td class="num">${fmtInt(it.quota_used)}</td>
          <td>
            <button type="button" class="icon-btn hist-view" data-id="${it.id}">👁</button>
            <button type="button" class="icon-btn hist-repeat" data-id="${it.id}">🔁</button>
            <button type="button" class="icon-btn danger hist-delete" data-id="${it.id}">🗑</button>
          </td>
        </tr>`;
      })
      .join("");

    historyBody.querySelectorAll(".hist-view").forEach((btn) => {
      btn.addEventListener("click", () => viewHistoryEntry(btn.dataset.id));
    });
    historyBody.querySelectorAll(".hist-repeat").forEach((btn) => {
      btn.addEventListener("click", () => repeatHistoryEntry(btn.dataset.id));
    });
    historyBody.querySelectorAll(".hist-delete").forEach((btn) => {
      btn.addEventListener("click", () => deleteHistoryEntry(btn.dataset.id));
    });
  }

  async function viewHistoryEntry(id) {
    const res = await fetch(`/api/history/${id}`);
    if (!res.ok) {
      showStatus("error", "Не вдалось завантажити запис історії.");
      return;
    }
    const record = await res.json();
    fillForm(record.params);
    currentResults = record.response.results;
    // Бейдж квоти навмисно НЕ оновлюємо тут — він завжди показує поточний реальний
    // залишок (з /api/quota), а не знімок на момент того старого пошуку.
    exportBtn.disabled = currentResults.length === 0;
    renderTable();
    showStatus(
      "info",
      `Показано збережений результат від ${fmtDate(record.created_at)} (без нового запиту до YouTube API).`
    );
    window.scrollTo({ top: table.offsetTop - 20, behavior: "smooth" });
  }

  async function repeatHistoryEntry(id) {
    const res = await fetch(`/api/history/${id}`);
    if (!res.ok) {
      showStatus("error", "Не вдалось завантажити запис історії.");
      return;
    }
    const record = await res.json();
    fillForm(record.params);
    await runSearch(record.params);
  }

  async function deleteHistoryEntry(id) {
    await fetch(`/api/history/${id}`, { method: "DELETE" });
    loadHistory();
  }

  async function refreshQuotaBadge() {
    try {
      const res = await fetch("/api/quota");
      if (!res.ok) return;
      const data = await res.json();
      updateQuotaBadge(data.quota_used_today, data.quota_remaining);
    } catch {
      // бейдж лишається зі значенням, відрендереним сервером при завантаженні сторінки
    }
  }

  historyRefreshBtn.addEventListener("click", loadHistory);
  loadHistory();
  refreshQuotaBadge();

  // ---------- Графік росту каналу ----------

  function buildGrowthSvg(videos) {
    const width = 820;
    const height = 260;
    const padding = { top: 16, right: 20, bottom: 30, left: 60 };
    const plotW = width - padding.left - padding.right;
    const plotH = height - padding.top - padding.bottom;

    const maxCum = Math.max(...videos.map((v) => v.cumulative_views), 1);
    const times = videos.map((v) => new Date(v.published_at).getTime());
    const minT = Math.min(...times);
    const maxT = Math.max(...times, minT + 1);

    const x = (t) => padding.left + ((t - minT) / (maxT - minT || 1)) * plotW;
    const y = (v) => padding.top + plotH - (v / maxCum) * plotH;

    const points = videos.map((v) => [x(new Date(v.published_at).getTime()), y(v.cumulative_views)]);
    const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
    const areaPath = `${linePath} L${points[points.length - 1][0].toFixed(1)},${(padding.top + plotH).toFixed(1)} L${points[0][0].toFixed(1)},${(padding.top + plotH).toFixed(1)} Z`;

    const dots = videos
      .map((v, i) => {
        const [px, py] = points[i];
        let color = "#4f8cff";
        let r = 3;
        if (v.is_breakout) {
          color = "#35c17a";
          r = 6;
        } else if (v.is_peak) {
          color = "#e0a53f";
          r = 5;
        }
        const label = v.is_breakout ? "🚀 Прорив" : v.is_peak ? "★ Пік" : "";
        return `<circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="${r}" fill="${color}" stroke="#0f1526" stroke-width="1">
          <title>${escapeHtml(decodeEntities(v.title))} — ${fmtInt(v.view_count)} переглядів (${fmtDate(v.published_at)}) ${label}</title>
        </circle>`;
      })
      .join("");

    const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => {
      const val = maxCum * f;
      const py = padding.top + plotH - f * plotH;
      return `<line x1="${padding.left}" y1="${py}" x2="${width - padding.right}" y2="${py}" stroke="#263049" stroke-width="1" />
        <text x="${padding.left - 8}" y="${py + 4}" text-anchor="end" font-size="10" fill="#93a0bd">${fmtInt(Math.round(val))}</text>`;
    }).join("");

    return `<svg viewBox="0 0 ${width} ${height}" width="100%" style="max-width:${width}px">
      ${yTicks}
      <path d="${areaPath}" fill="rgba(79,140,255,0.12)" stroke="none" />
      <path d="${linePath}" fill="none" stroke="#4f8cff" stroke-width="2" />
      ${dots}
      <text x="${padding.left}" y="${height - 6}" font-size="10" fill="#93a0bd">${fmtDate(videos[0].published_at)}</text>
      <text x="${width - padding.right}" y="${height - 6}" font-size="10" fill="#93a0bd" text-anchor="end">${fmtDate(videos[videos.length - 1].published_at)}</text>
    </svg>`;
  }

  async function openGrowthModal(channelId, channelTitle) {
    growthTitle.textContent = `📈 ${decodeEntities(channelTitle) || channelId}`;
    growthChartWrap.innerHTML = `<p class="muted">Завантаження…</p>`;
    growthBody.innerHTML = "";
    growthModal.hidden = false;

    try {
      const res = await fetch(`/api/channel/${channelId}/growth`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();

      if (!data.videos.length) {
        growthChartWrap.innerHTML = `<p class="muted">У каналу немає публічних відео для побудови графіка.</p>`;
        return;
      }

      growthChartWrap.innerHTML = buildGrowthSvg(data.videos);

      if (data.truncated || (data.warnings && data.warnings.length)) {
        growthChartWrap.innerHTML += `<p class="hint">⚠️ ${escapeHtml((data.warnings || []).join(" "))}</p>`;
      }

      growthBody.innerHTML = data.videos
        .slice()
        .reverse()
        .map((v) => {
          const rowClass = v.is_breakout ? "row-breakout" : v.is_peak ? "row-peak" : "";
          const type = v.is_short ? `<span class="type-badge short">Short</span>` : `<span class="type-badge long">Long</span>`;
          const mark = v.is_breakout ? "🚀 Прорив" : v.is_peak ? "★ Пік переглядів" : "";
          return `<tr class="${rowClass}">
            <td>${fmtDate(v.published_at)}</td>
            <td><a href="${v.url}" target="_blank" rel="noopener">${escapeHtml(decodeEntities(v.title))}</a></td>
            <td>${type}</td>
            <td class="num">${fmtInt(v.view_count)}</td>
            <td class="num">${fmtInt(v.cumulative_views)}</td>
            <td>${mark}</td>
          </tr>`;
        })
        .join("");
    } catch (err) {
      growthChartWrap.innerHTML = `<p class="hint">❌ ${escapeHtml(err.message || String(err))}</p>`;
    }
  }

  growthCloseBtn.addEventListener("click", () => {
    growthModal.hidden = true;
  });
  growthModal.addEventListener("click", (e) => {
    if (e.target === growthModal) growthModal.hidden = true;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !growthModal.hidden) growthModal.hidden = true;
  });
})();
