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


export function showQuestionModal(q, opts = {}) {
  // q = { question_id, text, choices: [], ... } (как присылаем по WS)
  const gameId = opts.gameId || window.gameId;
  const csrfToken = opts.csrfToken || window.csrfToken;
  const answerUrl = opts.answerUrl || `/games/${gameId}/answer-question/`;
  const onSubmit = typeof opts.onSubmit === "function" ? opts.onSubmit : null;

  // если уже есть открытая — закроем
  const existing = document.getElementById("__question_modal__");
  if (existing) existing.remove();

  const wrap = document.createElement("div");
  wrap.id = "__question_modal__";
  Object.assign(wrap.style, {
    position: "fixed",
    inset: "0",
    background: "rgba(0,0,0,.5)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: "4000",
  });

  // контейнер
  const box = document.createElement("div");
  Object.assign(box.style, {
    background: "#fff",
    padding: "16px",
    borderRadius: "8px",
    width: "min(480px, 94vw)",
    boxShadow: "0 8px 24px rgba(0,0,0,.2)",
  });

  const title = document.createElement("h3");
  title.textContent = "Вопрос";
  title.style.marginTop = "0";

  const text = document.createElement("div");
  text.textContent = q?.text || "";
  Object.assign(text.style, { marginBottom: "10px", fontSize: "16px", lineHeight: "1.4" });

  const choicesBox = document.createElement("div");
  const choices = Array.isArray(q?.choices) ? q.choices : [];

  if (choices.length) {
    choices.forEach((c, i) => {
      const row = document.createElement("label");
      Object.assign(row.style, { display: "flex", gap: "8px", alignItems: "center", margin: "6px 0" });

      const input = document.createElement("input");
      input.type = "radio";
      input.name = "q_choice";
      input.value = String(i);

      const span = document.createElement("span");
      span.textContent = String(c);

      row.appendChild(input);
      row.appendChild(span);
      choicesBox.appendChild(row);
    });
  } else {
    const empty = document.createElement("div");
    empty.textContent = "Нет вариантов ответа.";
    empty.style.color = "#888";
    choicesBox.appendChild(empty);
  }

  const actions = document.createElement("div");
  Object.assign(actions.style, { display: "flex", gap: "10px", justifyContent: "flex-end", marginTop: "14px" });

  const btnCancel = document.createElement("button");
  btnCancel.textContent = "Отмена";

  const btnSend = document.createElement("button");
  btnSend.textContent = "Ответить";
  Object.assign(btnSend.style, { background: "#2f71f5", color: "#fff", border: "none", padding: "6px 12px", borderRadius: "6px", cursor: "pointer" });

  actions.appendChild(btnCancel);
  actions.appendChild(btnSend);

  box.appendChild(title);
  box.appendChild(text);
  box.appendChild(choicesBox);
  box.appendChild(actions);
  wrap.appendChild(box);

  function close() { wrap.remove(); }

  btnCancel.addEventListener("click", close);

  btnSend.addEventListener("click", async () => {
    const sel = wrap.querySelector('input[name="q_choice"]:checked');
    if (!sel) {
      if (typeof showMessage === "function") showMessage("Выберите вариант.", "warning");
      return;
    }
    const choiceIndex = parseInt(sel.value, 10);

    try {
      if (onSubmit) {
        // пользовательский обработчик (если передали)
        await onSubmit({ question_id: q.question_id, choice_index: choiceIndex });
      } else {
        // дефолт: шлём на /answer-question/
        const resp = await fetch(answerUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken,
            "X-Requested-With": "XMLHttpRequest",
          },
          body: JSON.stringify({ question_id: q.question_id, choice_index: choiceIndex }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data?.error || "Ошибка");

        /*if (typeof showMessage === "function") {
          if (data.correct === true) showMessage("Верно! 🎉", "success");
          else if (data.correct === false) showMessage("Неверно.", "warning");
          else showMessage("Ответ отправлен.", "info");
        }*/
      }
      close();
    } catch (e) {
      if (typeof showMessage === "function") showMessage(String(e?.message || e), "error");
    }
  });

  document.body.appendChild(wrap);
}

// Сделаем доступными и как ESM-экспорты, и как глобалы (на случай, если где-то ещё используют глобально)
if (typeof window !== "undefined") {
  window.showMessage = window.showMessage || showMessage;
  window.showQuestionModal = showQuestionModal;
}

