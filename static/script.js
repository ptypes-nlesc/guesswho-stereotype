function submitQuestion() {
    const q = document.getElementById("question").value;
    console.log("Player 2 question:", q);
}

function sendAnswer(ans) {
    console.log("Player 1 answer:", ans);
}

function eliminateCard(id) {
    document.getElementById("card" + id).classList.add("eliminated");
    console.log("Eliminated card:", id);
}

function submitNote() {
    const note = document.getElementById("note").value;
    console.log("Moderator note:", note);
}

