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
  const btn = document.getElementById("ask-question-button");
  if (!btn) return;

  const modal = document.getElementById("ask-question-modal");
  const sel = document.getElementById("ask-target");
  const cancel = document.getElementById("ask-cancel");
  const send = document.getElementById("ask-send");

  btn.addEventListener("click", () => {
    modal.style.display = "flex";
  });
  cancel.addEventListener("click", () => {
    modal.style.display = "none";
  });

  send.addEventListener("click", async () => {
  const target = sel.value;
  const qidInput = document.getElementById("ask-question-id");
  const qidRaw = qidInput ? qidInput.value.trim() : "";
  const payload = { target_player_id: parseInt(target, 10) };
  if (qidRaw !== "") {
    const qid = parseInt(qidRaw, 10);
    if (!Number.isFinite(qid) || qid <= 0) {
      if (typeof showMessage === "function") showMessage("Некорректный номер вопроса.", "warning");
      return;
    }
    payload.question_id = qid;  // <== отправляем номер
  }

  try {
    const resp = await fetch(`/games/${gameId}/ask-question/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
    });

    if (resp.status === 204) return;

    let data = {};
    try { data = await resp.json(); } catch {}
    if (!resp.ok) throw new Error(data.error || "Ошибка");
    if (typeof showMessage === "function") showMessage("Вопрос отправлен.", "success");
  } catch (e) {
    if (typeof showMessage === "function") showMessage(String(e.message || e), "error");
  } finally {
    modal.style.display = "none";
  }
});
}
