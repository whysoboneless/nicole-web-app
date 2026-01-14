@echo off
echo ==========================================
echo   Nicole Web Suite - Upload to VPS
echo ==========================================
echo.

set /p VPS_USER=Enter your VPS username (e.g., root): 
set /p VPS_IP=Enter your VPS IP address: 

echo.
echo Uploading to %VPS_USER%@%VPS_IP%:/var/www/nicole_web_suite/
echo This may take a few minutes...
echo.

REM Create directories on VPS first
ssh %VPS_USER%@%VPS_IP% "sudo mkdir -p /var/www/nicole_web_suite/nicole_web_suite_template && sudo chown -R %VPS_USER%:%VPS_USER% /var/www/nicole_web_suite"

REM Upload the project using rsync (handles excludes better)
echo Uploading files...
scp -r ^
    ..\app.py ^
    ..\config.py ^
    ..\config_standalone.py ^
    ..\run.py ^
    ..\requirements.txt ^
    %VPS_USER%@%VPS_IP%:/var/www/nicole_web_suite/nicole_web_suite_template/

echo Uploading core...
scp -r ..\core %VPS_USER%@%VPS_IP%:/var/www/nicole_web_suite/nicole_web_suite_template/

echo Uploading dashboard...
scp -r ..\dashboard %VPS_USER%@%VPS_IP%:/var/www/nicole_web_suite/nicole_web_suite_template/

echo Uploading services...
scp -r ..\services %VPS_USER%@%VPS_IP%:/var/www/nicole_web_suite/nicole_web_suite_template/

echo Uploading workers...
scp -r ..\workers %VPS_USER%@%VPS_IP%:/var/www/nicole_web_suite/nicole_web_suite_template/

echo Uploading templates...
scp -r ..\templates %VPS_USER%@%VPS_IP%:/var/www/nicole_web_suite/nicole_web_suite_template/

echo Uploading static...
scp -r ..\static %VPS_USER%@%VPS_IP%:/var/www/nicole_web_suite/nicole_web_suite_template/

echo Uploading deploy scripts...
scp -r ..\deploy %VPS_USER%@%VPS_IP%:/var/www/nicole_web_suite/nicole_web_suite_template/

REM Also upload parent directory dependencies (utils, services from Discord bot)
echo Uploading shared utilities from parent...
scp -r ..\..\utils %VPS_USER%@%VPS_IP%:/var/www/nicole_web_suite/
scp -r ..\..\services %VPS_USER%@%VPS_IP%:/var/www/nicole_web_suite/
scp ..\..\config.py %VPS_USER%@%VPS_IP%:/var/www/nicole_web_suite/ 2>nul
scp ..\..\database.py %VPS_USER%@%VPS_IP%:/var/www/nicole_web_suite/ 2>nul

echo.
echo ==========================================
echo   Upload Complete!
echo ==========================================
echo.
echo Next steps on your VPS:
echo.
echo 1. SSH into your VPS:
echo    ssh %VPS_USER%@%VPS_IP%
echo.
echo 2. Run the setup script:
echo    cd /var/www/nicole_web_suite/nicole_web_suite_template
echo    chmod +x deploy/setup_vps.sh
echo    ./deploy/setup_vps.sh
echo.
echo 3. Configure your .env file:
echo    nano .env
echo    (Add your MONGODB_URI, DISCORD_CLIENT_ID, etc.)
echo.
echo 4. Start the service:
echo    sudo systemctl start nicole
echo    sudo systemctl enable nicole
echo.
pause
