@echo off
echo Adding firewall rule to allow Flask on port 5000...
netsh advfirewall firewall add rule name="Flask Port 5000" dir=in action=allow protocol=TCP localport=5000 profile=any
if %errorlevel%==0 (
    echo.
    echo SUCCESS! Port 5000 is now open.
    echo.
    echo Now try opening http://10.167.72.91:5000 on your phone browser.
) else (
    echo.
    echo FAILED. Please right-click this file and select "Run as administrator"
)
echo.
pause
