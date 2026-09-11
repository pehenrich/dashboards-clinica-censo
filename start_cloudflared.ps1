# Sobe o quick tunnel do Cloudflare apontando pro backend HTTPS:31000.
# --config NUL evita que o cloudflared use o ~/.cloudflared/config.yml (tunnel nomeado antigo,
# aponta pra porta 8000) que faz o quick tunnel devolver 404 por engano.
Set-Location C:\Dashboard
& .\cloudflared.exe tunnel --config NUL --url https://192.168.1.40:31000 --no-tls-verify *> cloudflared_out.log
