@echo off
title Alana LLM - Iniciando...
cd /d "C:\Users\JC INFO\Documents\Alana LLM\Alana_System"

echo.
echo  Iniciando Alana LLM System...
echo.

:: Inicia o backend em janela separada
start "Alana Backend" cmd /k ".venv\Scripts\python.exe bridge.py"

:: Aguarda o servidor subir
echo  Aguardando servidor inicializar...
timeout /t 8 /nobreak > nul

:: Abre o navegador
echo  Abrindo interface...
start "" "http://localhost:8000"

exit
