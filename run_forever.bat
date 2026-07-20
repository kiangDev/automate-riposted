@echo off
REM run_forever.bat
REM
REM แก้: wrapper สำหรับรัน automate_script.py แบบไม่มีคนเฝ้า -- ถ้าสคริปต์
REM เจอ error ที่กู้คืนหน้าจอไม่สำเร็จ ([FATAL]) หรือ crash กลางทาง มันจะ
REM ออกด้วย exit code 1 (ดู sys.exit() ท้ายไฟล์ automate_script.py) แทนที่
REM จะต้องรอคนมาเห็นแล้วรันใหม่เอง ตัว wrapper นี้จะรอสักครู่แล้วรันสคริปต์
REM ใหม่อัตโนมัติให้เอง ต่อจากรายการที่ทำไปแล้ว (อ่านจาก log เดิม
REM (LOG_FILENAME) ผ่าน load_processed_data() อยู่แล้วในตัวสคริปต์)
REM
REM สคริปต์จะเสร็จจริง (exit code 0) ก็ต่อเมื่อวนครบทุกแถวใน data.csv โดยไม่
REM ค้างระหว่างทาง -- ตอนนั้น wrapper จะหยุดวนลูปเอง
REM
REM ถ้า crash รัวๆ ติดกันเกิน MAX_RETRIES ครั้ง (เช่น Riposte ไม่ได้เปิดอยู่
REM เลย หรือปัญหาที่ auto recovery แก้ไม่ได้จริงๆ) จะหยุดแล้วแจ้งเตือน
REM แทนที่จะวนลูป error ไม่มีที่สิ้นสุด

setlocal enabledelayedexpansion

REM แก้: บังคับให้ทำงานที่โฟลเดอร์เดียวกับไฟล์ .bat นี้เสมอ (กัน error
REM หา automate_script.py/data.csv ไม่เจอ ถ้าเผลอรันจาก working directory
REM อื่น เช่น เปิดผ่าน shortcut หรือ Task Scheduler)
cd /d "%~dp0"

set MAX_RETRIES=30
set RETRY_DELAY_SECONDS=15
set /a attempt=0

:run
set /a attempt+=1
echo.
echo ================================================================
echo [%date% %time%] เริ่มรัน automate_script.py (ครั้งที่ %attempt%/%MAX_RETRIES%)
echo ================================================================

python automate_script.py
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% EQU 0 (
    echo.
    echo [%date% %time%] สคริปต์จบครบทุกรายการแล้ว ^(exit code 0^) -- หยุด wrapper
    goto :end
)

echo.
echo [%date% %time%] สคริปต์หยุดกลางทาง ^(exit code %EXIT_CODE%^)

if %attempt% GEQ %MAX_RETRIES% (
    echo [%date% %time%] ลองรันซ้ำครบ %MAX_RETRIES% ครั้งแล้วยัง fail อยู่ -- หยุด wrapper กรุณาตรวจสอบด้วยตนเอง
    goto :end
)

echo [%date% %time%] รอ %RETRY_DELAY_SECONDS% วินาที แล้วจะรันซ้ำอัตโนมัติ ^(รายการที่ทำไปแล้วจะไม่ทำซ้ำ อ่านจาก log เดิม^)...
timeout /t %RETRY_DELAY_SECONDS% /nobreak >nul
goto :run

:end
echo.
echo [%date% %time%] run_forever.bat จบการทำงาน
pause
