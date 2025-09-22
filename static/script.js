function submitQuestion() {
    const q = document.getElementById("question").value;
    fetch("/submit_question", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({question: q})
    });
}

function sendAnswer(ans) {
    fetch("/submit_answer", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({answer: ans})
    });
}

function eliminateCard(id) {
    document.getElementById("card" + id).classList.add("eliminated");
    fetch("/eliminate_card", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({card_id: id})
    });
}
function submitNote() {
    const note = document.getElementById("note").value;
    fetch("/submit_note", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({note: note})
    }).then(() => {
        document.getElementById("note").value = "";
    });
}

