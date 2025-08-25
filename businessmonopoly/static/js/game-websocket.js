// static/js/game-websocket.js
import { applyPauseToButtons, showQuestionModal } from "/static/js/ui-utils.js";

export function initWebSocket(gameId, currentUsername) {
  const socket = new WebSocket(`ws://${window.location.host}/ws/game/${gameId}/`);

  socket.onmessage = async function (e) {
    const data = JSON.parse(e.data);

    // 1) Персональные сообщения
    if (data.type === "personal") {
      const msg = data.message;

      // вопрос игроку → открываем модалку
      if (msg?.data?.kind === "question") {
        (typeof showQuestionModal === "function" ? showQuestionModal : window.showQuestionModal)?.(msg.data);
        return;
      }

      if (typeof msg === "string") {
        window.showMessage?.(msg, "info");
      } else {
        window.showMessage?.(msg.message, msg.level || "info");
      }
      return;
    }

    // 2) Обновление состояния игры
    if (data.type === "update") {
      const update = data.data;

      if (update.money !== undefined && !window.isObserver) {
        document.getElementById("player-money").textContent = `${update.money}`;
      }
      if (update.influence !== undefined && !window.isObserver) {
        document.getElementById("player-influence").textContent = `${update.influence} ⭐`;
      }
      if (update.role !== undefined && !window.isObserver) {
        document.getElementById("player-role").textContent = update.role;
      }

      if (typeof update.elapsed_seconds === "number" && window.timer?.setElapsed) {
        window.timer.setElapsed(update.elapsed_seconds);
      }

      // ===== Players list / selects / кнопки по ролям =====
      let self = null;

      if (Array.isArray(update.players)) {
        const playerList = document.getElementById("players-list");
        if (playerList) playerList.innerHTML = "";

        const receiverSelect = document.getElementById("receiver");
        if (receiverSelect && !window.isObserver) receiverSelect.innerHTML = "";

        update.players.forEach(p => {
          // список игроков
          if (!p.is_observer) {
            if (playerList) {
              const div = document.createElement("div");
              div.classList.add("player-card");
              div.style.cssText = "display:flex;justify-content:space-between;align-items:center;padding:12px;border:1px solid #dee2e6;border-radius:8px;background:#ffffff;";
              div.innerHTML = `
                <div>
                  <strong>Имя:</strong> ${p.username}<br>
                  <strong>Роль:</strong> ${p.role}<br>
                  <strong>Деньги:</strong> ${p.money} 💰<br>
                  <strong>Влияние:</strong> ${p.influence} ⭐<br>
                </div>`;
              playerList.appendChild(div);
            }
          }

          // обновим селект получателей
          if (receiverSelect && p.username !== currentUsername && !p.is_observer) {
            const option = document.createElement("option");
            option.value = p.id;
            option.textContent = p.username;
            receiverSelect.appendChild(option);
          }

          // найдём текущего игрока
          if (p.username === currentUsername) {
            self = p;
            if (!p.is_observer) {
              document.getElementById("player-money").textContent = p.money;
              document.getElementById("player-influence").textContent = `${p.influence} ⭐`;
              document.getElementById("player-role").textContent = p.role;
            }
          }
        });

        // кандидаты на голосование
        window.voteCandidates = update.players
          .filter(p => !p.is_observer && p.is_active && p.username !== currentUsername)
          .map(p => ({ id: p.id, username: p.username }));

        // если модалка голосования открыта — перерисуем список
        const electionModal = document.getElementById("election-modal");
        if (electionModal && electionModal.style.display === "flex" && typeof window.renderElectionList === "function") {
          window.renderElectionList();
        }
      }

      // ===== Панель выборов (таймер/баннер) =====
      const electionBlock = document.getElementById("election-block");
      if (electionBlock) {
        const hasRemaining = (typeof update.election_remaining === "number" && update.election_remaining > 0);
        const shouldShow = !!update.is_voting || hasRemaining;
        electionBlock.style.display = shouldShow ? "flex" : "none";
      }

      const timerEl = document.getElementById("election-timer");
      if (timerEl && typeof update.election_remaining !== "undefined") {
        timerEl.textContent = formatSeconds(update.election_remaining);
      }

      const messageContainer = document.getElementById("message-container");
      let votingMsg = document.getElementById("voting-message");
      if (update.is_voting) {
        if (!votingMsg && messageContainer) {
          votingMsg = document.createElement("div");
          votingMsg.id = "voting-message";
          votingMsg.textContent = "⚠️ Внимание, идёт голосование за нового Политика!";
          Object.assign(votingMsg.style, {
            padding: "12px 20px",
            marginBottom: "10px",
            borderRadius: "6px",
            fontSize: "16px",
            color: "#333",
            backgroundColor: "#ffc107",
            boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
            textAlign: "center",
          });
          messageContainer.appendChild(votingMsg);
        }
      } else if (votingMsg) {
        votingMsg.remove();
      }

      // ===== Пауза =====
      if (typeof update.paused !== "undefined") {
        window.paused = !!update.paused;

        const pauseIndicator = document.getElementById("pause-indicator");
        if (pauseIndicator) {
          pauseIndicator.innerHTML = window.paused ? "<em>(пауза)</em>" : "";
        }
        if (window.timer) window.timer.setPaused(window.paused);
        applyPauseToButtons(window.paused);
      }

      // ===== Показываем/прячем кнопки по ролям (на основе self) =====
      {
        const upgradeBtn = document.getElementById("upgrade-role-button");
        if (upgradeBtn) {
          const canUpgrade =
            self &&
            !window.isObserver &&
            Number(self?.special_role ?? 0) === 0 &&
            Number(self?.role_id ?? 0) < 3;

          upgradeBtn.style.display = canUpgrade ? "inline-block" : "none";
        }

        const askBtn = document.getElementById("ask-question-button");
        if (askBtn) {
          const canAsk =
            self &&
            !window.isObserver &&
            Number(self?.special_role ?? 0) === 2;

          // Кнопка «Задать вопрос» у нас на отдельной строке — делаем block
          askBtn.style.display = canAsk ? "block" : "none";
        }
      }

      return;
    }

    // 3) Игра удалена
    if (data.type === "game_deleted") {
      const gameName = data.name || "Название игры";
      sessionStorage.setItem("flash_message", JSON.stringify({
        text: `Игра «${gameName}» была удалена`,
        level: "warning"
      }));
      window.location.href = data.redirect || "/games/list/";
      return;
    }
  };
}
