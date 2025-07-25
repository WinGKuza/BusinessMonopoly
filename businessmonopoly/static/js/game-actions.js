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
            window.isObserver = data.is_observ
            Вer;
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
