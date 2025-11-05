// timer.js
export function initGameTimer(startSeconds, isPaused) {
    const timerElement = document.getElementById('game-timer');

    // базовое накопленное время (сек), которое уже прошло
    let baseElapsed = Number(startSeconds) || 0;

    // флаг паузы
    let paused = (isPaused === 'true' || isPaused === true);

    // момент последнего "стартанули" (монотонные милисекунды)
    let startPerf = performance.now();

    function secondsToHMS(d) {
        const h = Math.floor(d / 3600);
        const m = Math.floor((d % 3600) / 60);
        const s = Math.floor(d % 60);
        return [h, m, s].map(v => v.toString().padStart(2, '0')).join(':');
    }

    function currentElapsed() {
        if (paused) return baseElapsed;
        const delta = (performance.now() - startPerf) / 1000;
        return baseElapsed + delta;
    }

    function render() {
        const sec = Math.max(0, Math.floor(currentElapsed()));
        if (timerElement) timerElement.innerText = secondsToHMS(sec);
    }

    // тикаем чаще, чтобы не копился дрейф; UI обновится плавнее
    const intervalId = setInterval(render, 250);
    render();

    // публичные методы для внешнего управления
    function pause() {
        if (!paused) {
            baseElapsed = currentElapsed(); // зафиксировали накопленное
            paused = true;
        }
    }

    function resume() {
        if (paused) {
            paused = false;
            startPerf = performance.now(); // новая точка отсчёта
        }
    }

    function setPaused(value) { value ? pause() : resume(); }

    // ресинхронизация от бэка: аккуратно устанавливаем точное значение
    function setElapsed(seconds) {
        baseElapsed = Number(seconds) || 0;
        // не сбрасываем paused; просто обновляем базу и, если идёт — обновляем точку старта
        startPerf = performance.now();
        render();
    }

    return {
        pause,
        resume,
        setPaused,
        setElapsed,
        // чтобы можно было вручную остановить при уходе со страницы (не обязательно)
        _dispose: () => clearInterval(intervalId),
    };
}
