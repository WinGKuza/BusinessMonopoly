export function initGameTimer(startSeconds, isPaused) {
    let elapsed = startSeconds;
    let paused = isPaused === 'true';
    const timerElement = document.getElementById('game-timer');

    function secondsToHMS(d) {
        const h = Math.floor(d / 3600);
        const m = Math.floor((d % 3600) / 60);
        const s = Math.floor(d % 60);
        return [h, m, s].map(v => v.toString().padStart(2, '0')).join(':');
    }

    function updateTimer() {
        timerElement.innerText = secondsToHMS(elapsed);
        if (!paused) elapsed++;
    }

    setInterval(updateTimer, 1000);
    updateTimer();

    return {
        pause: () => { paused = true; },
        resume: () => { paused = false; },
        setPaused: (value) => { paused = value; },
    };
}
