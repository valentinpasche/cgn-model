@echo off
setlocal

REM Chemin vers conda.bat. A adapter selon l'installation:
REM miniconda, miniconda3, Miniconda3, anaconda3, ou chemin complet.
call "%UserProfile%\miniconda\condabin\conda.bat" activate cgnmodel
if errorlevel 1 (
    echo [ERREUR] Impossible d'activer l'environnement conda "cgnmodel".
    pause
    exit /b 1
)

REM Serveur Dash local utilise par cgnmodel-gui.
start "" "http://127.0.0.1:8050"
cgnmodel-gui
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERREUR] L'application s'est terminee avec le code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
