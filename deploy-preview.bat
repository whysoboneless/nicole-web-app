@echo off
echo.
echo ========================================
echo   NICOLE WEB SUITE - PREVIEW DEPLOY
echo ========================================
echo.
echo Deploying to PREVIEW environment...
echo.

cd /d "%~dp0"

vercel

echo.
echo ========================================
echo   PREVIEW DEPLOYMENT COMPLETE!
echo ========================================
echo.
pause

