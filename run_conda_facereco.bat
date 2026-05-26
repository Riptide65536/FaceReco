@echo off
setlocal
cd /d "%~dp0"
call D:\anaconda3\Scripts\activate.bat D:\Anaconda_envs\envs\FaceReco
set FACE_RECO_ORT_PROVIDER=CUDA
set FACE_RECO_ENABLE_TRT=0
set FACE_RECO_STRICT_PROVIDER_PROBE=0
python run.py
pause
