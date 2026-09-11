import { useState, useEffect, useRef } from "react";
import { useAuth } from "./Login";

const API = `${window.location.protocol}//${window.location.host}`;
const VINHO = "#8B1A1A";
const AMBAR = "#D97706";
const CINZA_ESCURO = "#1E293B";
const CINZA_TXT = "#64748B";
const CINZA_LINHA = "#E2E5EA";

const SUPORTA_NOTIFICACAO = typeof window !== "undefined" && "Notification" in window;
const SUPORTA_SW = typeof navigator !== "undefined" && "serviceWorker" in navigator;

// Via Service Worker dá pra colocar botões de ação de verdade ("Fechar",
// "Ir para o chat") dentro da notificação nativa do SO — requireInteraction
// faz ela ficar na tela até a pessoa clicar em algum dos dois, não some
// sozinha. É o SW (sw.js) quem trata o clique nesses botões.
async function dispararNotificacaoNavegador(alerta, login) {
  if (!SUPORTA_NOTIFICACAO || Notification.permission !== "granted") return;
  const titulo = `🚨 ${alerta.remetente_nome} — mensagem importante`;
  const opcoes = {
    body: `${alerta.canal_nome}\n${alerta.texto}`,
    icon: "/logo_clinica_censo.png",
    tag: `chat-alerta-${alerta.id}`,
    requireInteraction: true,
  };
  if (SUPORTA_SW) {
    try {
      const reg = await navigator.serviceWorker.ready;
      await reg.showNotification(titulo, {
        ...opcoes,
        data: { mensagemId: alerta.id, login },
        actions: [
          { action: "abrir", title: "Ir para o chat" },
          { action: "fechar", title: "Fechar" },
        ],
      });
      return;
    } catch { /* cai no fallback abaixo */ }
  }
  try {
    const notif = new Notification(titulo, opcoes);
    notif.onclick = () => { window.focus(); notif.close(); };
  } catch { /* ambiente sem suporte real (ex: alguns navegadores mobile) — ignora */ }
}

// Popup global de mensagem importante — montado uma vez no topo do App,
// aparece em cima de qualquer tela do Dashboard (não só dentro do chat).
// Além do popup in-page, dispara notificação nativa do navegador (Web
// Notifications API) pra funcionar mesmo com a aba minimizada/em segundo
// plano — só não alcança se o navegador estiver totalmente fechado.
// Poll simples (sem WebSocket), consistente com o resto do app.
export default function AlertaImportante({ onAbrirChat }) {
  const { user } = useAuth();
  const [fila, setFila] = useState([]);
  const [permissaoNotif, setPermissaoNotif] = useState(SUPORTA_NOTIFICACAO ? Notification.permission : "unsupported");
  const notificadosRef = useRef(new Set());
  const login = user?.login || "";

  useEffect(() => {
    if (SUPORTA_SW) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);

  // quando a pessoa clica em "Ir para o chat" dentro da notificação nativa,
  // o Service Worker foca a aba e manda essa mensagem pra navegar até lá
  useEffect(() => {
    if (!SUPORTA_SW) return;
    function aoReceberMensagem(event) {
      if (event.data?.tipo === "abrir-chat") onAbrirChat?.();
    }
    navigator.serviceWorker.addEventListener("message", aoReceberMensagem);
    return () => navigator.serviceWorker.removeEventListener("message", aoReceberMensagem);
  }, [onAbrirChat]);

  useEffect(() => {
    if (!login) return;
    function checar() {
      fetch(`${API}/api/chat/alertas?login=${encodeURIComponent(login)}`)
        .then(r => r.json())
        .then(novos => {
          if (Array.isArray(novos) && novos.length > 0) {
            setFila(f => {
              const idsExistentes = new Set(f.map(a => a.id));
              const adicionar = novos.filter(a => !idsExistentes.has(a.id));
              return adicionar.length ? [...f, ...adicionar] : f;
            });
          }
        }).catch(() => {});
    }
    checar();
    const t = setInterval(checar, 6000);
    return () => clearInterval(t);
  }, [login]);

  // dispara a notificação nativa só na primeira vez que cada alerta entra
  // na fila — separado do fetch acima pra não duplicar em StrictMode/dev
  useEffect(() => {
    fila.forEach(a => {
      if (!notificadosRef.current.has(a.id)) {
        notificadosRef.current.add(a.id);
        dispararNotificacaoNavegador(a, login);
      }
    });
  }, [fila, login]);

  function ativarNotificacoes() {
    Notification.requestPermission().then(setPermissaoNotif).catch(() => {});
  }

  const mostrarBanner = permissaoNotif === "default";

  if (fila.length === 0) {
    if (!mostrarBanner) return null;
    return (
      <div style={{
        position: "fixed", top: 14, right: 14, zIndex: 99998,
        background: "#fff", border: `1px solid ${CINZA_LINHA}`, borderRadius: 12,
        padding: "10px 14px", boxShadow: "0 8px 24px rgba(0,0,0,0.15)",
        display: "flex", alignItems: "center", gap: 10, maxWidth: 320,
      }}>
        <span style={{ fontSize: 12.5, color: CINZA_ESCURO, lineHeight: 1.4 }}>
          Ativar notificações do navegador para receber alertas de mensagens importantes mesmo fora do Dashboard?
        </span>
        <button onClick={ativarNotificacoes} style={{
          flexShrink: 0, padding: "7px 12px", borderRadius: 8, border: "none",
          background: VINHO, color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer",
        }}>Ativar</button>
        <button onClick={() => setPermissaoNotif("dispensado")} style={{
          flexShrink: 0, padding: "7px 8px", borderRadius: 8, border: "none",
          background: "transparent", color: CINZA_TXT, fontSize: 14, cursor: "pointer", lineHeight: 1,
        }}>✕</button>
      </div>
    );
  }

  const atual = fila[0];

  function dispensar() {
    fetch(`${API}/api/chat/alertas/marcar-visto`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ login, mensagem_id: atual.id }),
    }).catch(() => {});
    setFila(f => f.slice(1));
  }

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 99999,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div style={{
        background: "#fff", borderRadius: 16, width: 420, maxWidth: "90vw", padding: 28,
        boxShadow: "0 20px 60px rgba(0,0,0,0.35)", textAlign: "center",
      }}>
        <div style={{ fontSize: 40, marginBottom: 6 }}>🚨</div>
        <div style={{ fontSize: 12, fontWeight: 800, color: AMBAR, textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 10 }}>
          Mensagem importante
        </div>
        <div style={{ fontSize: 13, color: CINZA_TXT, marginBottom: 4 }}>
          {atual.remetente_nome} · {atual.canal_nome}
        </div>
        <div style={{
          fontSize: 15, color: CINZA_ESCURO, fontWeight: 600, lineHeight: 1.5, margin: "14px 0 22px",
          background: "#FDF3E7", borderRadius: 10, padding: "14px 16px", wordBreak: "break-word",
        }}>
          {atual.texto}
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <button onClick={dispensar} style={{
            flex: 1, padding: "10px", borderRadius: 10, border: `1px solid ${CINZA_LINHA}`,
            background: "#fff", color: CINZA_TXT, fontSize: 13, fontWeight: 700, cursor: "pointer",
          }}>Fechar</button>
          <button onClick={() => { onAbrirChat?.(); dispensar(); }} style={{
            flex: 1, padding: "10px", borderRadius: 10, border: "none",
            background: VINHO, color: "#fff", fontSize: 13, fontWeight: 700, cursor: "pointer",
          }}>Ir para o chat</button>
        </div>
        {fila.length > 1 && (
          <div style={{ fontSize: 11, color: "#94A3B8", marginTop: 12 }}>
            +{fila.length - 1} outra(s) mensagem(ns) importante(s)
          </div>
        )}
      </div>
    </div>
  );
}
