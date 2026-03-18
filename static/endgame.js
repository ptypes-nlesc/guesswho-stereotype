function createEndOfGameHighlighter(options) {
    const {
        appendMessage,
        cardSelector = '.card',
        messageSelector = '[data-round-complete-message]',
        autoAppendMessage = true,
        messageHtml = '<strong style="color: #d32f2f; font-size: 1.1em;"> Einde van de ronde </strong>',
        messageStyle = 'text-align: center; margin: 10px 0; padding: 10px; background: #ffebee; border-radius: 4px;'
    } = options;

    let endOfGameDisplayed = false;

    function highlightRemainingCard() {
        const remainingCard = document.querySelector(`${cardSelector}:not(.eliminated)`);
        if (remainingCard) {
            remainingCard.style.pointerEvents = 'none';
            remainingCard.style.opacity = '0.7';
            remainingCard.style.cursor = 'not-allowed';
            remainingCard.style.border = '3px solid #d32f2f';
            remainingCard.style.boxShadow = '0 0 10px rgba(211, 47, 47, 0.5)';
        }
    }

    function countRemainingCards() {
        const totalCards = document.querySelectorAll(cardSelector).length;
        const eliminatedCards = document.querySelectorAll(`${cardSelector}.eliminated`).length;
        return totalCards - eliminatedCards;
    }

    function checkEndOfGame() {
        const remaining = countRemainingCards();

        if (document.querySelector(messageSelector)) {
            endOfGameDisplayed = true;
        }

        if (remaining === 1 && !endOfGameDisplayed && autoAppendMessage) {
            endOfGameDisplayed = true;
            appendMessage(messageHtml, messageStyle);
        }

        if (remaining === 1) {
            highlightRemainingCard();
        }
    }

    return {
        countRemainingCards,
        checkEndOfGame
    };
}
