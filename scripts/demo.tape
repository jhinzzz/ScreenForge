# VHS Demo Recording for ScreenForge README
# Install VHS: https://github.com/charmbracelet/vhs
# Run: vhs scripts/demo.tape

Output docs/assets/demo.gif
Output docs/assets/demo.webm

Set Shell "bash"
Set FontSize 14
Set Width 1200
Set Height 600
Set Padding 20
Set Theme "Dracula"
Set TypingSpeed 50ms

# Activate venv so screenforge is on PATH
Hide
Type "source .venv/bin/activate"
Enter
Sleep 0.5s
Show

# Title
Type "# ScreenForge: Describe what to test. Watch it happen. Get a pytest script."
Enter
Sleep 1.5s

# Show the demo command
Type "screenforge --demo"
Enter
Sleep 8s

# Show the generated test file
Type "cat test_cases/web/test_auto_*.py | head -30"
Enter
Sleep 3s

# Show running the generated test
Type "# The generated pytest script is ready to run:"
Enter
Type "pytest test_cases/web/test_auto_*.py -v --alluredir=./report/allure-results"
Enter
Sleep 3s

# End
Type ""
Sleep 2s
