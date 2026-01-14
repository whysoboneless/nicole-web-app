@echo off
echo.
echo ========================================
echo   NICOLE WEB SUITE - VERCEL DEPLOY
echo ========================================
echo.
echo Deploying to PRODUCTION...
echo.

cd /d "%~dp0"

vercel --prod

echo.
echo ========================================
echo   DEPLOYMENT COMPLETE!
echo ========================================
echo.
pause

