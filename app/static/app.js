(() => {
  const form = document.getElementById("search-form");
  const searchBtn = document.getElementById("search-btn");
  const exportBtn = document.getElementById("export-btn");
  const statusEl = document.getElementById("status");
  const tbody = document.getElementById("results-body");
  const resultsCount = document.getElementById("results-count");
  const quotaUsedEl = document.getElementById("quota-used");
  const table = document.getElementById("results-table");

  let currentResults = [];
  let sortKey = "score";
  let sortDir = -1; // -1 = desc, 1 = asc

  function showStatus(kind, html) {
    statusEl.hidden = false;
    statusEl.className = `status ${kind}`;
    statusEl.innerHTML = html;
  }

  function hideStatus() {
    statusEl.hidden = true;
  }

  function fmtInt(n) {
    if (n === null || n === undefined) return "—";
    return Number(n).toLocaleString("uk-UA");
  }

  function fmtFloat(n, digits = 1) {
    if (n === null || n === undefined) return "—";
    return Number(n).toLocaleString("uk-UA", { maximumFractionDigits: digits });
  }

  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function renderTable() {
    if (!currentResults.length) {
      tbody.innerHTML = `<tr><td colspan="11" class="empty">Нічого не знайдено за цими фільтрами. Спробуй послабити пороги або інші ключові слова.</td></tr>`;
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
        const topVideo = c.top_video_url
          ? `<a href="${c.top_video_url}" target="_blank" rel="noopener">${escapeHtml(c.top_video_title || "відео")}</a><br><span class="muted">${fmtInt(c.top_video_views)} переглядів</span>`
          : "—";
        return `
        <tr>
          <td><a href="${c.url}" target="_blank" rel="noopener">${escapeHtml(c.title)}</a></td>
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
        </tr>`;
      })
      .join("");

    resultsCount.textContent = `${currentResults.length} канал(ів)`;
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
      published_after_days: Number(fd.get("published_after_days")) || null,
      pages_per_keyword: Number(fd.get("pages_per_keyword")),
      min_views_per_video: Number(fd.get("min_views_per_video")) || 0,
      max_video_count: Number(fd.get("max_video_count")),
      max_channel_age_months: Number(fd.get("max_channel_age_months")),
      min_subscribers: optInt("min_subscribers"),
      max_subscribers: optInt("max_subscribers"),
    };
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = collectFormData();
    if (!payload.keywords.length) {
      showStatus("error", "Введи хоча б одне ключове слово.");
      return;
    }

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
      quotaUsedEl.textContent = data.quota_used_session;
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
    }
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
})();
