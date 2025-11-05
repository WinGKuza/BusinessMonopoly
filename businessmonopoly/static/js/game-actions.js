// game-actions.js

export function submitTransfer(gameId, csrfToken) {
    const form = document.getElementById('transfer-form');
    if (!form) return;
    form.addEventListener('submit', function(event) {
        event.preventDefault();
        const receiver = form.receiver.value;
        const amount = form.amount.value;

        fetch(`/games/${gameId}/transfer/`, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body: `receiver_id=${receiver}&amount=${amount}`
        }).then(res => res.json())
          .then(data => {
              if (data.status === "ok") {
                  form.style.display = "none";
                  form.reset();
              } else {
                  alert(data.error || "Ошибка перевода");
              }
          });
    });
}

export function togglePause(gameId, csrfToken) {
    fetch(`/games/${gameId}/toggle_pause/`, {
        method: "POST",
        headers: {
            "X-CSRFToken": csrfToken,
            "X-Requested-With": "XMLHttpRequest"
        }
    });
}

export function toggleMode(gameId, csrfToken) {
    fetch(`/games/${gameId}/toggle_mode/`, {
        method: "POST",
        headers: {
            "X-CSRFToken": csrfToken,
            "X-Requested-With": "XMLHttpRequest"
        }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === "ok") {
            window.isObserver = data.is_observer;
            updateUIForMode(data.is_observer);
        } else {
            alert("Ошибка при переключении режима");
        }
    });
}

function updateUIForMode(isObserver) {
    const playerInfo = document.getElementById("player-info");
    if (playerInfo) {
        playerInfo.style.display = isObserver ? "none" : "block";
    }

    const transferForm = document.getElementById("transfer-form");
    if (transferForm) {
        transferForm.style.display = "none";
    }

    const modeButton = document.getElementById("mode-toggle-button");
    if (modeButton) {
        modeButton.textContent = isObserver ? "Режим игрока" : "Режим наблюдателя";
    }

    submitTransfer(window.gameId, window.csrfToken);
}

export function deleteGame(gameId, csrfToken, redirectUrl) {
    if (!confirm('Вы уверены, что хотите удалить игру?')) return;
    fetch(`/games/${gameId}/delete/`, {
        method: "POST",
        headers: {
            "X-CSRFToken": csrfToken,
            "X-Requested-With": "XMLHttpRequest"
        }
    }).then(res => res.json())
      .then(data => {
          if (data.status === "deleted") {
              window.location.href = redirectUrl;
          }
      });
}

export function leaveGame(gameId, csrfToken, redirectUrl) {
    fetch(`/games/${gameId}/leave/`, {
        method: "POST",
        headers: {
            "X-CSRFToken": csrfToken,
            "X-Requested-With": "XMLHttpRequest"
        }
    }).then(res => res.json())
      .then(data => {
          if (data.status === "left") {
              window.location.href = redirectUrl;
          }
      });
}

export function submitSettings(gameId, csrfToken) {
    const settingsForm = document.getElementById("settings-form");
    if (settingsForm) {
        settingsForm.addEventListener("submit", function(event) {
            event.preventDefault();
            const formData = new FormData(settingsForm);
            fetch(`/games/${gameId}/update_settings/`, {
                method: "POST",
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                },
                body: formData
            });
        });
    }
}


export function upgradeRole(gameId, csrfToken) {
    const upgradeBtn = document.getElementById("upgrade-role-button");
    if (upgradeBtn) {
        upgradeBtn.addEventListener("click", () => {
            const confirmUpgrade = confirm("Вы точно хотите улучшить свою роль?");
            if (!confirmUpgrade) return;

            fetch(`/games/${gameId}/upgrade_role/`, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrfToken,
                    "X-Requested-With": "XMLHttpRequest"
                }
            });
        });
    }
}


export function initElectionUI(currentUsername) {
    console.debug("[election] initElectionUI start");

    let selectedCandidateId = null;

    function openElectionModal() {
        const modal = document.getElementById("election-modal");
        if (modal) modal.style.display = "flex";
    }

    function closeElectionModal() {
        const modal = document.getElementById("election-modal");
        if (modal) modal.style.display = "none";
        selectedCandidateId = null;
    }

    function renderElectionList() {
        const list = document.getElementById("election-list");
        const empty = document.getElementById("election-empty");
        if (!list || !empty) return;

        const candidates = (window.voteCandidates || [])
            .filter(p => p && p.username !== currentUsername);

        list.innerHTML = "";
        if (!candidates.length) {
            empty.style.display = "block";
            return;
        }
        empty.style.display = "none";

        candidates.forEach(p => {
            const item = document.createElement("label");
            item.style.cssText =
                "display:flex;align-items:center;gap:10px;padding:10px;border:1px solid #dee2e6;border-radius:8px;cursor:pointer;";

            const radio = document.createElement("input");
            radio.type = "radio";
            radio.name = "candidate";
            radio.value = p.id;
            radio.style.margin = 0;
            radio.addEventListener("change", () => { selectedCandidateId = p.id; });

            const info = document.createElement("div");
            info.innerHTML = `<strong>${p.username}</strong>`;

            item.appendChild(radio);
            item.appendChild(info);
            list.appendChild(item);
        });
    }

    // Дадим доступ WS-обработчику
    window.renderElectionList = renderElectionList;

    // === Пытаемся навесить обработчики СРАЗУ (без DOMContentLoaded) ===
    bindHandlers();
    // и на всякий случай повторим на следующем тике (если вдруг элементы дорисуются позже)
    setTimeout(bindHandlers, 0);

    function bindHandlers() {
        const reelectBtn = document.getElementById("reelect-button");
        const cancelBtn = document.getElementById("election-cancel");
        const submitBtn = document.getElementById("election-submit");
        const modal = document.getElementById("election-modal");

        console.debug("[election] bindHandlers",
            { reelectBtn: !!reelectBtn, cancelBtn: !!cancelBtn, submitBtn: !!submitBtn, modal: !!modal });

        if (reelectBtn && !reelectBtn.__electionBound) {
            reelectBtn.__electionBound = true;
            reelectBtn.addEventListener("click", () => {
                renderElectionList();
                openElectionModal();
            });
            //console.debug("[election] click bound to #reelect-button");
        }

        if (cancelBtn && !cancelBtn.__electionBound) {
            cancelBtn.__electionBound = true;
            cancelBtn.addEventListener("click", closeElectionModal);
        }

        if (modal && !modal.__electionBound) {
            modal.__electionBound = true;
            modal.addEventListener("click", (e) => {
                if (e.target === modal) closeElectionModal();
            });
        }

        if (submitBtn && !submitBtn.__electionBound) {
            submitBtn.__electionBound = true;
            submitBtn.addEventListener("click", async () => {
                if (!selectedCandidateId) {
                    if (typeof showMessage === "function") showMessage("Выберите кандидата.", "warning");
                    return;
                }

                const reelectBtnNow = document.getElementById("reelect-button");
                const url = reelectBtnNow && reelectBtnNow.getAttribute("data-vote-url");
                if (!url) {
                    if (typeof showMessage === "function") showMessage("URL голосования не настроен.", "error");
                    return;
                }

                const prevText = submitBtn.textContent;
                submitBtn.disabled = true;
                submitBtn.textContent = "Отправка...";

                try {
                    const res = await fetch(url, {
                        method: "POST",
                        headers: {
                            "X-CSRFToken": window.csrfToken,
                            "X-Requested-With": "XMLHttpRequest",
                            "Content-Type": "application/json",
                        },
                        body: JSON.stringify({ candidate_id: selectedCandidateId }),
                    });

                    let payload = null;
                    try { payload = await res.json(); } catch (_) {}

                    if (!res.ok) {
                        const msg = (payload && (payload.error || payload.message)) || "Ошибка при голосовании.";
                        if (typeof showMessage === "function") showMessage(msg, "error");
                    } else {
                        if (typeof showMessage === "function") showMessage("Голос учтён.", "success");
                        closeElectionModal();
                    }
                } catch {
                    if (typeof showMessage === "function") showMessage("Сеть недоступна. Повторите позже.", "error");
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.textContent = prevText;
                }
            });
        }
    }
}



export function initPoliticianQuestions(gameId, csrfToken) {
  const askBtn   = document.getElementById("ask-question-button");
  const modal    = document.getElementById("ask-question-modal");
  if (!askBtn || !modal) return;

  const selTarget= document.getElementById("ask-target");
  const inputId  = document.getElementById("ask-question-id");
  const btnSend  = document.getElementById("ask-send");
  const btnCancel= document.getElementById("ask-cancel");

  const open = () => { modal.style.display = "flex"; };
  const close= () => { modal.style.display = "none"; };

  askBtn.addEventListener("click", () => {
    if (window.paused) { showMessage("Игра на паузе", "warning"); return; }
    open();
  });

  btnCancel.addEventListener("click", close);

  btnSend.addEventListener("click", async () => {
    try {
      const targetId = parseInt(selTarget.value, 10);
      const qidRaw   = (inputId.value || "").trim();
      const body = { target_player_id: targetId };
      if (qidRaw) body.question_id = parseInt(qidRaw, 10);

      const resp = await fetch(`/games/${gameId}/ask-question/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify(body),
      });

      if (resp.status === 204) { close(); return; }
      let data = {}; try { data = await resp.json(); } catch {}
      if (!resp.ok) throw new Error(data?.error || `Ошибка ${resp.status}`);

      showMessage("Вопрос отправлен.", "success");
      close();
    } catch (e) {
      showMessage(String(e?.message || e), "error");
    }
  });
}

export async function startElectionEarly(gameId, csrfToken) {
    if (!confirm("Запустить выборы досрочно?")) return;

    try {
        const resp = await fetch(`/games/${gameId}/elections/start_early/`, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken,
                "X-Requested-With": "XMLHttpRequest"
            }
        });

        // пробуем прочитать JSON, даже если не ok
        let data = {};
        try { data = await resp.json(); } catch (_) {}

        if (!resp.ok) {
            const msg = data.error || data.message || "Не удалось запустить выборы (нет прав или ошибка).";
            if (typeof showMessage === "function") showMessage(msg, "error");
            else alert(msg);
            return;
        }

        if (data.status === "already_running") {
            if (typeof showMessage === "function") showMessage("Голосование уже идёт.", "info");
            else alert("Голосование уже идёт.");
        } else {
            if (typeof showMessage === "function") showMessage("Выборы запущены.", "success");
            else alert("Выборы запущены.");
        }
    } catch (e) {
        if (typeof showMessage === "function") showMessage("Сеть недоступна. Попробуйте ещё раз.", "error");
        else alert("Сеть недоступна. Попробуйте ещё раз.");
    } finally {
        // аккуратно закрыть меню шестерёнки, если открыто
        const menu = document.getElementById("settings-menu");
        if (menu) menu.style.display = "none";
    }
}

export function initBankerSelectionUI(gameId, csrfToken) {
  const modal = document.getElementById("banker-modal");
  const list = document.getElementById("banker-list");
  const empty = document.getElementById("banker-empty");
  const cancel = document.getElementById("banker-cancel");
  const submit = document.getElementById("banker-submit");
  if (!modal || !list || !cancel || !submit) return;

  let selectedBankerId = null;

  function openModal(candidates) {
    list.innerHTML = "";
    selectedBankerId = null;
    if (!Array.isArray(candidates) || !candidates.length) {
      empty.style.display = "block";
    } else {
      empty.style.display = "none";
      candidates.forEach(c => {
        const item = document.createElement("label");
        item.style.cssText = "display:flex;align-items:center;gap:10px;padding:8px;border:1px solid #dee2e6;border-radius:8px;cursor:pointer;margin-bottom:6px;";

        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = "banker";
        radio.value = c.id;
        radio.addEventListener("change", () => { selectedBankerId = c.id; });

        const info = document.createElement("div");
        const name = c.username || c["user__username"] || `#${c.id}`;
        info.innerHTML = `<strong>${name}</strong>`;

        item.appendChild(radio);
        item.appendChild(info);
        list.appendChild(item);
      });
    }
    modal.style.display = "flex";
  }
  function closeModal() { modal.style.display = "none"; }

  // делаем доступными для вызова из WS
  window.__openBankerSelection = openModal;
  window.__closeBankerSelection = closeModal;
  if (Array.isArray(window._bankerQueue)) {
      while (_bankerQueue.length) {
        const ev = _bankerQueue.shift();
        if (ev.type === "open") openModal(ev.cands);
        else if (ev.type === "close") closeModal();
      }
    }
  cancel.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });

  submit.addEventListener("click", async () => {
    if (!selectedBankerId) {
      if (typeof showMessage === "function") showMessage("Выберите банкира.", "warning");
      else alert("Выберите банкира.");
      return;
    }
    const prev = submit.textContent;
    submit.disabled = true;
    submit.textContent = "Отправка...";
    try {
      const res = await fetch(`/games/${gameId}/choose_banker/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ banker_id: selectedBankerId }),
      });
      let data = {};
      try { data = await res.json(); } catch {}
      if (!res.ok) {
        const msg = data.error || "Ошибка назначения банкира.";
        if (typeof showMessage === "function") showMessage(msg, "error"); else alert(msg);
      } else {
        if (typeof showMessage === "function") showMessage("Банкир назначен.", "success");
        closeModal();
      }
    } finally {
      submit.disabled = false;
      submit.textContent = prev;
    }
  });
}

export function bindTransferToggle() {
  const btn = document.querySelector('button[data-toggle="transfer"]');
  if (!btn) return;
  btn.addEventListener("click", () => window.toggleDisplay("transfer-form"));
}