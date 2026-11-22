@echo off
rem One-time Cloudflare login for the daily scheduled job.
rem Double-click this file (or run it in a normal terminal, NOT inside the Claude app).
rem A browser opens; click "Allow". The daily job can then deploy the site.
rem Uses the public npm registry, because this PC's global npm registry setting is a broken private one.
rem Node via fnm (per-user, no admin): put its default Node on PATH when npx isn't there already.
where npx >nul 2>nul || set "PATH=%USERPROFILE%\.fnm\aliases\default;%PATH%"
set npm_config_registry=https://registry.npmjs.org/
call npx --yes wrangler@4 login
call npx --yes wrangler@4 whoami
echo.
echo Done. You can close this window.
pause
