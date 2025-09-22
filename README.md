# Guess Who - Stereotype Study

A web application for playing "Guess Who" game designed to explore unconscious bias and stereotypes through interactive gameplay.

![Game Preview](https://github.com/user-attachments/assets/ac8754fa-087a-4071-bac7-e8a5a6513b1a)

## 🎯 Purpose

This application serves as an educational tool to help users:
- Identify patterns in their questioning strategies
- Recognize potential unconscious biases
- Reflect on stereotypical assumptions
- Promote awareness of diversity and inclusion

## 🎮 How to Play

1. **Start the Game**: Click "Start New Game" to begin
2. **Select a Character**: Choose a character that the computer should try to guess
3. **Answer Questions**: The computer will ask yes/no questions to narrow down possibilities
4. **Observe Patterns**: Pay attention to which questions are asked first
5. **Reflect**: Consider whether the questions reveal any stereotypical thinking

## 🌟 Features

- **Diverse Character Set**: 12 characters representing different ethnicities, professions, ages, and backgrounds
- **Interactive Gameplay**: Point-and-click interface with visual feedback
- **Educational Focus**: Built-in reflection prompts to encourage critical thinking
- **Responsive Design**: Works on desktop and mobile devices
- **Accessibility**: Clean, high-contrast design with semantic HTML

## 🚀 Getting Started

### Prerequisites
- Modern web browser (Chrome, Firefox, Safari, Edge)
- No additional software required

### Running the Application

#### Option 1: Direct File Opening
1. Clone or download this repository
2. Open `index.html` in your web browser

#### Option 2: Local Server (Recommended)
```bash
# Navigate to the project directory
cd guesswho-stereotype

# Start a local server (Python)
python3 -m http.server 8080

# Or using Node.js
npx serve .

# Or using PHP
php -S localhost:8080
```

Then open `http://localhost:8080` in your browser.

## 📁 Project Structure

```
guesswho-stereotype/
├── index.html          # Main application page
├── styles.css          # Styling and responsive design
├── script.js           # Game logic and interactivity
├── README.md          # Project documentation
└── LICENSE            # Apache 2.0 license
```

## 🎨 Technical Details

### Character Representation
Each character includes:
- **Visual Identity**: Emoji-based avatars
- **Demographics**: Name, profession, age group, ethnicity
- **Traits**: Various attributes for questioning logic

### Question Categories
Questions are designed to potentially reveal bias in areas such as:
- Gender assumptions
- Professional stereotypes
- Age-related biases
- Appearance-based judgments

### Browser Compatibility
- Chrome 60+
- Firefox 55+
- Safari 12+
- Edge 79+

## 🔧 Customization

### Adding New Characters
Edit the `characterData` array in `script.js`:

```javascript
{
    id: 13,
    name: "Character Name",
    icon: "👤",
    traits: {
        gender: "...",
        profession: "...",
        age: "...",
        ethnicity: "...",
        // ... other traits
    }
}
```

### Modifying Questions
Update the `questionTemplates` array in `script.js` to add new question types.

## 🎓 Educational Use

This application is suitable for:
- Diversity and inclusion training
- Psychology and sociology courses
- Workplace bias awareness sessions
- Personal reflection and self-assessment

## 🤝 Contributing

We welcome contributions to improve the educational value and technical quality of this application:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Designed for educational and research purposes
- Inspired by the classic "Guess Who?" board game
- Built with accessibility and inclusion in mind
