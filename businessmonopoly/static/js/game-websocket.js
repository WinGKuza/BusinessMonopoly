//game-websocket.js

export function initWebSocket(gameId, currentUsername) {
    const socket = new WebSocket(`ws://${window.location.host}/ws/game/${gameId}/`);
    socket.onmessage = async function (e) {
        const data = JSON.parse(e.data);
        if (data.type === "personal") {
            const msg = data.message;

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
            }

            const reelectBtn = document.getElementById("reelect-button");
            if (reelectBtn) reelectBtn.style.display = update.is_voting ? "none" : "inline-block";

            const votingNotice = document.getElementById("voting-notice");
            if (votingNotice) votingNotice.style.display = update.is_voting ? "block" : "none";

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
    };
}
