# 一键打包为单文件 exe
# 用法：powershell -ExecutionPolicy Bypass -File build_exe.ps1
# 可选：-Python "C:\path\to\python.exe"

param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "使用 Python: $Python"
& $Python -c "import PyInstaller, PySide6, openpyxl; print('环境检查通过')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "缺少依赖，请先执行：pip install -r requirements-dev.txt" -ForegroundColor Yellow
    exit 1
}

$args = @(
    "-m", "PyInstaller",
    "--noconfirm", "--clean",
    "--onefile", "--windowed", "--noupx",
    "--name", "班级排座助手",
    "--icon", "assets/app.ico",
    "--paths", $root,
    "run.py"
)

& $Python @args
if ($LASTEXITCODE -ne 0) {
    Write-Host "打包失败" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "打包完成：dist\班级排座助手.exe" -ForegroundColor Green
Write-Host "首次运行会在 exe 同级创建 data 目录保存配置。" -ForegroundColor Gray
