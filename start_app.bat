@echo off
rem Flame in Freefall - double-click to install what is missing and open the site in your browser.
cd /d "%~dp0"
title Flame in Freefall
if exist "%USERPROFILE%\anaconda3\Scripts\activate.bat" call "%USERPROFILE%\anaconda3\Scripts\activate.bat"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10 or newer from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during setup. Then double-click this file again.
  pause
  exit /b 1
)
python -c "import streamlit, plotly, rank_bm25, sentence_transformers, yaml, pandas, numpy" >nul 2>nul
if errorlevel 1 (
  echo First run: installing the required packages. This can take several minutes...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Package installation failed. Check your internet connection and try again.
    pause
    exit /b 1
  )
)
echo.
echo Starting Flame in Freefall. Your browser opens at http://localhost:8501
echo Keep this window open while you use the site. Close it to stop.
echo.
python -m streamlit run app.py
pause
