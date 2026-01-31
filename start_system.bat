@echo off
title NewsPulse Orchestrator


:: --- STEP 1: START ELASTICSEARCH ---
echo [1/4] Starting Database (Elasticsearch)...
:: We use 'start' to open it in a new window so it doesn't block this script.
:: We go to the exact path you provided.
cd /d "C:\Users\anshu\Downloads\elasticsearch-9.1.2-windows-x86_64\elasticsearch-9.1.2\bin"
start "Elasticsearch DB" cmd /k "elasticsearch.bat"

:: --- STEP 2: WAIT & CHECK STATUS ---
echo [2/4] Waiting 20 seconds for Database to warm up...
:: Elasticsearch takes time to boot. We wait so the backend doesn't crash.
timeout /t 20 /nobreak

echo      Checking connection...
:: This runs your curl command to prove it's alive
curl http://localhost:9200
echo.

:: --- STEP 3: START BACKEND ---
echo [3/4] Starting Backend API...
:: Navigate to your project folder
cd /d "C:\Users\anshu\Projects\NewsPulse"
:: Using 'backend.app:app' because that is the file we created. 
:: If your file is named 'main.py', change it to 'backend.main:app'.
start "Backend API" cmd /k "uvicorn backend.app:app --reload --port 8000"

:: --- STEP 4: START FRONTEND ---
echo [4/4] Starting Frontend Dashboard...
cd /d "C:\Users\anshu\Projects\NewsPulse\frontend"
start "React Frontend" cmd /k "npm start"

echo.
echo  ALL SYSTEMS GO!
echo You can minimize this window (keep it open).
pause