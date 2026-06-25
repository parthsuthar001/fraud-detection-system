@echo off
REM ============================================================
REM  push_to_github.bat
REM  Run this once from inside the project folder on Windows
REM  Usage: Double-click OR run from Command Prompt
REM ============================================================

echo =============================================
echo  Fraud Detection System - GitHub Push Script
echo  Repo: parthsuthar001/fraud-detection-system
echo =============================================
echo.

REM Check git is installed
git --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo ERROR: Git not found. Download from https://git-scm.com/download/win
    pause
    exit /b 1
)

REM Initialize git repo
git init
echo [1/5] Git initialized

REM Stage all files
git add .
echo [2/5] Files staged

REM First commit
git commit -m "feat: Real-time fraud detection system with XGBoost + Grafana

- FastAPI gateway with circuit breaker pattern
- Kafka streaming pipeline (transactions-raw -> fraud-events)
- Redis sliding window velocity checks (Sorted Sets)
- XGBoost ML scoring (hybrid: 0.65 ML + 0.35 rules)
- Idempotency dedup pattern for Kafka at-least-once delivery
- PostgreSQL async persistence (asyncpg)
- Prometheus metrics + Grafana dashboard (auto-provisioned)
- Docker Compose: 11 services, health-checked startup
- GitHub Actions CI: lint + pytest on every push
- Locust load test + transaction generator script"
echo [3/5] Initial commit created

REM Add remote
git remote add origin https://github.com/parthsuthar001/fraud-detection-system.git
echo [4/5] Remote added

REM Push
echo [5/5] Pushing to GitHub...
git branch -M main
git push -u origin main

IF %ERRORLEVEL% EQU 0 (
    echo.
    echo =============================================
    echo  SUCCESS! Repo live at:
    echo  https://github.com/parthsuthar001/fraud-detection-system
    echo =============================================
) ELSE (
    echo.
    echo ERROR: Push failed. Make sure you:
    echo   1. Created the repo at https://github.com/new
    echo   2. Named it exactly: fraud-detection-system
    echo   3. Left it EMPTY (no README, no .gitignore)
    echo   4. Are logged in: git config --global user.email "your@email.com"
)

pause
