// ModuloContratos.jsx — Módulo de Contratos
//
// INSTALAÇÃO no App.jsx:
//   1. import ModuloContratos from "./ModuloContratos";
//   2. NAV: { id:"contratos", label:"Contratos", icon:"layers", color:"#0D9488", desc:"Gestão de contratos" }
//   3. RENDER_MAP: contratos: () => <ModuloContratos/>

import { useState } from "react";

const URL_CONTRATOS = "https://frolicking-pavlova-d2b8af.netlify.app/";

const C = {
  primary: "#8B1A1A",
  teal:    "#0D9488",
  text:    "#111827",
  sub:     "#6B7280",
  faint:   "#9CA3AF",
  border:  "#F3F4F6",
};

export default function ModuloContratos() {
  const [hover, setHover] = useState(false);

  const abrir = () => window.open(URL_CONTRATOS, "_blank", "noopener,noreferrer");

  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", minHeight: "60vh", gap: 32, padding: "40px 20px",
    }}>

      {/* Card principal */}
      <div style={{
        background: "#fff", borderRadius: 24, padding: "48px 56px",
        boxShadow: "0 4px 24px rgba(0,0,0,0.08), 0 0 0 1px rgba(0,0,0,0.04)",
        maxWidth: 520, width: "100%", textAlign: "center",
        borderTop: `4px solid ${C.teal}`,
      }}>

        {/* Ícone */}
        <div style={{
          width: 72, height: 72, borderRadius: 20,
          background: `${C.teal}15`,
          display: "flex", alignItems: "center", justifyContent: "center",
          margin: "0 auto 24px",
          border: `1.5px solid ${C.teal}30`,
        }}>
          <svg width="34" height="34" viewBox="0 0 24 24" fill="none"
            stroke={C.teal} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <polyline points="10 9 9 9 8 9"/>
          </svg>
        </div>

        {/* Título */}
        <div style={{ fontSize: 22, fontWeight: 800, color: C.text, marginBottom: 8 }}>
          Gestão de Contratos
        </div>
        <div style={{ fontSize: 14, color: C.sub, lineHeight: 1.6, marginBottom: 32 }}>
          Acesse o sistema de contratos da Clínica Censo para visualizar,
          gerenciar e acompanhar todos os contratos ativos.
        </div>

        {/* Botão principal */}
        <button
          onClick={abrir}
          onMouseEnter={() => setHover(true)}
          onMouseLeave={() => setHover(false)}
          style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            gap: 10, padding: "14px 32px", borderRadius: 12, border: "none",
            background: hover ? "#0a7a70" : C.teal,
            color: "#fff", fontSize: 15, fontWeight: 700, cursor: "pointer",
            width: "100%", transition: "all 0.18s",
            boxShadow: hover
              ? "0 6px 20px rgba(13,148,136,0.35)"
              : "0 2px 8px rgba(13,148,136,0.2)",
          }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
            stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
            <polyline points="15 3 21 3 21 9"/>
            <line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
          Abrir Sistema de Contratos
        </button>

        {/* URL de referência */}
        <div style={{ marginTop: 16, fontSize: 11, color: C.faint }}>
          {URL_CONTRATOS}
        </div>
      </div>

      {/* Info cards */}
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
        gap: 12, width: "100%",
      }}>
        {[
          { icon: "📋", titulo: "Contratos Ativos",   desc: "Visualize todos os contratos vigentes" },
          { icon: "🔔", titulo: "Vencimentos",         desc: "Alertas de renovação e validade" },
          { icon: "📊", titulo: "Relatórios",          desc: "Histórico e métricas de contratos" },
        ].map((item, i) => (
          <div key={i} onClick={abrir} style={{
            background: "#fff", borderRadius: 14, padding: "16px 14px",
            boxShadow: "0 1px 4px rgba(0,0,0,0.06), 0 0 0 1px rgba(0,0,0,0.04)",
            cursor: "pointer", textAlign: "center",
            transition: "all 0.15s",
          }}
            onMouseEnter={e => {
              e.currentTarget.style.transform = "translateY(-2px)";
              e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.10)";
            }}
            onMouseLeave={e => {
              e.currentTarget.style.transform = "none";
              e.currentTarget.style.boxShadow = "0 1px 4px rgba(0,0,0,0.06)";
            }}>
            <div style={{ fontSize: 22, marginBottom: 6 }}>{item.icon}</div>
            <div style={{ fontSize: 12, fontWeight: 700, color: C.text, marginBottom: 4 }}>
              {item.titulo}
            </div>
            <div style={{ fontSize: 10, color: C.faint, lineHeight: 1.4 }}>
              {item.desc}
            </div>
          </div>
        ))}
      </div>

    </div>
  );
}
