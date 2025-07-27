chcp 65001
@echo off
setlocal enabledelayedexpansion

:: ���Python�汾
python --version 2>&1 | findstr /C:"Python 3.11.9" >nul

if %errorlevel% equ 0 (
    echo Python 3.11.9 is installed.
    
    :: ��װ����
    pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo Error: Failed to install requirements
        exit /b 1
    )
    
    :: �������ݿ�
    python .\setup_database.py
    if !errorlevel! neq 0 (
        echo Error: Failed to setup database
        exit /b 1
    )
    
    echo All tasks completed successfully.
) else (
    echo Python 3.11.9 not found or error occurred.
    echo Opening download page...
    start "" "https://mirrors.aliyun.com/python-release/windows/python-3.11.9-amd64.exe"
    exit /b 1
)

endlocal