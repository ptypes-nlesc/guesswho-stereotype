// Text-only DOM helpers so chat/system strings are never parsed as HTML.
(function (global) {
  function appendStyled(container, style) {
    const div = document.createElement("div");
    if (style) div.style.cssText = style;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
  }

  function appendTextLine(container, text, style) {
    const div = appendStyled(container, style);
    div.textContent = text == null ? "" : String(text);
    return div;
  }

  function appendChatLine(container, role, text) {
    const div = appendStyled(container, "");
    const bold = document.createElement("b");
    bold.textContent = (role || "systeem") + ":";
    div.appendChild(bold);
    div.appendChild(document.createTextNode(" " + (text || "")));
    return div;
  }

  function appendEmLine(container, text, style) {
    const div = appendStyled(container, style);
    const em = document.createElement("em");
    em.textContent = text == null ? "" : String(text);
    div.appendChild(em);
    return div;
  }

  function appendRoundCompleteMessage(container, message) {
    const text = message || "Einde van de ronde";
    const already = Array.from(container.querySelectorAll("[data-round-complete-message]")).some(
      (el) => el.dataset.roundCompleteMessage === text
    );
    if (already) return null;
    const div = document.createElement("div");
    div.setAttribute("data-round-complete-message", text);
    div.dataset.roundCompleteMessage = text;
    div.style.cssText =
      "text-align: center; margin: 10px 0; padding: 10px; background: #ffebee; border-radius: 4px;";
    const strong = document.createElement("strong");
    strong.style.cssText = "color: #d32f2f; font-size: 1.1em;";
    strong.textContent = " " + text + " ";
    div.appendChild(strong);
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
  }

  global.DomSafe = {
    appendTextLine,
    appendChatLine,
    appendEmLine,
    appendRoundCompleteMessage,
  };
})(window);
