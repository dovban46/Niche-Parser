const VideoFactory = (() => {
  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString("uk-UA");
    } catch {
      return iso;
    }
  }

  function statusBadge(status) {
    return `<span class="status-badge status-${status}">${escapeHtml(status)}</span>`;
  }

  function formatStageBody(stage) {
    const parts = [];
    if (stage.error_message) parts.push("Помилка: " + stage.error_message);
    if (stage.output) parts.push(JSON.stringify(stage.output, null, 2));
    if (stage.started_at) parts.push("Почато: " + stage.started_at);
    if (stage.finished_at) parts.push("Завершено: " + stage.finished_at);
    parts.push("Спроб: " + stage.attempt);
    return parts.join("\n\n") || "(ще не запускалась)";
  }

  async function deleteJob(jobId) {
    if (!confirm(`Видалити job #${jobId}? Сценарій, озвучку та готове відео буде видалено з диска безповоротно.`)) {
      return false;
    }
    const res = await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert("Не вдалося видалити: " + (err.detail || `HTTP ${res.status}`));
      return false;
    }
    return true;
  }

  // ---------------- Index page ----------------

  function initIndexPage() {
    const form = document.getElementById("create-form");
    const createBtn = document.getElementById("create-btn");
    const createStatus = document.getElementById("create-status");
    const jobsBody = document.getElementById("jobs-body");
    const refreshBtn = document.getElementById("refresh-btn");
    const languageSelect = document.getElementById("language");
    const voiceField = document.getElementById("voice-field");
    const voiceSelect = document.getElementById("voice");
    const voiceCustom = document.getElementById("voice-custom");
    const voicePreviewBtn = document.getElementById("voice-preview-btn");
    const voicePreviewAudio = document.getElementById("voice-preview-audio");
    const voiceHint = document.getElementById("voice-hint");
    const CUSTOM = "__custom__";
    let voiceProvider = null;

    function selectedVoiceId() {
      if (voiceSelect.value === CUSTOM) return voiceCustom.value.trim() || null;
      return voiceSelect.value || null;
    }

    async function loadVoices() {
      voicePreviewAudio.hidden = true;
      voiceHint.hidden = true;
      try {
        const res = await fetch(`/api/voices?language=${encodeURIComponent(languageSelect.value)}`);
        if (!res.ok) return;
        const data = await res.json();
        voiceProvider = data.provider;
        if (!data.voices.length) {
          voiceField.hidden = true;
          return;
        }
        voiceField.hidden = false;
        const opts = [`<option value="">Авто (за замовчуванням провайдера)</option>`];
        for (const v of data.voices) {
          const gender = v.gender === "female" ? "жін." : "чол.";
          opts.push(`<option value="${escapeHtml(v.id)}">${escapeHtml(v.name)} · ${gender} · ${escapeHtml(v.note)}</option>`);
        }
        if (data.provider === "elevenlabs") opts.push(`<option value="${CUSTOM}">Свій ID голосу…</option>`);
        voiceSelect.innerHTML = opts.join("");
        voiceCustom.hidden = true;
      } catch {
        // тиха відмова — форма лишається робочою з голосом за замовчуванням
      }
    }

    voiceSelect.addEventListener("change", () => {
      voiceCustom.hidden = voiceSelect.value !== CUSTOM;
      voicePreviewAudio.hidden = true;
      voiceHint.hidden = true;
    });

    voicePreviewBtn.addEventListener("click", async () => {
      voicePreviewBtn.disabled = true;
      voicePreviewBtn.textContent = "⏳ Синтезую…";
      voiceHint.hidden = true;
      try {
        const res = await fetch("/api/voices/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ language: languageSelect.value, voice_id: selectedVoiceId() }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(typeof err.detail === "string" ? err.detail : `HTTP ${res.status}`);
        }
        const data = await res.json();
        voicePreviewAudio.src = data.url;
        voicePreviewAudio.hidden = false;
        voicePreviewAudio.play().catch(() => {});
        if (voiceProvider === "elevenlabs") {
          voiceHint.textContent = "Проба кешується — повторне прослуховування цього голосу безкоштовне.";
          voiceHint.hidden = false;
        }
      } catch (err) {
        voiceHint.textContent = "❌ " + (err.message || String(err));
        voiceHint.hidden = false;
      } finally {
        voicePreviewBtn.disabled = false;
        voicePreviewBtn.textContent = "🔊 Прослухати";
      }
    });

    languageSelect.addEventListener("change", loadVoices);

    function renderJobs(jobs) {
      if (!jobs.length) {
        jobsBody.innerHTML = `<tr><td colspan="10" class="empty">Завдань ще немає.</td></tr>`;
        return;
      }
      jobsBody.innerHTML = jobs
        .map(
          (j) => `
        <tr>
          <td>${j.id}</td>
          <td>${escapeHtml(j.topic)}${j.preview_seconds ? ` <span class="muted">· тест ${j.preview_seconds} с</span>` : ""}</td>
          <td>${escapeHtml(j.niche)}</td>
          <td>${escapeHtml(j.language)}</td>
          <td>${escapeHtml(j.voice_name || "авто")}</td>
          <td>${j.target_duration_minutes} хв</td>
          <td>${statusBadge(j.status)}</td>
          <td>${j.progress_done}/${j.progress_total}${j.current_stage ? " · " + escapeHtml(j.current_stage) : ""}</td>
          <td>${fmtDate(j.updated_at)}</td>
          <td>
            <a href="/jobs/${j.id}">Деталі →</a>
            <button type="button" class="row-delete" data-delete="${j.id}" title="Видалити job і всі його файли">🗑</button>
          </td>
        </tr>`
        )
        .join("");
    }

    jobsBody.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-delete]");
      if (!btn) return;
      if (await deleteJob(Number(btn.dataset.delete))) loadJobs();
    });

    async function loadJobs() {
      try {
        const res = await fetch("/api/jobs");
        if (!res.ok) return;
        renderJobs(await res.json());
      } catch {
        // тиха відмова — наступний polling спробує знову
      }
    }

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const payload = {
        topic: fd.get("topic"),
        niche: fd.get("niche") || "space_science",
        target_duration_minutes: Number(fd.get("target_duration_minutes")) || 20,
        language: fd.get("language") || "uk",
        voice_id: selectedVoiceId(),
        style_id: fd.get("style_id") || null,
        preview_seconds: fd.get("preview_seconds") ? Number(fd.get("preview_seconds")) : null,
        auto_dossier: fd.get("auto_dossier") === "on",
      };

      createBtn.disabled = true;
      createStatus.hidden = false;
      createStatus.textContent = "Створюю job…";

      try {
        const res = await fetch("/api/jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail ? JSON.stringify(err.detail) : `HTTP ${res.status}`);
        }
        const data = await res.json();
        createStatus.textContent = `✅ Job #${data.id} створено і поставлено в чергу.`;
        form.reset();
        document.getElementById("niche").value = "space_science";
        document.getElementById("target_duration_minutes").value = 20;
        loadVoices();
        loadJobs();
      } catch (err) {
        createStatus.textContent = "❌ " + escapeHtml(err.message || String(err));
      } finally {
        createBtn.disabled = false;
      }
    });

    refreshBtn.addEventListener("click", loadJobs);
    loadVoices();
    loadJobs();
    setInterval(loadJobs, 3000);
  }

  // ---------------- Job detail page ----------------

  function initJobDetailPage(jobId) {
    const header = document.getElementById("job-header");
    const stepper = document.getElementById("stage-stepper");
    const retryBtn = document.getElementById("retry-btn");
    const deleteBtn = document.getElementById("delete-btn");
    const segmentsPanel = document.getElementById("segments-panel");
    const segmentsBody = document.getElementById("segments-body");
    const qaPanel = document.getElementById("qa-panel");
    const qaBody = document.getElementById("qa-body");
    const metadataPanel = document.getElementById("metadata-panel");
    const metadataContent = document.getElementById("metadata-content");

    const scriptPanel = document.getElementById("script-panel");
    const scriptTextEl = document.getElementById("script-text");
    const scriptStatusHint = document.getElementById("script-status-hint");
    const scriptReviewControls = document.getElementById("script-review-controls");
    const scriptFeedback = document.getElementById("script-feedback");
    const reviseBtn = document.getElementById("revise-btn");
    const approveBtn = document.getElementById("approve-btn");
    const scriptReviewStatus = document.getElementById("script-review-status");

    const dossierPanel = document.getElementById("dossier-panel");
    const dossierText = document.getElementById("dossier-text");
    const dossierHint = document.getElementById("dossier-hint");
    const dossierControls = document.getElementById("dossier-controls");
    const dossierSaveBtn = document.getElementById("dossier-save-btn");
    const dossierApproveBtn = document.getElementById("dossier-approve-btn");
    const dossierStatus = document.getElementById("dossier-status");
    let dossierDirty = false;
    dossierText.addEventListener("input", () => { dossierDirty = true; });

    let pollTimer = null;
    const openStages = new Set();

    function renderHeader(job) {
      header.innerHTML = `
        <h2>${escapeHtml(job.topic)}</h2>
        <p class="muted">Ніша: ${escapeHtml(job.niche)} · Мова: ${escapeHtml(job.language)} · Голос: ${escapeHtml(job.voice_name || "авто")} · Стиль: ${escapeHtml(job.style_id || "за замовчуванням")} · Тривалість: ${job.target_duration_minutes} хв${job.preview_seconds ? ` · <strong>ТЕСТ: перші ${job.preview_seconds} с</strong>` : ""} · Створено: ${fmtDate(job.created_at)}${job.estimated_cost_usd ? ` · Витрати (озвучка+візуал): ≈ $${job.estimated_cost_usd}` : ""}</p>
        ${job.visual_glossary ? `<details class="glossary"><summary>Візуальний глосарій (історичні деталі в кожному кадрі)</summary>${escapeHtml(job.visual_glossary)}</details>` : ""}
        <p>${statusBadge(job.status)} ${job.current_stage ? "— " + escapeHtml(job.current_stage) : ""} (${job.progress_done}/${job.progress_total})</p>
        ${job.error_message ? `<p class="hint" style="color:var(--bad)">❌ ${escapeHtml(job.error_message)}</p>` : ""}
        ${
          job.final_video_url
            ? `<video controls src="${job.final_video_url}"></video>`
            : `<p class="hint">Фінальне відео ще не зібрано (з'являється після стадії "Збірка відео"; готові відео лежать у теці videos/).</p>`
        }
      `;
    }

    function renderDossier(job) {
      if (!job.dossier) {
        dossierPanel.hidden = true;
        return;
      }
      dossierPanel.hidden = false;
      const awaiting = job.status === "awaiting_review" && job.current_stage === "research_dossier";
      if (!dossierDirty) dossierText.value = job.dossier;
      dossierText.readOnly = !awaiting;
      dossierControls.hidden = !awaiting;
      dossierHint.textContent = awaiting
        ? "⏸ Пайплайн зупинено — перевір і за потреби виправ досьє (це швидка перевірка, не глибоке дослідження)."
        : job.dossier_approved ? "✅ Досьє схвалено." : "";
    }

    async function saveDossier() {
      const res = await fetch(`/api/jobs/${jobId}/dossier`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: dossierText.value }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(typeof err.detail === "string" ? err.detail : `HTTP ${res.status}`);
      }
      dossierDirty = false;
    }

    dossierSaveBtn.addEventListener("click", async () => {
      dossierSaveBtn.disabled = true;
      try {
        await saveDossier();
        dossierStatus.hidden = false;
        dossierStatus.textContent = "✅ Правки збережено.";
      } catch (err) {
        dossierStatus.hidden = false;
        dossierStatus.textContent = "❌ " + escapeHtml(err.message || String(err));
      } finally {
        dossierSaveBtn.disabled = false;
      }
    });

    dossierApproveBtn.addEventListener("click", async () => {
      dossierApproveBtn.disabled = true;
      dossierSaveBtn.disabled = true;
      try {
        if (dossierDirty) await saveDossier();
        const res = await fetch(`/api/jobs/${jobId}/dossier/approve`, { method: "POST" });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        await load();
      } catch (err) {
        dossierStatus.hidden = false;
        dossierStatus.textContent = "❌ " + escapeHtml(err.message || String(err));
      } finally {
        dossierApproveBtn.disabled = false;
        dossierSaveBtn.disabled = false;
      }
    });

    function renderScript(job) {
      if (!job.script_text) {
        scriptPanel.hidden = true;
        return;
      }
      scriptPanel.hidden = false;
      scriptTextEl.textContent = job.script_text;

      const isAwaiting = job.status === "awaiting_review" && job.current_stage === "script_review";
      scriptReviewControls.hidden = !isAwaiting;
      if (isAwaiting) {
        scriptStatusHint.textContent = "⏸ Пайплайн зупинено — перевір сценарій нижче.";
      } else if (job.script_approved) {
        scriptStatusHint.textContent = "✅ Сценарій підтверджено, пайплайн продовжено.";
      } else {
        scriptStatusHint.textContent = "";
      }
    }

    function renderStages(job) {
      stepper.innerHTML = job.stages
        .map((s) => {
          const isOpen = openStages.has(s.stage_name);
          return `
        <div class="stage-row">
          <div class="stage-row-header" data-stage="${s.stage_name}">
            <span><span class="stage-order">${s.stage_order + 1}/${job.stages.length}</span><span class="stage-name">${escapeHtml(s.stage_label)}</span></span>
            ${statusBadge(s.status)}
          </div>
          <div class="stage-row-body" ${isOpen ? "" : "hidden"}>${escapeHtml(formatStageBody(s))}</div>
        </div>`;
        })
        .join("");

      stepper.querySelectorAll(".stage-row-header").forEach((el) => {
        el.addEventListener("click", () => {
          const name = el.dataset.stage;
          const body = el.parentElement.querySelector(".stage-row-body");
          if (body.hasAttribute("hidden")) {
            body.removeAttribute("hidden");
            openStages.add(name);
          } else {
            body.setAttribute("hidden", "");
            openStages.delete(name);
          }
        });
      });
    }

    function renderSegments(job) {
      if (!job.segments || !job.segments.length) return;
      segmentsPanel.hidden = false;
      segmentsBody.innerHTML = job.segments
        .map(
          (s) => `
        <tr>
          <td>${s.index}</td>
          <td>${escapeHtml(s.text.slice(0, 90))}${s.text.length > 90 ? "…" : ""}</td>
          <td>
            <span class="tag ${s.visual_type === "animated" ? "animated" : ""}">${s.visual_type === "animated" ? "анімація" : "кадр"}</span>
            ${(s.sfx || []).map((t) => `<span class="tag">🔊 ${escapeHtml(t)}</span>`).join("")}
            ${s.ambience ? `<span class="tag">фон: ${escapeHtml(s.ambience)}</span>` : ""}
            ${s.cta ? `<span class="tag animated">CTA: підписка/лайк</span>` : ""}
          </td>
          <td>${s.audio_url ? `<audio controls src="${s.audio_url}"></audio>` : "—"}</td>
          <td title="${escapeHtml(s.shot || "")}">${
            s.clip_url ? `<video class="visual-thumb" src="${s.clip_url}" muted loop controls></video>`
            : s.visual_url ? `<img class="visual-thumb" src="${s.visual_url}" alt="">` : "—"
          }</td>
          <td>${s.duration_ms ? (s.duration_ms / 1000).toFixed(1) + "с" : "—"}</td>
          <td>${statusBadge(s.status)}</td>
        </tr>`
        )
        .join("");
    }

    function renderQa(job) {
      if (!job.qa_issues || !job.qa_issues.length) return;
      qaPanel.hidden = false;
      qaBody.innerHTML = job.qa_issues
        .map(
          (i) => `
        <tr>
          <td>${escapeHtml(i.issue_type)}</td>
          <td>${escapeHtml(i.severity)}</td>
          <td>${statusBadge(i.resolution)}</td>
          <td>${escapeHtml(i.notes || "")}</td>
        </tr>`
        )
        .join("");
    }

    function renderMetadata(job) {
      const metaStage = job.stages.find((s) => s.stage_name === "metadata_generate");
      if (!metaStage || !metaStage.output) return;
      metadataPanel.hidden = false;
      const out = metaStage.output;
      const lintByTitle = new Map((out.title_lint || []).map((r) => [r.title, r]));
      metadataContent.innerHTML = `
        <h3>Варіанти назви</h3>
        <ul>${(out.title_options || [])
          .map((t) => {
            const r = lintByTitle.get(t);
            const score = r ? ` — <b>${r.score}/100</b>` : "";
            return `<li>${escapeHtml(t)}${score}</li>`;
          })
          .join("")}</ul>
        <h3>Опис</h3>
        <p class="metadata-description">${escapeHtml(out.description || "(не згенеровано)").replace(/\n/g, "<br>")}</p>
        <h3>Теги</h3>
        <p>${(out.tags || []).map(escapeHtml).join(", ")}</p>
        <h3>Прев'ю</h3>
        ${out.thumbnail_text ? `<p>Текст на прев'ю: <b>${escapeHtml(out.thumbnail_text)}</b></p>` : ""}
        <div class="thumb-grid">${(out.thumbnails || []).map((p) => `<img src="/storage/${p}" alt="">`).join("")}</div>
      `;
    }

    async function load() {
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) return;
        const job = await res.json();

        renderHeader(job);
        renderDossier(job);
        renderScript(job);
        renderStages(job);
        renderSegments(job);
        renderQa(job);
        renderMetadata(job);

        retryBtn.hidden = job.status !== "failed";

        if (job.status === "running" || job.status === "pending") {
          if (!pollTimer) pollTimer = setInterval(load, 2500);
        } else if (pollTimer) {
          clearInterval(pollTimer);
          pollTimer = null;
        }
      } catch {
        // тиха відмова — наступний polling спробує знову
      }
    }

    retryBtn.addEventListener("click", async () => {
      retryBtn.disabled = true;
      await fetch(`/api/jobs/${jobId}/retry`, { method: "POST" });
      retryBtn.disabled = false;
      load();
    });

    deleteBtn.addEventListener("click", async () => {
      if (await deleteJob(jobId)) window.location.href = "/";
    });

    approveBtn.addEventListener("click", async () => {
      approveBtn.disabled = true;
      reviseBtn.disabled = true;
      try {
        const res = await fetch(`/api/jobs/${jobId}/script/approve`, { method: "POST" });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        scriptFeedback.value = "";
        await load();
      } catch (err) {
        scriptReviewStatus.hidden = false;
        scriptReviewStatus.textContent = "❌ " + escapeHtml(err.message || String(err));
      } finally {
        approveBtn.disabled = false;
        reviseBtn.disabled = false;
      }
    });

    reviseBtn.addEventListener("click", async () => {
      const feedback = scriptFeedback.value.trim();
      if (!feedback) {
        scriptReviewStatus.hidden = false;
        scriptReviewStatus.textContent = "Опиши, що саме треба змінити.";
        return;
      }
      approveBtn.disabled = true;
      reviseBtn.disabled = true;
      reviseBtn.textContent = "⏳ Вношу правки…";
      scriptReviewStatus.hidden = true;
      try {
        const res = await fetch(`/api/jobs/${jobId}/script/revise`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ feedback }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        const data = await res.json();
        scriptTextEl.textContent = data.script_text;
        scriptFeedback.value = "";
        scriptReviewStatus.hidden = false;
        scriptReviewStatus.textContent = "✅ Правки внесено — перевір текст ще раз.";
      } catch (err) {
        scriptReviewStatus.hidden = false;
        scriptReviewStatus.textContent = "❌ " + escapeHtml(err.message || String(err));
      } finally {
        approveBtn.disabled = false;
        reviseBtn.disabled = false;
        reviseBtn.textContent = "✏️ Внести правки";
      }
    });

    load();
  }

  return { initIndexPage, initJobDetailPage };
})();
