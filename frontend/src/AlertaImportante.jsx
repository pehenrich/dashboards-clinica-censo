import { useState, useEffect } from "react";
import { useAuth } from "./Login";

const API = `${window.location.protocol}//${window.location.host}`;
const VINHO = "#8B1A1A";
const AMBAR = "#D97706";
const CINZA_ESCURO = "#1E293B";
const CINZA_TXT = "#64748B";
const CINZA_LINHA = "#E2E5EA";

// Popup global de mensagem importante — montado uma vez no topo do App,
// aparece em cima de qualquer tela do Dashboard (não só dentro do chat).
// Poll simples (sem WebSocket), consistente com o resto do app.
export default function AlertaImportante({ onAbrirChat }) {
  const { user } = useAuth();
  const [fila, setFila] = useState([]);
  const login = user?.login || "";

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

  if (fila.length === 0) return null;
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
