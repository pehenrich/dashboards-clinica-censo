import { useState, useEffect } from "react";

const API = `${window.location.protocol}//${window.location.host}`;

export default function BriefingCard({ cor = "#8B1A1A", promptFn, cacheKey, disabled = false }) {
  const [texto,   setTexto]   = useState("");
  const [loading, setLoading] = useState(false);
  const [gerado,  setGerado]  = useState(false);

  useEffect(() => {
    if (!cacheKey) return;
    const salvo = sessionStorage.getItem(cacheKey);
    if (salvo) { setTexto(salvo); setGerado(true); }
    else { setTexto(""); setGerado(false); }
  }, [cacheKey]);

  const gerar = async () => {
    if (loading || disabled || !promptFn) return;
    const prompt = promptFn();
    if (!prompt) return;
    setLoading(true); setTexto(""); setGerado(false);
    try {
      const res  = await fetch(`${API}/api/briefing`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      const data = await res.json();
      const t    = data.texto || "Não foi possível gerar o briefing.";
      setTexto(t);
      if (cacheKey) sessionStorage.setItem(cacheKey, t);
      setGerado(true);
    } catch {
      setTexto("Erro ao conectar com a IA.");
      setGerado(true);
    }
    setLoading(false);
  };

  const regenerar = () => {
    if (cacheKey) sessionStorage.removeItem(cacheKey);
    setTexto(""); setGerado(false);
    setTimeout(gerar, 0);
  };

  return (
    <div style={{
      background: `linear-gradient(135deg, ${cor}2E 0%, ${cor}08 60%)`,
      border: `1.5px solid ${cor}50`,
      borderRadius: 16, padding: "18px 22px",
      boxShadow: `0 4px 14px ${cor}18, 0 1px 4px rgba(0,0,0,0.06)`,
      marginBottom: 4,
    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: texto ? 14 : 0 }}>
        <div style={{
          width: 30, height: 30, borderRadius: 9,
          background: cor, display: "flex", alignItems: "center",
          justifyContent: "center", fontSize: 15, flexShrink: 0,
        }}>✨</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 800, color: "#111827" }}>Briefing Inteligente</div>
          <div style={{ fontSize: 11, color: "#9CA3AF" }}>Análise gerada por IA · Clínica Censo</div>
        </div>
        {gerado ? (
          <button onClick={regenerar} disabled={loading} style={{
            padding: "4px 12px", borderRadius: 8,
            border: `1px solid ${cor}40`, background: "#fff",
            color: cor, fontSize: 11, fontWeight: 700, cursor: "pointer", flexShrink: 0,
          }}>↻ Atualizar</button>
        ) : (
          <button onClick={gerar} disabled={loading || disabled} style={{
            padding: "5px 14px", borderRadius: 8,
            border: "none", background: disabled ? "#E5E7EB" : cor,
            color: disabled ? "#9CA3AF" : "#fff",
            fontSize: 11, fontWeight: 700,
            cursor: disabled ? "not-allowed" : "pointer", flexShrink: 0,
          }}>
            {loading ? "⟳ Gerando..." : "✨ Gerar Briefing"}
          </button>
        )}
      </div>

      {/* Conteúdo */}
      {loading && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, paddingTop: 12 }}>
          <div style={{
            width: 18, height: 18, border: `2px solid ${cor}40`,
            borderTopColor: cor, borderRadius: "50%",
            animation: "spin 0.8s linear infinite", flexShrink: 0,
          }}/>
          <span style={{ fontSize: 13, color: "#9CA3AF" }}>Analisando dados...</span>
        </div>
      )}
      {!loading && texto && (
        <p style={{
          margin: 0, fontSize: 13.5, lineHeight: 1.7,
          color: "#374151", fontStyle: "italic",
          borderLeft: `3px solid ${cor}40`, paddingLeft: 12,
        }}>{texto}</p>
      )}
    </div>
  );
}
