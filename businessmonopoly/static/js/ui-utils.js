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
