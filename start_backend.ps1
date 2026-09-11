# Inicia o backend com HTTPS na porta 31000
Set-Location C:\Dashboard\backend

$env:PYTHONUNBUFFERED = "1"

C:\Python312\python.exe -m uvicorn main:app `
  --host 0.0.0.0 `
  --port 31000 `
  --ssl-keyfile  ssl/dashboard_ip.key `
  --ssl-certfile ssl/dashboard_ip.crt `
  --workers 1 *> C:\Dashboard\backend_out.log
