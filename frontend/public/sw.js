// Service Worker minimo — so cuida das notificacoes de mensagem importante
// (sem cache/offline, sem interceptar fetch). Precisa rodar num Service
// Worker (nao na pagina) pra poder mostrar botoes de acao ("Fechar",
// "Ir para o chat") dentro da propria notificacao do sistema operacional.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("notificationclick", (event) => {
  const dados = event.notification.data || {};
  const acao = event.action;
  event.notification.close();

  if (dados.login && dados.mensagemId) {
    event.waitUntil(
      fetch(`${self.location.origin}/api/chat/alertas/marcar-visto`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ login: dados.login, mensagem_id: dados.mensagemId }),
      }).catch(() => {})
    );
  }

  if (acao !== "fechar") {
    event.waitUntil(
      self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((lista) => {
        if (lista.length > 0) {
          lista[0].focus();
          lista[0].postMessage({ tipo: "abrir-chat" });
        } else {
          self.clients.openWindow("/");
        }
      })
    );
  }
});
