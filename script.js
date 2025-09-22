// Game state
let gameState = {
    characters: [],
    selectedCharacter: null,
    eliminatedCharacters: new Set(),
    questionsAsked: [],
    gameStarted: false,
    currentPhase: 'setup' // setup, questioning, guessing, finished
};

// Character data with diverse representation
const characterData = [
    {
        id: 1,
        name: "Maya",
        icon: "👩🏽‍💼",
        traits: {
            gender: "female",
            profession: "doctor",
            age: "adult",
            ethnicity: "south_asian",
            hairColor: "black",
            hasGlasses: true,
            clothing: "professional"
        }
    },
    {
        id: 2,
        name: "Ahmed",
        icon: "👨🏽‍🔬",
        traits: {
            gender: "male",
            profession: "scientist",
            age: "adult",
            ethnicity: "middle_eastern",
            hairColor: "black",
            hasGlasses: false,
            clothing: "casual"
        }
    },
    {
        id: 3,
        name: "Emma",
        icon: "👩🏼‍🎨",
        traits: {
            gender: "female",
            profession: "artist",
            age: "young_adult",
            ethnicity: "white",
            hairColor: "blonde",
            hasGlasses: false,
            clothing: "creative"
        }
    },
    {
        id: 4,
        name: "Hiroshi",
        icon: "👨🏻‍💻",
        traits: {
            gender: "male",
            profession: "programmer",
            age: "adult",
            ethnicity: "east_asian",
            hairColor: "black",
            hasGlasses: true,
            clothing: "casual"
        }
    },
    {
        id: 5,
        name: "Fatima",
        icon: "👩🏽‍🏫",
        traits: {
            gender: "female",
            profession: "teacher",
            age: "middle_aged",
            ethnicity: "north_african",
            hairColor: "brown",
            hasGlasses: true,
            clothing: "professional"
        }
    },
    {
        id: 6,
        name: "Carlos",
        icon: "👨🏽‍🍳",
        traits: {
            gender: "male",
            profession: "chef",
            age: "adult",
            ethnicity: "latino",
            hairColor: "brown",
            hasGlasses: false,
            clothing: "uniform"
        }
    },
    {
        id: 7,
        name: "Aisha",
        icon: "👩🏿‍⚕️",
        traits: {
            gender: "female",
            profession: "nurse",
            age: "young_adult",
            ethnicity: "black",
            hairColor: "black",
            hasGlasses: false,
            clothing: "uniform"
        }
    },
    {
        id: 8,
        name: "David",
        icon: "👨🏼‍🎓",
        traits: {
            gender: "male",
            profession: "student",
            age: "young_adult",
            ethnicity: "white",
            hairColor: "brown",
            hasGlasses: true,
            clothing: "casual"
        }
    },
    {
        id: 9,
        name: "Priya",
        icon: "👩🏽‍💻",
        traits: {
            gender: "female",
            profession: "engineer",
            age: "adult",
            ethnicity: "south_asian",
            hairColor: "black",
            hasGlasses: false,
            clothing: "professional"
        }
    },
    {
        id: 10,
        name: "Marcus",
        icon: "👨🏿‍🎤",
        traits: {
            gender: "male",
            profession: "musician",
            age: "adult",
            ethnicity: "black",
            hairColor: "black",
            hasGlasses: false,
            clothing: "creative"
        }
    },
    {
        id: 11,
        name: "Sofia",
        icon: "👩🏻‍🔬",
        traits: {
            gender: "female",
            profession: "researcher",
            age: "middle_aged",
            ethnicity: "white",
            hairColor: "blonde",
            hasGlasses: true,
            clothing: "professional"
        }
    },
    {
        id: 12,
        name: "Jin",
        icon: "👨🏻‍🎨",
        traits: {
            gender: "male",
            profession: "designer",
            age: "young_adult",
            ethnicity: "east_asian",
            hairColor: "black",
            hasGlasses: false,
            clothing: "creative"
        }
    }
];

// Question templates that might reveal biases
const questionTemplates = [
    {
        text: "Is this person male?",
        property: "gender",
        value: "male"
    },
    {
        text: "Is this person female?",
        property: "gender",
        value: "female"
    },
    {
        text: "Does this person work in technology?",
        property: "profession",
        values: ["programmer", "engineer", "designer"]
    },
    {
        text: "Does this person work in healthcare?",
        property: "profession",
        values: ["doctor", "nurse"]
    },
    {
        text: "Does this person work in a creative field?",
        property: "profession",
        values: ["artist", "musician", "designer"]
    },
    {
        text: "Does this person wear glasses?",
        property: "hasGlasses",
        value: true
    },
    {
        text: "Is this person young (under 30)?",
        property: "age",
        value: "young_adult"
    },
    {
        text: "Does this person dress professionally?",
        property: "clothing",
        value: "professional"
    },
    {
        text: "Does this person have dark hair?",
        property: "hairColor",
        values: ["black", "brown"]
    },
    {
        text: "Is this person in education?",
        property: "profession",
        values: ["teacher", "student"]
    }
];

// DOM elements
const elements = {
    startBtn: null,
    resetBtn: null,
    characterGrid: null,
    questionPanel: null,
    questionButtons: null,
    questionResult: null,
    guessPanel: null,
    guessGrid: null,
    statusMessage: null,
    answerText: null,
    nextQuestionBtn: null,
    makeGuessBtn: null
};

// Initialize the game
function init() {
    // Get DOM elements
    elements.startBtn = document.getElementById('start-game-btn');
    elements.resetBtn = document.getElementById('reset-game-btn');
    elements.characterGrid = document.getElementById('character-grid');
    elements.questionPanel = document.getElementById('question-panel');
    elements.questionButtons = document.getElementById('question-buttons');
    elements.questionResult = document.getElementById('question-result');
    elements.guessPanel = document.getElementById('guess-panel');
    elements.guessGrid = document.getElementById('guess-grid');
    elements.statusMessage = document.getElementById('status-message');
    elements.answerText = document.getElementById('answer-text');
    elements.nextQuestionBtn = document.getElementById('next-question-btn');
    elements.makeGuessBtn = document.getElementById('make-guess-btn');

    // Add event listeners
    elements.startBtn.addEventListener('click', startGame);
    elements.resetBtn.addEventListener('click', resetGame);
    elements.nextQuestionBtn.addEventListener('click', showQuestions);
    elements.makeGuessBtn.addEventListener('click', showGuessPanel);

    // Initialize character data
    gameState.characters = [...characterData];
    
    // Show initial state
    updateDisplay();
}

function startGame() {
    gameState.gameStarted = true;
    gameState.currentPhase = 'setup';
    gameState.eliminatedCharacters.clear();
    gameState.questionsAsked = [];
    
    updateDisplay();
    renderCharacters();
    updateStatusMessage("Click on a character that the computer should try to guess!");
}

function resetGame() {
    gameState.gameStarted = false;
    gameState.currentPhase = 'setup';
    gameState.selectedCharacter = null;
    gameState.eliminatedCharacters.clear();
    gameState.questionsAsked = [];
    
    updateDisplay();
    elements.statusMessage.textContent = '';
}

function renderCharacters() {
    elements.characterGrid.innerHTML = '';
    
    gameState.characters.forEach(character => {
        const card = document.createElement('div');
        card.className = 'character-card';
        card.dataset.characterId = character.id;
        card.setAttribute('role', 'gridcell');
        card.setAttribute('tabindex', '0');
        card.setAttribute('aria-label', `${character.name}, ${getTraitDescription(character)}`);
        
        if (gameState.eliminatedCharacters.has(character.id)) {
            card.classList.add('eliminated');
        }
        
        if (gameState.selectedCharacter && gameState.selectedCharacter.id === character.id) {
            card.classList.add('selected');
        }
        
        card.innerHTML = `
            <div class="character-image">${character.icon}</div>
            <div class="character-name">${character.name}</div>
            <div class="character-traits">${getTraitDescription(character)}</div>
        `;
        
        if (gameState.currentPhase === 'setup') {
            card.addEventListener('click', () => selectCharacter(character));
            card.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    selectCharacter(character);
                }
            });
        } else if (gameState.currentPhase === 'guessing') {
            card.addEventListener('click', () => makeGuess(character));
            card.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    makeGuess(character);
                }
            });
        }
        
        elements.characterGrid.appendChild(card);
    });
}

function getTraitDescription(character) {
    const profession = character.traits.profession.charAt(0).toUpperCase() + character.traits.profession.slice(1);
    const age = character.traits.age.replace('_', ' ');
    return `${profession}, ${age}`;
}

function selectCharacter(character) {
    if (gameState.currentPhase !== 'setup') return;
    
    gameState.selectedCharacter = character;
    gameState.currentPhase = 'questioning';
    
    updateDisplay();
    renderCharacters();
    renderQuestions();
    updateStatusMessage(`Great! You selected ${character.name}. Now the computer will ask questions to guess who it is.`);
}

function renderQuestions() {
    elements.questionButtons.innerHTML = '';
    
    // Filter out questions that have already been asked
    const availableQuestions = questionTemplates.filter(q => 
        !gameState.questionsAsked.some(asked => asked.text === q.text)
    );
    
    // Show a random subset of questions
    const questionsToShow = availableQuestions
        .sort(() => Math.random() - 0.5)
        .slice(0, 6);
    
    questionsToShow.forEach(question => {
        const button = document.createElement('button');
        button.className = 'question-btn';
        button.textContent = question.text;
        button.addEventListener('click', () => askQuestion(question));
        elements.questionButtons.appendChild(button);
    });
}

function askQuestion(question) {
    const answer = evaluateQuestion(question, gameState.selectedCharacter);
    gameState.questionsAsked.push({...question, answer});
    
    // Simulate computer eliminating characters based on the answer
    eliminateCharacters(question, answer);
    
    elements.answerText.textContent = `${question.text} ${answer ? 'Yes!' : 'No.'}`;
    elements.questionResult.classList.remove('hidden');
    elements.questionButtons.style.display = 'none';
    
    renderCharacters();
    
    // Check if computer should make a guess
    const remainingCharacters = gameState.characters.filter(c => !gameState.eliminatedCharacters.has(c.id));
    if (remainingCharacters.length <= 3) {
        elements.makeGuessBtn.textContent = 'Computer Makes Final Guess';
        elements.nextQuestionBtn.style.display = 'none';
    }
}

function evaluateQuestion(question, character) {
    if (question.value !== undefined) {
        return character.traits[question.property] === question.value;
    } else if (question.values) {
        return question.values.includes(character.traits[question.property]);
    }
    return false;
}

function eliminateCharacters(question, answer) {
    gameState.characters.forEach(character => {
        const characterAnswer = evaluateQuestion(question, character);
        if (characterAnswer !== answer) {
            gameState.eliminatedCharacters.add(character.id);
        }
    });
}

function showQuestions() {
    elements.questionResult.classList.add('hidden');
    elements.questionButtons.style.display = 'grid';
    renderQuestions();
}

function showGuessPanel() {
    gameState.currentPhase = 'guessing';
    updateDisplay();
    renderGuessGrid();
    updateStatusMessage("The computer is making its final guess. Click on who you think the computer will choose:");
}

function renderGuessGrid() {
    const remainingCharacters = gameState.characters.filter(c => !gameState.eliminatedCharacters.has(c.id));
    
    elements.guessGrid.innerHTML = '';
    remainingCharacters.forEach(character => {
        const card = document.createElement('div');
        card.className = 'character-card';
        card.innerHTML = `
            <div class="character-image">${character.icon}</div>
            <div class="character-name">${character.name}</div>
        `;
        card.addEventListener('click', () => makeGuess(character));
        elements.guessGrid.appendChild(card);
    });
}

function makeGuess(guessedCharacter) {
    const isCorrect = guessedCharacter.id === gameState.selectedCharacter.id;
    gameState.currentPhase = 'finished';
    
    if (isCorrect) {
        updateStatusMessage(`🎉 Correct! The computer successfully guessed ${gameState.selectedCharacter.name}!`);
    } else {
        updateStatusMessage(`❌ Wrong! You selected ${gameState.selectedCharacter.name}, but the computer guessed ${guessedCharacter.name}.`);
    }
    
    updateDisplay();
    
    // Show reflection prompt
    setTimeout(() => {
        const reflection = document.createElement('div');
        reflection.className = 'reflection-panel';
        reflection.style.cssText = `
            background: #fff3e0;
            border: 2px solid #ff9800;
            border-radius: 8px;
            padding: 1.5rem;
            margin-top: 1rem;
        `;
        reflection.innerHTML = `
            <h4 style="color: #f57c00; margin-bottom: 1rem;">🤔 Reflection Questions</h4>
            <ul style="color: #666; line-height: 1.6;">
                <li>What was the first question asked? Did it focus on appearance, profession, or demographics?</li>
                <li>Were there any assumptions made based on stereotypes?</li>
                <li>How might these questioning patterns reflect unconscious bias?</li>
                <li>What questions might be more neutral or fair?</li>
            </ul>
        `;
        elements.questionPanel.appendChild(reflection);
    }, 2000);
}

function updateDisplay() {
    // Show/hide panels based on game phase
    elements.startBtn.classList.toggle('hidden', gameState.gameStarted);
    elements.resetBtn.classList.toggle('hidden', !gameState.gameStarted);
    
    elements.questionPanel.classList.toggle('hidden', gameState.currentPhase !== 'questioning');
    elements.guessPanel.classList.toggle('hidden', gameState.currentPhase !== 'guessing');
    
    elements.characterGrid.classList.toggle('hidden', gameState.currentPhase === 'guessing');
}

function updateStatusMessage(message) {
    elements.statusMessage.textContent = message;
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', init);