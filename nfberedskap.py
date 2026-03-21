@echo off
echo Sjekker installasjon og starter NF Melhus Beredskap...
echo.

:: Sjekker om Python er installert
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo FEIL: Python er ikke installert eller mangler i PATH.
    pause
    exit
)

:: Installerer nødvendige pakker fra requirements.txt
echo Installerer/oppdaterer verktoy...
python -m pip install -r requirements.txt

:: Starter selve appen
echo.
echo Starter appen i nettleseren...
python -m streamlit run nfberedskap.py

pause
