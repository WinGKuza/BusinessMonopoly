export function showMessage(message, level = "info") {
    const container = document.getElementById("message-container");
    if (!container) return;

    const box = document.createElement("div");
    box.className = "message-box";
    box.textContent = message;

    // Цвета по уровню
    const styles = {
        info: { background: "#e7f5ff", color: "#0c5460" },
        success: { background: "#d4edda", color: "#155724" },
        warning: { background: "#fff3cd", color: "#856404" },
        error: { background: "#f8d7da", color: "#721c24" },
    };

    const style = styles[level] || styles.info;
    Object.assign(box.style, {
        backgroundColor: style.background,
        color: style.color,
        borderRadius: "6px",
        padding: "12px 20px",
        marginTop: "10px",
        textAlign: "center",
        boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
        opacity: "1",
        transition: "opacity 0.5s ease",
    });

    container.appendChild(box);

    setTimeout(() => {
        box.style.opacity = "0";
        setTimeout(() => {
            container.removeChild(box);
        }, 500);
    }, 4000);
}


// Модалка ответа на вопрос (поддерживает выбор и свободный текст)
export function showQuestionModal(q, opts = {}) {
  const gameId   = opts.gameId   || window.gameId;
  const csrf     = opts.csrf     || window.csrfToken;
  const answerUrl= opts.answerUrl|| `/games/${gameId}/answer-question/`;
  const onSubmit = typeof opts.onSubmit === "function" ? opts.onSubmit : null;

  const existing = document.getElementById("__question_modal__");
  if (existing) existing.remove();

  const wrap = document.createElement("div");
  wrap.id = "__question_modal__";
  Object.assign(wrap.style, {
    position: "fixed", inset: 0, background: "rgba(0,0,0,.5)",
    display: "flex", alignItems: "center", justifyContent: "center", zIndex: 4000
  });

  const box = document.createElement("div");
  Object.assign(box.style, {
    background: "#fff", padding: "16px", borderRadius: "8px",
    width: "min(480px,94vw)", boxShadow: "0 8px 24px rgba(0,0,0,.2)"
  });

  const h = document.createElement("h3");
  h.textContent = "Вопрос"; h.style.marginTop = 0;

  const txt = document.createElement("div");
  txt.textContent = q?.text || "";
  Object.assign(txt.style, { marginBottom: "10px", fontSize: "16px", lineHeight: "1.4" });

  const choicesBox = document.createElement("div");
  const choices = Array.isArray(q?.choices) ? q.choices : [];

  let textInput = null;
  if (choices.length) {
    choices.forEach((c, i) => {
      const row = document.createElement("label");
      Object.assign(row.style, { display: "flex", gap: "8px", alignItems: "center", margin: "6px 0" });
      const input = document.createElement("input");
      input.type = "radio"; input.name = "q_choice"; input.value = String(i);
      const span = document.createElement("span"); span.textContent = String(c);
      row.appendChild(input); row.appendChild(span); choicesBox.appendChild(row);
    });
  } else {
    textInput = document.createElement("textarea");
    textInput.placeholder = "Ваш ответ...";
    Object.assign(textInput.style, { width: "100%", minHeight: "80px" });
    choicesBox.appendChild(textInput);
  }

  const actions = document.createElement("div");
  Object.assign(actions.style, { display: "flex", gap: "10px", justifyContent: "flex-end", marginTop: "14px" });

  const btnCancel = document.createElement("button"); btnCancel.textContent = "Отмена";
  const btnSend = document.createElement("button"); btnSend.textContent = "Ответить";
  Object.assign(btnSend.style, { background: "#2f71f5", color: "#fff", border: "none", padding: "6px 12px", borderRadius: "6px", cursor: "pointer" });

  actions.appendChild(btnCancel); actions.appendChild(btnSend);

  function close() { wrap.remove(); }

  btnCancel.addEventListener("click", close);
  btnSend.addEventListener("click", async () => {
    let payload = { question_id: q.question_id, ask_token: q.ask_token };
    if (choices.length) {
      const sel = wrap.querySelector('input[name="q_choice"]:checked');
      if (!sel) { showMessage("Выберите вариант.", "warning"); return; }
      payload.choice_index = parseInt(sel.value, 10);
    } else {
      const val = (textInput?.value || "").trim();
      if (!val) { showMessage("Введите ответ.", "warning"); return; }
      payload.answer_text = val;
    }

    const prev = btnSend.textContent;
    btnSend.disabled = true; btnSend.textContent = "Отправка...";

    try {
      if (onSubmit) {
        await onSubmit(payload);
      } else {
        const resp = await fetch(answerUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest" },
          body: JSON.stringify(payload),
        });
        if (resp.status === 204) { close(); return; }
        if (!resp.ok) {
          let d = {}; try { d = await resp.json(); } catch {}
          throw new Error(d?.error || `Ошибка ${resp.status}`);
        }
      }
      close();
    } catch (e) {
      showMessage(String(e?.message || e), "error");
    } finally {
      btnSend.disabled = false; btnSend.textContent = prev;
    }
  });

  box.appendChild(h); box.appendChild(txt); box.appendChild(choicesBox); box.appendChild(actions);
  wrap.appendChild(box); document.body.appendChild(wrap);
}

// Модалка ревью для Политика: approve/reject ручного ответа
export function showReviewModal(data, opts = {}) {
  // data: {question_id, player_username, answer_text, ask_token, player_id?}
  const gameId = opts.gameId || window.gameId;
  const csrf   = opts.csrf   || window.csrfToken;
  const gradeUrl = opts.gradeUrl || `/games/${gameId}/grade-pending-answer/`;

  const wrap = document.createElement("div");
  Object.assign(wrap.style, {
    position: "fixed", inset: 0, background: "rgba(0,0,0,.5)",
    display: "flex", alignItems: "center", justifyContent: "center", zIndex: 4000
  });

  const box = document.createElement("div");
  Object.assign(box.style, { background: "#fff", padding: "16px", borderRadius: "8px", width: "min(520px,94vw)" });

  const h = document.createElement("h3");
  h.textContent = `Ответ игрока ${data.player_username} по вопросу №${data.question_id}`;

  const ans = document.createElement("pre");
  ans.textContent = data.answer_text || "(пусто)";
  Object.assign(ans.style, { whiteSpace: "pre-wrap", background: "#f8f9fa", padding: "10px", borderRadius: "6px" });

  const actions = document.createElement("div");
  Object.assign(actions.style, { display: "flex", gap: "10px", justifyContent: "flex-end", marginTop: "12px" });

  const btnCancel = document.createElement("button"); btnCancel.textContent = "Закрыть";
  const btnReject = document.createElement("button"); btnReject.textContent = "Отклонить";
  const btnApprove= document.createElement("button"); btnApprove.textContent = "Одобрить";
  Object.assign(btnReject.style, { background: "#dc3545", color: "#fff", border: "none", padding: "6px 12px", borderRadius: "6px", cursor: "pointer" });
  Object.assign(btnApprove.style,{ background: "#198754", color: "#fff", border: "none", padding: "6px 12px", borderRadius: "6px", cursor: "pointer" });

  actions.append(btnCancel, btnReject, btnApprove);

  async function sendDecision(approved) {
    const payload = {
      question_id: data.question_id,
      approved: !!approved,
      ask_token: data.ask_token || null,
    };
    //if (!payload.player_id) { showMessage("Нет player_id для решения.", "error"); return; }

    const btn = approved ? btnApprove : btnReject;
    const prev = btn.textContent;
    btn.disabled = true; btn.textContent = "Отправка…";

    try {
      const resp = await fetch(gradeUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest" },
        body: JSON.stringify(payload),
      });
      let d = {}; try { d = await resp.json(); } catch {}
      if (!resp.ok) throw new Error(d?.error || `Ошибка ${resp.status}`);
      showMessage("Решение сохранено.", "success");
      close();
    } catch (e) {
      showMessage(String(e?.message || e), "error");
    } finally {
      btn.disabled = false; btn.textContent = prev;
    }
  }

  function close() { wrap.remove(); }

  btnCancel.addEventListener("click", close);
  btnReject.addEventListener("click", () => sendDecision(false));
  btnApprove.addEventListener("click", () => sendDecision(true));

  box.append(h, ans, actions); wrap.appendChild(box); document.body.appendChild(wrap);
}

// Глобалы для удобства
if (typeof window !== "undefined") {
  window.showMessage = window.showMessage || showMessage;
  window.showQuestionModal = showQuestionModal;
  window.showReviewModal = showReviewModal;
  window.applyPauseToButtons = applyPauseToButtons;
  window.toggleDisplay = window.toggleDisplay || toggleDisplay;
}


export function applyPauseToButtons(paused) {
  document.querySelectorAll('button[data-pause]').forEach(btn => {
    // ставим disabled, плюс класс для визуала (если где-то disabled не хочется)
    btn.disabled = !!paused;
    btn.classList.toggle('paused', !!paused);
    // подсказка
    if (paused) {
      if (!btn.dataset.prevTitle) btn.dataset.prevTitle = btn.title || "";
      btn.title = "Игра на паузе";
    } else {
      btn.title = btn.dataset.prevTitle || "";
      delete btn.dataset.prevTitle;
    }
  });
}


export function toggleDisplay(id, showAs = 'block') {
  const el = document.getElementById(id);
  if (!el) return;
  const curr = getComputedStyle(el).display;
  el.style.display = (curr === 'none') ? showAs : 'none';
}
window.toggleDisplay = window.toggleDisplay || toggleDisplay;