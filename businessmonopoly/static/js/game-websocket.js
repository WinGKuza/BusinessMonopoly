// static/js/game-websocket.js
import { applyPauseToButtons, showQuestionModal } from "/static/js/ui-utils.js";

export function initWebSocket(gameId, currentUsername) {
  const protocol = window.location.protocol === "https:" ? "wss://" : "ws://";
  const socket = new WebSocket(protocol + window.location.host + "/ws/game/" + gameId + "/");

  socket.onmessage = (e) => {
    const data = JSON.parse(e.data);

    // ------- 1) Персональное --------
    if (data.type === "personal") {
      const msg = data.message;
      const kind = msg?.data?.kind;
      const _bankerQueue = [];
      // a) старт/скрытие выбора банкира — ТОЛЬКО модалка, без тостов
      if (kind === "banker_selection_started") {
          const cands = Array.isArray(msg.data?.candidates) ? msg.data.candidates : [];
          if (typeof window.__openBankerSelection === "function") {
            window.__openBankerSelection(cands);
          } else {
            _bankerQueue.push({ type: "open", cands });
          }
          return;
        }
        if (kind === "banker_selection_hide") {
          if (typeof window.__closeBankerSelection === "function") {
            window.__closeBankerSelection();
          } else {
            _bankerQueue.push({ type: "close" });
          }
          return;
        }

      // b) вопрос игроку
      if (kind === "question") {
        (typeof showQuestionModal === "function" ? showQuestionModal : window.showQuestionModal)?.(msg.data);
        return;
      }

      // c) отзыв по вопросу для политика
      if (kind === "question_review") {
        if (typeof window.showReviewModal === "function") {
          window.showReviewModal(msg.data, { gameId, csrf: window.csrfToken });
        }
        return;
      }

      // d) отчёт политику об ответе
      if (kind === "question_report") {
        const who = msg?.data?.player || "Игрок";
        const qn  = msg?.data?.question_id ?? "";
        let lvl = msg?.level || "info";
        let text = `${who} ответил на вопрос №${qn}.`;
        if (msg?.data?.correct === true || msg?.data?.correct === 1) {
          text = `${who} ответил верно на вопрос №${qn}.`;
          lvl = "success";
        } else if (msg?.data?.correct === false) {
          text = `${who} ответил неверно на вопрос №${qn}.`;
          lvl = "warning";
        }
        window.showMessage?.(text, lvl);
        return;
      }

      // e) обычные персоналки — тостим только если есть текст
      if (typeof msg === "string") {
        if (msg.trim()) window.showMessage?.(msg, "info");
      } else {
        const text = (msg && msg.message) ? String(msg.message) : "";
        if (text.trim()) window.showMessage?.(text, msg.level || "info");
      }
      return;
    }

    // ------- 2) Update --------
    if (data.type === "update") {
      const update = data.data;

      // деньги/влияние/роль/таймер…
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

      if (update.bank_balance !== undefined) {
        const bankEl = document.getElementById("bank-balance");
        if (bankEl) bankEl.textContent = update.bank_balance;
      }

      // список игроков + собственная роль
      let self = null;
      if (Array.isArray(update.players)) {
        const playerList = document.getElementById("players-list");
        if (playerList) playerList.innerHTML = "";
        const receiverSelect = document.getElementById("receiver");
        if (receiverSelect && !window.isObserver) receiverSelect.innerHTML = "";

        update.players.forEach(p => {
          if (!p.is_observer && playerList) {
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
          if (receiverSelect && p.username !== currentUsername && !p.is_observer) {
            if (!p.is_observer &&
                p.username !== currentUsername &&
                Number(p.special_role ?? 0) !== 2) {

              const opt = document.createElement("option");
              opt.value = "p" + p.id;   // ВАЖНО: префикс "p"
              opt.textContent = p.username;
              receiverSelect.appendChild(opt);
            }
          }
          if (p.username === currentUsername) {
            self = p;
            if (!p.is_observer) {
              document.getElementById("player-money").textContent = p.money;
              document.getElementById("player-influence").textContent = `${p.influence} ⭐`;
              document.getElementById("player-role").textContent = p.role;
            }
          }
        });

        // после обхода игроков — добавляем спец-опции
        if (receiverSelect && !window.isObserver) {
          const bankOpt = document.createElement("option");
          bankOpt.value = "bank";
          bankOpt.textContent = "Банк";
          receiverSelect.appendChild(bankOpt);

          const govOpt = document.createElement("option");
          govOpt.value = "gov";
          govOpt.textContent = "Государство";
          receiverSelect.appendChild(govOpt);
        }

        // кандидаты для модалки голосования
        window.voteCandidates = update.players
          .filter(p => !p.is_observer && p.is_active && p.username !== currentUsername)
          .map(p => ({ id: p.id, username: p.username }));

        window.currentUserIsPolitician = Number(self?.special_role ?? 0) === 2;

        const electionModal = document.getElementById("election-modal");
        if (electionModal && electionModal.style.display === "flex" && typeof window.renderElectionList === "function") {
          window.renderElectionList();
        }
      }

      // панель выборов
      const electionBlock = document.getElementById("election-block");
      if (electionBlock) {
        const hasRemaining = (typeof update.election_remaining === "number" && update.election_remaining > 0);
        electionBlock.style.display = (update.is_voting || hasRemaining) ? "flex" : "none";
      }
      const timerEl = document.getElementById("election-timer");
      if (timerEl && typeof update.election_remaining !== "undefined") {
        timerEl.textContent = formatSeconds(update.election_remaining);
      }

      // баннер «идёт голосование»
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

      // пауза
      if (typeof update.paused !== "undefined") {
        window.paused = !!update.paused;
        const pauseIndicator = document.getElementById("pause-indicator");
        if (pauseIndicator) pauseIndicator.innerHTML = window.paused ? "<em>(пауза)</em>" : "";
        if (window.timer) window.timer.setPaused(window.paused);
        applyPauseToButtons(window.paused);
      }

      // кнопки по ролям
      const upgradeBtn = document.getElementById("upgrade-role-button");
      if (upgradeBtn) {
        const canUpgrade = self && !window.isObserver && Number(self?.special_role ?? 0) === 0 && Number(self?.role_id ?? 0) < 3;
        upgradeBtn.style.display = canUpgrade ? "inline-block" : "none";
      }
      const askBtn = document.getElementById("ask-question-button");
      if (askBtn) {
        const canAsk = self && !window.isObserver && Number(self?.special_role ?? 0) === 2;
        askBtn.style.display = canAsk ? "block" : "none";
      }

      return;
    }

    // ------- 3) Удаление игры --------
    if (data.type === "game_deleted") {
      const gameName = data.name || "Название игры";
      sessionStorage.setItem("flash_message", JSON.stringify({ text: `Игра «${gameName}» была удалена`, level: "warning" }));
      window.location.href = data.redirect || "/games/list/";
      return;
    }
  };
}
