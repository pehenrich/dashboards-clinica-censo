# Chat do Dashboard ao ligar a máquina — deploy via GPO

Objetivo: em toda estação da unidade, ao logar no Windows, abre uma janela
minimizada do Dashboard (sem barra de endereço, parece um app). Ela fica
"viva" em segundo plano e o balão nativo de mensagem importante (com os
botões "Fechar" e "Ir para o chat") aparece por cima de qualquer programa,
mesmo com essa janela minimizada. Clicar no balão foca a janela — se
ninguém tiver logado ainda, ela mostra a tela de login (mesmo usuário/senha
do Smart, já é assim hoje).

Passos a aplicar no Domain Controller (Group Policy Management):

## 1. Publicar o script

Copie `abrir_chat_dashboard.ps1` para uma pasta acessível a todas as
estações — o padrão é dentro do SYSVOL do domínio, por exemplo:

```
\\<dominio>\SYSVOL\<dominio>\scripts\abrir_chat_dashboard.ps1
```

## 2. Rodar como script de logon do usuário (não de startup do computador)

Precisa ser logon de **usuário**, não startup de **computador** — script de
startup roda como SYSTEM antes do login, e uma janela aberta nesse contexto
não aparece na sessão do usuário.

`Group Policy Management` → editar (ou criar) a GPO aplicada às OUs das
estações → **User Configuration → Policies → Windows Settings → Scripts
(Logon/Logoff) → Logon** → aba **PowerShell Scripts** → Add → apontar para
o caminho do passo 1.

(Se a aba PowerShell Scripts não aparecer, ative antes: *Computer
Configuration → Policies → Administrative Templates → System → Scripts →
"Run Windows PowerShell scripts first"*.)

## 3. Liberar notificação automaticamente (evita clicar em "Ativar" em cada PC)

Sem isso, cada estação precisa clicar uma vez no banner "Ativar
notificações" que aparece dentro do Dashboard. Pra pular esse passo em
todas as máquinas de uma vez:

`Group Policy Management` → editar a GPO → **Computer Configuration →
Policies → Administrative Templates → Microsoft Edge → Content Settings →
"Notification allowed for these sites"** → Enabled → adicionar:

```
https://192.168.1.40:31000
```

(Precisa dos templates ADMX do Microsoft Edge instalados no servidor de
GPO — download em `https://aka.ms/EdgeEnterprise`, se ainda não estiverem.)

Se as estações usam Chrome em vez de Edge, o equivalente é
`Computer Configuration → Policies → Administrative Templates → Google →
Google Chrome → Content Settings → "Notification allowed for these sites"`
(precisa dos templates ADMX do Chrome).

### Só aparece "Internet Explorer" em Administrative Templates (Windows Server 2016)

Normal — o Windows Server 2016 não vem com os templates do Edge Chromium
instalados, só os antigos do Internet Explorer. É só instalar os templates
uma vez, no servidor onde você abre o Group Policy Management:

1. Baixe o pacote de templates em
   `https://aka.ms/EdgeEnterprise` → seção "Group Policy" → baixe o
   **"Microsoft Edge Policy Templates"**. Às vezes vem como `.cab` em vez
   de `.zip` — o Explorer do Server 2016 não abre `.cab` como pasta
   comprimida, então extrai pelo `expand.exe` (já vem no Windows, não
   precisa instalar nada). Abra o Prompt de Comando ou PowerShell como
   administrador:
   ```
   mkdir C:\EdgeADMX
   expand -F:* "C:\Users\<seu_usuario>\Downloads\MicrosoftEdgePolicyTemplates.cab" C:\EdgeADMX
   ```
   Isso extrai tudo (mantendo a estrutura de pastas) pra `C:\EdgeADMX`.
2. Dentro da pasta extraída, abra `windows\admx`. Tem os arquivos
   `msedge.admx` e `msedgeupdate.admx` (entre outros) e, dentro dela, uma
   subpasta por idioma (ex: `en-US`) com os `.adml` correspondentes.
3. Copie os `.admx` para a pasta de templates do domínio (Central Store).
   Se o domínio já tiver uma Central Store, o caminho é:
   ```
   \\<dominio>\SYSVOL\<dominio>\Policies\PolicyDefinitions\
   ```
   Se essa pasta não existir ainda (domínio sem Central Store configurada),
   crie ela copiando primeiro o conteúdo de
   `C:\Windows\PolicyDefinitions` do servidor de GPO pra esse caminho no
   SYSVOL, e só depois cole os arquivos do Edge por cima.
4. Copie os `.adml` (arquivos de idioma) pra dentro da subpasta de idioma
   correspondente dentro de `PolicyDefinitions`, ex:
   `...\PolicyDefinitions\en-US\`. Se não existir uma pasta `pt-BR` nos
   templates baixados, use os `en-US` mesmo — só muda o texto exibido no
   editor de GPO, não afeta o funcionamento.
5. Feche e reabra o Group Policy Management Console. O nó **"Microsoft
   Edge"** deve aparecer agora em Administrative Templates, tanto em
   Computer quanto em User Configuration.

## 4. Confirmar que o certificado já é confiável

O Dashboard usa HTTPS com certificado autoassinado
(`backend/ssl/dashboard_ip.crt`, válido para `45.7.24.29`, `192.168.1.40` e
`127.0.0.1`). Se as estações já acessam o Dashboard hoje sem aviso de
"conexão não seguem", esse certificado já está confiável e não precisa
mexer em nada. Caso apareça aviso, importe `dashboard_ip.crt` via
**Computer Configuration → Policies → Windows Settings → Security Settings
→ Public Key Policies → Trusted Root Certification Authorities**.

## Testando numa máquina antes de aplicar em todas

Rode o script manualmente primeiro:

```powershell
powershell.exe -ExecutionPolicy Bypass -File "\\<dominio>\SYSVOL\<dominio>\scripts\abrir_chat_dashboard.ps1"
```

Deve abrir o Dashboard minimizado na barra de tarefas. Depois, com a
notificação já liberada (passo 3) ou ativada manualmente uma vez, mande uma
mensagem importante pra esse usuário e confirme que o balão aparece mesmo
com outro programa em foco.

## Atualizar a URL

Se o IP/porta do Dashboard mudar, edite a variável `$urlDashboard` no topo
do script — não precisa reconfigurar a GPO, só sobrescrever o arquivo no
SYSVOL (aplica no próximo logon de cada usuário).
