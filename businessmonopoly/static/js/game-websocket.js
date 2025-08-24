//game-websocket.js

export function initWebSocket(gameId, currentUsername) {
    const socket = new WebSocket(`ws://${window.location.host}/ws/game/${gameId}/`);
    socket.onmessage = async function (e) {
        const data = JSON.parse(e.data);

        // Персональное сообщение
        if (data.type === "personal") {
            const msg = data.message;

            if (msg.data && msg.data.kind === "question") {
              // Покажем модалку с вопросом и вариантами
              showQuestionModal(msg.data);
              return; // дальше обычные ветки не нужны
            }

            if (typeof msg === "string") {
                showMessage(msg, "info");
            } else {
                showMessage(msg.message, msg.level || "info");

                if (msg.data && msg.data.role_id !== undefined && msg.data.special_role !== undefined) {
                    const upgradeBtn = document.getElementById("upgrade-role-button");
                    if (upgradeBtn) {
                        if (msg.data.special_role === 0 && msg.data.role_id < 3) {
                            upgradeBtn.style.display = "inline-block";
                        } else {
                            upgradeBtn.style.display = "none";
                        }
                    }

                    if (msg.data.role) {
                        document.getElementById("player-role").textContent = msg.data.role;
                    }
                }
            }

            return;
        }

        // Логика для обновлении элементов игры
        if (data.type === "update") {
            const update = data.data;

            if (update.money !== undefined && !window.isObserver) {
                document.getElementById('player-money').textContent = `${update.money}`;
            }

            if (update.influence !== undefined && !window.isObserver) {
                document.getElementById('player-influence').textContent = `${update.influence} ⭐`;
            }

            if (update.role !== undefined && !window.isObserver) {
                document.getElementById('player-role').textContent = update.role;
            }

            if (typeof update.elapsed_seconds === "number" && window.timer && typeof window.timer.setElapsed === "function") {
                window.timer.setElapsed(update.elapsed_seconds);
            }

            if (update.players && Array.isArray(update.players)) {
                const playerList = document.getElementById("players-list");
                playerList.innerHTML = "";

                const receiverSelect = document.getElementById("receiver");
                if (receiverSelect && !window.isObserver) {
                    receiverSelect.innerHTML = "";
                }

                update.players.forEach(player => {
                    if (!player.is_observer) {
                        const div = document.createElement("div");
                        div.classList.add("player-card");
                        div.style.cssText = "display: flex; justify-content: space-between; align-items: center; padding: 12px; border: 1px solid #dee2e6; border-radius: 8px; background: #ffffff;";
                        div.innerHTML = `
                            <div>
                                <strong>Имя:</strong> ${player.username}<br>
                                <strong>Роль:</strong> ${player.role}<br>
                                <strong>Деньги:</strong> ${player.money} 💰<br>
                                <strong>Влияние:</strong> ${player.influence} ⭐<br>
                            </div>`;
                        playerList.appendChild(div);
                    }

                    if (receiverSelect && player.username !== currentUsername && !player.is_observer) {
                        const option = document.createElement("option");
                        option.value = player.id;
                        option.textContent = player.username;
                        receiverSelect.appendChild(option);
                    }

                    if (player.username === currentUsername && !player.is_observer) {
                        document.getElementById("player-money").textContent = player.money;
                        document.getElementById("player-influence").textContent = `${player.influence} ⭐`;
                        document.getElementById("player-role").textContent = player.role;
                    }
                });

                // ОБНОВЛЕНИЕ СПИСКА КАНДИДАТОВ ДЛЯ ГОЛОСОВАНИЯ
                window.voteCandidates = update.players
                  .filter(p => !p.is_observer && p.is_active && p.username !== currentUsername)
                  .map(p => ({ id: p.id, username: p.username }));

                // если модалка открыта — перерисовать список
                const electionModal = document.getElementById("election-modal");
                if (electionModal && electionModal.style.display === "flex"
                    && typeof window.renderElectionList === "function") {
                  window.renderElectionList();
                }
            }

            const electionBlock = document.getElementById("election-block");
            if (electionBlock) {
                // показываем, когда идёт голосование
                const hasRemaining = (typeof update.election_remaining === "number" && update.election_remaining > 0);
                const shouldShow = !!update.is_voting || hasRemaining;
                electionBlock.style.display = shouldShow ? "flex" : "none";
            }

            const el = document.getElementById("election-timer");
            if (el && typeof update.election_remaining !== "undefined") {
              el.textContent = formatSeconds(update.election_remaining);
            }

            const messageContainer = document.getElementById("message-container");
            let votingMsg = document.getElementById("voting-message");

            if (update.is_voting) {
                if (!votingMsg) {
                    votingMsg = document.createElement("div");
                    votingMsg.id = "voting-message";
                    votingMsg.textContent = "⚠️ Внимание, идёт голосование за нового Политика!";
                    votingMsg.style.padding = "12px 20px";
                    votingMsg.style.marginBottom = "10px";
                    votingMsg.style.borderRadius = "6px";
                    votingMsg.style.fontSize = "16px";
                    votingMsg.style.color = "#333";
                    votingMsg.style.backgroundColor = "#ffc107"; // warning
                    votingMsg.style.boxShadow = "0 2px 6px rgba(0,0,0,0.2)";
                    votingMsg.style.textAlign = "center";
                    messageContainer.appendChild(votingMsg);
                }
            } else {
                if (votingMsg) {
                    votingMsg.remove();
                }
            }

            if (update.paused !== undefined) {
                window.paused = update.paused;

                const pauseIndicator = document.getElementById("pause-indicator");
                if (pauseIndicator) {
                    pauseIndicator.innerHTML = update.paused ? "<em>(пауза)</em>" : "";
                }

                if (window.timer) {
                    window.timer.setPaused(update.paused);
                }
            }

        }

        // Логика при удалении игры
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
