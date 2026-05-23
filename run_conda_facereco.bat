@echo off
setlocal
cd /d "%~dp0"
call D:\anaconda3\Scripts\activate.bat D:\Anaconda_envs\envs\FaceReco
python run.py
pause
