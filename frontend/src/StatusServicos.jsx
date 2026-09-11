import { useState, useEffect, useCallback } from "react";

const API = `${window.location.protocol}//${window.location.host}`;

const CORES = {
  up:   { bg: "#ECFDF5", border: "#A7F3D0", texto: "#059669", ponto: "#10B981", label: "No ar" },
  down: { bg: "#FEF2F2", border: "#FECACA", texto: "#DC2626", ponto: "#EF4444", label: "Fora do ar" },
};

function CardServico({ servico }) {
  const c = CORES[servico.status] || CORES.down;
  return (
    <div style={{
      background: "#fff", borderRadius: 16, padding: "18px 20px",
      boxShadow: "0 2px 8px rgba(0,0,0,0.07), 0 0 0 1px rgba(0,0,0,0.04)",
      borderLeft: `4px solid ${c.ponto}`,
      display: "flex", flexDirection: "column", gap: 8, minWidth: 0,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <span style={{ fontSize: 14, fontWeight: 800, color: "#111827" }}>{servico.nome}</span>
        <span style={{
          display: "flex", alignItems: "center", gap: 6,
          fontSize: 11, fontWeight: 800, color: c.texto,
          background: c.bg, border: `1px solid ${c.border}`,
          borderRadius: 99, padding: "3px 10px", flexShrink: 0,
        }}>
          <span style={{
            width: 7, height: 7, borderRadius: "50%", background: c.ponto,
            boxShadow: servico.status === "up" ? `0 0 0 3px ${c.ponto}33` : "none",
          }}/>
          {c.label}
        </span>
      </div>
      <div style={{ fontSize: 12.5, color: "#64748B", overflowWrap: "anywhere" }}>{servico.detalhe}</div>
      {servico.tempo_resposta_ms != null && (
        <div style={{ fontSize: 10.5, color: "#94A3B8", fontWeight: 600 }}>{servico.tempo_resposta_ms}ms</div>
      )}
    </div>
  );
}

export default function StatusServicos() {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const carregar = useCallback(() => {
    setError(null);
    fetch(`${API}/api/status-servicos`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    carregar();
    const id = setInterval(carregar, 30000);
    return () => clearInterval(id);
  }, [carregar]);

  const servicos = data?.servicos || [];
  const total   = servicos.length;
  const noAr    = servicos.filter(s => s.status === "up").length;
  const foraAr  = total - noAr;

  return (
    <div>
      <div style={{
        background: "linear-gradient(135deg, #1E293B 0%, #334155 100%)",
        borderRadius: 20, padding: "24px 28px", marginBottom: 20,
        boxShadow: "0 8px 32px rgba(30,41,59,0.35)",
        display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 16,
      }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 900, color: "#fff", marginBottom: 4 }}>Status dos Serviços</div>
          <div style={{ fontSize: 12.5, color: "rgba(255,255,255,0.65)" }}>
            {data ? `Atualizado às ${new Date(data.checado_em).toLocaleTimeString("pt-BR")} · atualiza a cada 30s` : "Carregando..."}
          </div>
        </div>
        {total > 0 && (
          <div style={{ display: "flex", gap: 10 }}>
            <div style={{ background: "rgba(16,185,129,0.18)", borderRadius: 12, padding: "8px 16px", textAlign: "center" }}>
              <div style={{ fontSize: 20, fontWeight: 900, color: "#6EE7B7" }}>{noAr}</div>
              <div style={{ fontSize: 10, color: "rgba(255,255,255,0.7)", fontWeight: 700, textTransform: "uppercase" }}>No ar</div>
            </div>
            <div style={{ background: "rgba(239,68,68,0.18)", borderRadius: 12, padding: "8px 16px", textAlign: "center" }}>
              <div style={{ fontSize: 20, fontWeight: 900, color: "#FCA5A5" }}>{foraAr}</div>
              <div style={{ fontSize: 10, color: "rgba(255,255,255,0.7)", fontWeight: 700, textTransform: "uppercase" }}>Fora do ar</div>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div style={{ background: "#FEF2F2", border: "1.5px solid #FECACA", color: "#DC2626", borderRadius: 12, padding: "12px 16px", fontSize: 13, marginBottom: 16 }}>
          ⚠ Não foi possível carregar o status ({String(error.message || error)})
        </div>
      )}

      {loading && !data ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 14 }}>
          {[1,2,3,4,5].map(i => (
            <div key={i} style={{ height: 96, background: "linear-gradient(90deg,#F1F5F9 25%,#E2E8F0 50%,#F1F5F9 75%)", backgroundSize: "200% 100%", borderRadius: 16, animation: "shimmer 1.5s infinite" }}/>
          ))}
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 14 }}>
          {servicos.map(s => <CardServico key={s.nome} servico={s}/>)}
        </div>
      )}
    </div>
  );
}
