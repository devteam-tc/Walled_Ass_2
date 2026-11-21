@echo off
echo ========================================================
echo   Launching Chrome with Walled DLP Extension Pre-loaded
echo ========================================================
echo.

set "CHROME_EXE=C:\Users\BayyaDivyaSri\AppData\Local\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_EXE%" (
    set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
)
if not exist "%CHROME_EXE%" (
    set "CHROME_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
)

start "" "%CHROME_EXE%" --load-extension="D:\walledai_assign2\extension" https://chatgpt.com https://www.perplexity.ai chrome://extensions

echo Chrome launched!
pause
