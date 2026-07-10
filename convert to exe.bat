@echo off
setlocal

echo [1/2] Limpiando build anterior...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

echo [2/2] Compilando AstroClicker con PyInstaller...
pyinstaller --noconfirm AstroClicker.spec

echo.
echo Build finalizado. Resultado esperado: dist\AstroClicker.exe
endlocal