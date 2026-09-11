# Abre o Dashboard da Clinica Censo em modo "app" (sem barra de endereco/
# abas), minimizado na barra de tarefas, ao logar no Windows. Enquanto essa
# janela existir (pode ficar minimizada, nao precisa estar em foco), o
# balao de mensagem importante do chat interno (com os botoes "Fechar" e
# "Ir para o chat") funciona normalmente em cima de qualquer outro programa.
#
# Ajuste a URL abaixo se o endereco do Dashboard mudar.
$urlDashboard = "https://192.168.1.40:31000/"

$candidatos = @(
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
)
$navegador = $candidatos | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($navegador) {
    Start-Process -FilePath $navegador -ArgumentList "--app=$urlDashboard" -WindowStyle Minimized
}
