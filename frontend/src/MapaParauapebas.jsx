// MapaParauapebas.jsx — Mapa de calor por bairro usando Leaflet
// Substitui o componente MapaCalor no PacientesDB.jsx
//
// INSTALAÇÃO:
//   npm install leaflet react-leaflet
//
// No index.html adicione no <head>:
//   <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
//
// No PacientesDB.jsx substitua:
//   import MapaCalor from "./MapaParauapebas";   (ou cole o componente direto)

import { useEffect, useRef, useState } from "react";

const API = `${window.location.protocol}//${window.location.host}`;

// Coordenadas centrais dos bairros de Parauapebas - PA
const COORDS_BAIRROS = {
  "União":              [-6.0672, -49.9012],
  "Cidade Nova":        [-6.0591, -49.8978],
  "da Paz":             [-6.0748, -49.9085],
  "Rio Verde":          [-6.0823, -49.9034],
  "Guanabara":          [-6.0701, -49.9052],
  "Paraíso":            [-6.0756, -49.9061],
  "Esplanada":          [-6.0769, -49.9038],
  "Liberdade I":        [-6.0637, -49.9008],
  "Liberdade II":       [-6.0614, -49.8993],
  "Maranhão":           [-6.0558, -49.8971],
  "Primavera":          [-6.0543, -49.9001],
  "Morada Nova":        [-6.0682, -49.8981],
  "Jardim América":     [-6.0651, -49.8952],
  "Caetanópolis":       [-6.0633, -49.8963],
  "Linha Verde":        [-6.0619, -49.8941],
  "Parque das Nações":  [-6.0598, -49.8912],
  "Parque dos Carajás": [-6.0889, -49.9123],
  "Nova Carajás":       [-6.0721, -49.8889],
  "Apoena":             [-6.0754, -49.8874],
  "Amazônia":           [-6.0798, -49.8851],
  "Novo Brasil":        [-6.0812, -49.8832],
  "Alvorada":           [-6.0734, -49.8901],
  "Brasília":           [-6.0512, -49.8934],
  "Jardim Planalto":    [-6.0487, -49.8961],
  "Jardim Canadá":      [-6.0923, -49.9145],
  "Cidade Jardim":      [-6.0871, -49.8978],
  "Beira Rio":          [-6.0945, -49.9089],
  "Beira Rio II":       [-6.0967, -49.9067],
  "Betânia":            [-6.1023, -49.9034],
  "Habitar Feliz":      [-6.1045, -49.9012],
  "Novo Horizonte":     [-6.1067, -49.8989],
  "Vila Rica":          [-6.1089, -49.8967],
  "Vale do Sol":        [-6.1112, -49.8945],
  "FAP":                [-6.1134, -49.8923],
  "Alto Bonito":        [-6.0456, -49.9012],
  "São Lucas":          [-6.0478, -49.8945],
  "Santa Luzia":        [-6.0923, -49.8912],
  "Tropical":           [-6.0945, -49.8889],
  "Novo Viver":         [-6.0967, -49.8867],
  "Palmares II":        [-6.1189, -49.8823],
  "Palmares Sul":       [-6.1234, -49.8801],
  "Nova Vida":          [-6.0512, -49.9023],
  "Minérios":           [-6.0589, -49.8823],
  "Polo Industrial":    [-6.0623, -49.8789],
  "Polo Moveleiro":     [-6.0912, -49.9178],
  "Área Rural":         [-6.0345, -49.8756],
};

function useFetch(path, deps = {}) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    setLoading(true);
    const p = new URLSearchParams(
      Object.fromEntries(Object.entries(deps).filter(([,v]) => v != null && v !== ""))
    );
    fetch(`${API}${path}?${p}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [path, JSON.stringify(deps)]);
  return { data, loading };
}

export default function MapaParauapebas({ periodo }) {
  const mapRef    = useRef(null);
  const instanceRef = useRef(null);
  const [sel, setSel] = useState(null);
  const { data, loading } = useFetch("/api/pacientesdb/por-bairro", { periodo });

  const bairros = data || [];
  const max = bairros[0]?.total || 1;

  // Cor por intensidade: azul claro → vermelho escuro
  const corBolha = (total) => {
    const t = Math.pow(Math.min(total / max, 1), 0.5);
    if (t < 0.25) return "#60A5FA";
    if (t < 0.5)  return "#F59E0B";
    if (t < 0.75) return "#EF4444";
    return "#8B1A1A";
  };

  const num = v => v != null ? Number(v).toLocaleString("pt-BR") : "—";
  const pct = v => v != null ? `${Number(v).toFixed(1)}%` : "—";

  useEffect(() => {
    if (!mapRef.current || bairros.length === 0) return;

    // Carrega Leaflet dinamicamente
    const loadLeaflet = async () => {
      // CSS
      if (!document.getElementById("leaflet-css")) {
        const link = document.createElement("link");
        link.id   = "leaflet-css";
        link.rel  = "stylesheet";
        link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
        document.head.appendChild(link);
      }

      // JS
      let L = window.L;
      if (!L) {
        await new Promise((res, rej) => {
          const s = document.createElement("script");
          s.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
          s.onload = res; s.onerror = rej;
          document.head.appendChild(s);
        });
        L = window.L;
      }

      // Inicializa ou limpa mapa
      if (instanceRef.current) {
        instanceRef.current.remove();
        instanceRef.current = null;
      }

      const map = L.map(mapRef.current, {
        center: [-6.085, -49.900],
        zoom: 12,
        zoomControl: true,
        scrollWheelZoom: true,
      });
      instanceRef.current = map;

      // Tile layer OpenStreetMap
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap contributors",
        maxZoom: 18,
      }).addTo(map);

      // Adiciona círculos por bairro
      bairros.forEach(b => {
        const coords = COORDS_BAIRROS[b.bairro];
        if (!coords) return;

        const raio   = Math.max(150, Math.sqrt(b.total / max) * 1200);
        const cor    = corBolha(b.total);
        const circle = L.circle(coords, {
          radius:      raio,
          color:       cor,
          fillColor:   cor,
          fillOpacity: 0.65,
          weight:      2,
        });

        circle.bindPopup(`
          <div style="font-family:system-ui;min-width:160px">
            <div style="font-weight:800;font-size:14px;color:#111827;margin-bottom:6px">
              📍 ${b.bairro}
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:12px">
              <div style="color:#6B7280">Atendidos</div>
              <div style="font-weight:700;color:#111827">${num(b.total)}</div>
              <div style="color:#6B7280">Novos</div>
              <div style="font-weight:700;color:#059669">${num(b.novos)}</div>
              <div style="color:#6B7280">Retorno</div>
              <div style="font-weight:700;color:#0891B2">${num(b.retorno)}</div>
              <div style="color:#6B7280">% do total</div>
              <div style="font-weight:700;color:#7C3AED">${pct(b.pct_total)}</div>
            </div>
          </div>
        `, { maxWidth: 220 });

        circle.on("click", () => setSel(b.bairro));
        circle.addTo(map);
      });

      // Marcadores de nome para os top 10
      bairros.slice(0, 10).forEach(b => {
        const coords = COORDS_BAIRROS[b.bairro];
        if (!coords) return;
        const icon = L.divIcon({
          className: "",
          html: `<div style="
            background:rgba(255,255,255,0.92);
            border:1.5px solid #E5E7EB;
            border-radius:6px;
            padding:2px 6px;
            font-size:10px;
            font-weight:700;
            color:#111827;
            white-space:nowrap;
            box-shadow:0 1px 4px rgba(0,0,0,0.15);
            pointer-events:none;
          ">${b.bairro} · ${num(b.total)}</div>`,
          iconAnchor: [0, 0],
        });
        L.marker(coords, { icon, interactive: false }).addTo(map);
      });
    };

    loadLeaflet();

    return () => {
      if (instanceRef.current) {
        instanceRef.current.remove();
        instanceRef.current = null;
      }
    };
  }, [JSON.stringify(bairros)]);

  const detalhado = sel ? bairros.find(x => x.bairro === sel) : null;

  return (
    <div style={{
      background: "#fff", borderRadius: 16, overflow: "hidden",
      boxShadow: "0 1px 4px rgba(0,0,0,0.07), 0 0 0 1px rgba(0,0,0,0.04)",
    }}>
      {/* Header */}
      <div style={{ padding: "16px 20px 10px", display: "flex",
        alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#111827" }}>
            Mapa de Calor — Parauapebas
          </div>
          <div style={{ fontSize: 11, color: "#9CA3AF", marginTop: 2 }}>
            Distribuição de pacientes por bairro · clique para detalhar
          </div>
        </div>
        {/* Legenda */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, color: "#9CA3AF" }}>
          {[["#60A5FA","Baixo"],["#F59E0B","Médio"],["#EF4444","Alto"],["#8B1A1A","Máx"]].map(([c,l]) => (
            <div key={l} style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: c }}/>
              <span>{l}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Mapa */}
      <div style={{ position: "relative" }}>
        {loading && (
          <div style={{
            position: "absolute", inset: 0, zIndex: 999,
            background: "rgba(255,255,255,0.8)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 13, color: "#9CA3AF",
          }}>
            Carregando mapa...
          </div>
        )}
        <div ref={mapRef} style={{ height: 420, width: "100%" }}/>
      </div>

      {/* Detalhe bairro selecionado */}
      {detalhado && (
        <div style={{
          margin: "0 20px 16px",
          background: "#FEF2F2", borderRadius: 12, padding: "12px 16px",
          border: "1px solid #FECACA", display: "flex",
          flexWrap: "wrap", gap: 16, alignItems: "center",
        }}>
          <div style={{ fontWeight: 800, fontSize: 15, color: "#8B1A1A" }}>
            📍 {detalhado.bairro}
          </div>
          {[
            { l: "Atendidos", v: num(detalhado.total),       c: "#111827" },
            { l: "Novos",     v: num(detalhado.novos),       c: "#059669" },
            { l: "Retorno",   v: num(detalhado.retorno),     c: "#0891B2" },
            { l: "% do total",v: pct(detalhado.pct_total),   c: "#7C3AED" },
          ].map(({ l, v, c }) => (
            <div key={l}>
              <div style={{ fontSize: 9, color: "#9CA3AF", fontWeight: 700,
                textTransform: "uppercase" }}>{l}</div>
              <div style={{ fontSize: 18, fontWeight: 800, color: c }}>{v}</div>
            </div>
          ))}
          <button onClick={() => setSel(null)} style={{
            marginLeft: "auto", background: "none", border: "none",
            color: "#8B1A1A", fontSize: 18, cursor: "pointer",
          }}>✕</button>
        </div>
      )}
    </div>
  );
}
