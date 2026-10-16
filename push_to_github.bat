@echo off
REM ============================================================================
REM One-Click GitHub Repository Initializer & Pusher for user: aris9952
REM Repository: https://github.com/aris9952/newsHub
REM ============================================================================

echo Initializing local Git repository for NewsHub for NVDA...
git init
git branch -M main
git add .
git commit -m "Initial release v1.0.0: NewsHub for NVDA by Aris Yohanes Elean, S.Kom"

REM Check if GitHub CLI (gh) is installed to create the repository automatically
where gh >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo Creating public repository aris9952/newsHub via GitHub CLI and pushing...
    gh repo create aris9952/newsHub --public --description "NewsHub for NVDA — Accessible multi-site news reader add-on for NVDA with full support for Kompas.com" --source=. --remote=origin --push
    echo Done! Repository is live at https://github.com/aris9952/newsHub
    pause
    exit /b 0
)

echo Adding remote origin https://github.com/aris9952/newsHub.git ...
git remote remove origin >nul 2>nul
git remote add origin https://github.com/aris9952/newsHub.git
echo Pushing to main branch...
git push -u origin main
pause
