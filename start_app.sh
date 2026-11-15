#!/usr/bin/env bash
# Flame in Freefall - run this to install what is missing and open the site in your browser.
cd "$(dirname "$0")" || exit 1
PY=python3; command -v "$PY" >/dev/null 2>&1 || PY=python
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Python was not found. Install Python 3.10 or newer from https://www.python.org/downloads/ and run this again."
  exit 1
fi
if ! "$PY" -c "import streamlit, plotly, rank_bm25, sentence_transformers, yaml, pandas, numpy" >/dev/null 2>&1; then
  echo "First run: installing the required packages. This can take several minutes..."
  "$PY" -m pip install -r requirements.txt || { echo "Package installation failed."; exit 1; }
fi
echo "Starting Flame in Freefall. Your browser opens at http://localhost:8501 (Ctrl+C here stops it)."
exec "$PY" -m streamlit run app.py
