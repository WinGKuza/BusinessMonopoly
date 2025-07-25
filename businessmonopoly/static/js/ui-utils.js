export function showMessage(text, type = "success") {
    const box = document.getElementById("message-box");
    if (!box) return;

    box.textContent = text;
    box.style.display = "block";
    box.style.backgroundColor = type === "success" ? "#d1e7dd" : "#f8d7da";
    box.style.color = type === "success" ? "#0f5132" : "#842029";
    box.style.border = `1px solid ${type === "success" ? "#badbcc" : "#f5c2c7"}`;

    setTimeout(() => {
        box.style.display = "none";
    }, 4000);
}
