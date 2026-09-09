import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./Login";

const API = `${window.location.protocol}//${window.location.host}`;
const COR = "#0EA5E9";
const COR2 = "#0369A1";

const Card = ({ children, style }) => (
  <div style={{
    background: "#fff", borderRadius: 18,
    boxShadow: "0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.03)",
    ...style,
  }}>
    {children}
  </div>
);

function idade(nascimentoISO) {
  if (!nascimentoISO) return null;
  const nasc = new Date(nascimentoISO);
  if (isNaN(nasc)) return null;
  const hoje = new Date();
  let anos = hoje.getFullYear() - nasc.getFullYear();
  const m = hoje.getMonth() - nasc.getMonth();
  if (m < 0 || (m === 0 && hoje.getDate() < nasc.getDate())) anos--;
  return anos >= 0 ? anos : null;
}

// Filas conhecidas com "dono" único e dominante em produção — mesmo padrão do
// autofill de executante em LancarOS.jsx. Dá pra trocar buscando outro nome.
const FILAS_PADRAO = [
  { codigo: 9126, nome: "Jessica Oliveira Ferreira (Laboratório)" },
  { codigo: 8541, nome: "Maria de Nazaré Martins Leão (Radiologia)" },
];

export default function Coleta() {
  const { user } = useAuth();
  const login = user?.login || "";

  const [fila, setFila] = useState(FILAS_PADRAO[0]);
  const [buscaFila, setBuscaFila] = useState("");
  const [resultadosFila, setResultadosFila] = useState(null);

  const [pacientes, setPacientes] = useState([]);
  const [carregandoFila, setCarregandoFila] = useState(false);
  const [selecionado, setSelecionado] = useState(null);
  const [osDetalhe, setOsDetalhe] = useState(null);
  const [carregandoOs, setCarregandoOs] = useState(false);
  const [itensMarcados, setItensMarcados] = useState({});
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState(null);
  const [aviso, setAviso] = useState(null);

  const carregarFila = useCallback(() => {
    if (!fila) return;
    setCarregandoFila(true);
    fetch(`${API}/api/coleta/fila?fila_psv_cod=${fila.codigo}`)
      .then(r => r.json()).then(setPacientes).catch(() => setPacientes([]))
      .finally(() => setCarregandoFila(false));
  }, [fila]);

  useEffect(() => { carregarFila(); }, [carregarFila]);

  useEffect(() => {
    if (!buscaFila.trim() || buscaFila.trim().length < 2) { setResultadosFila(null); return; }
    const t = setTimeout(() => {
      fetch(`${API}/api/faturamento/buscar-medico?q=${encodeURIComponent(buscaFila.trim())}`)
        .then(r => r.json()).then(d => setResultadosFila(d.resultados || []))
        .catch(() => setResultadosFila([]));
    }, 300);
    return () => clearTimeout(t);
  }, [buscaFila]);

  const abrirPaciente = (p) => {
    setSelecionado(p);
    setOsDetalhe(null);
    setErro(null);
    setAviso(null);
    setCarregandoOs(true);
    fetch(`${API}/api/coleta/os/${p.os_serie}/${p.os_num}`)
      .then(r => r.json())
      .then(d => {
        setOsDetalhe(d);
        const marcados = {};
        d.itens.forEach(it => { marcados[it.num] = !it.coleta_dthr; });
        setItensMarcados(marcados);
      })
      .catch(() => setErro("Não foi possível carregar a OS."))
      .finally(() => setCarregandoOs(false));
  };

  const alternarItem = (num) => setItensMarcados(prev => ({ ...prev, [num]: !prev[num] }));

  const receberAmostra = async () => {
    if (!selecionado || !osDetalhe) return;
    const itens = Object.keys(itensMarcados).filter(n => itensMarcados[n]).map(Number);
    if (itens.length === 0) { setErro("Selecione ao menos um item."); return; }
    setEnviando(true); setErro(null); setAviso(null);
    try {
      const resp = await fetch(`${API}/api/coleta/receber`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ serie: selecionado.os_serie, num: selecionado.os_num, itens, login }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Erro ao registrar recebimento.");
      setAviso(`✓ ${data.itens_atualizados} item(ns) marcado(s) como recebido(s).`);
      abrirPaciente(selecionado);
      carregarFila();
    } catch (e) {
      setErro(String(e.message || e));
    } finally {
      setEnviando(false);
    }
  };

  const imprimirEtiqueta = () => {
    if (!selecionado) return;
    window.open(`${API}/api/coleta/etiqueta/${selecionado.os_serie}/${selecionado.os_num}`, "_blank");
  };

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      <div style={{
        background: `linear-gradient(135deg, ${COR} 0%, ${COR2} 100%)`,
        borderRadius: 20, padding: "24px 30px", marginBottom: 18, color: "#fff",
      }}>
        <div style={{ fontSize: 20, fontWeight: 900 }}>🧪 Coleta</div>
        <div style={{ fontSize: 13, opacity: .85 }}>Fila de pacientes aguardando, recebimento de amostra e impressão de etiqueta</div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: 16, alignItems: "start" }}>
        {/* Coluna esquerda: fila */}
        <Card style={{ padding: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 800, color: "#0F172A" }}>Fila: {fila?.nome}</div>
            <button onClick={carregarFila} title="Atualizar" style={{
              border: "none", background: "transparent", color: COR, cursor: "pointer", fontSize: 13, fontWeight: 700,
            }}>⟳</button>
          </div>

          <div style={{ position: "relative", marginBottom: 12 }}>
            <input type="text" value={buscaFila} onChange={e => setBuscaFila(e.target.value)}
              placeholder="Trocar fila (buscar por nome)..."
              style={{ width: "100%", padding: "8px 10px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 12.5, boxSizing: "border-box" }} />
            {resultadosFila !== null && (
              <div style={{
                position: "absolute", top: "100%", left: 0, right: 0, zIndex: 50, marginTop: 4,
                background: "#fff", border: "1px solid #E2E8F0", borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,.15)", maxHeight: 220, overflowY: "auto",
              }}>
                {resultadosFila.length === 0 ? (
                  <div style={{ padding: 12, fontSize: 12, color: "#94A3B8", textAlign: "center" }}>Nada encontrado.</div>
                ) : resultadosFila.map(r => (
                  <div key={r.codigo} onClick={() => { setFila({ codigo: r.codigo, nome: r.nome }); setBuscaFila(""); setResultadosFila(null); }}
                    style={{ padding: "8px 12px", cursor: "pointer", fontSize: 12.5 }}
                    onMouseEnter={e => e.currentTarget.style.background = "#EEF2FF"}
                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                    {r.nome}
                  </div>
                ))}
              </div>
            )}
          </div>

          {carregandoFila ? (
            <div style={{ padding: 20, textAlign: "center", color: "#94A3B8", fontSize: 12.5 }}>Carregando...</div>
          ) : pacientes.length === 0 ? (
            <div style={{ padding: 20, textAlign: "center", color: "#94A3B8", fontSize: 12.5 }}>Ninguém aguardando nessa fila.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {pacientes.map(p => (
                <div key={`${p.os_serie}-${p.os_num}`} onClick={() => abrirPaciente(p)} style={{
                  padding: "10px 12px", borderRadius: 10, cursor: "pointer",
                  border: selecionado?.os_serie === p.os_serie && selecionado?.os_num === p.os_num ? `2px solid ${COR}` : "1.5px solid #F1F5F9",
                  background: selecionado?.os_serie === p.os_serie && selecionado?.os_num === p.os_num ? `${COR}0D` : "#FAFBFC",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>{p.paciente}</span>
                    {p.preferencial === "S" && <span style={{ fontSize: 9, fontWeight: 800, color: "#DC2626", background: "#FEF2F2", padding: "1px 6px", borderRadius: 99 }}>PREF</span>}
                  </div>
                  <div style={{ fontSize: 11, color: "#94A3B8" }}>
                    OS {p.os_serie}-{p.os_num} · chegou {p.chegada}{idade(p.nascimento) != null ? ` · ${idade(p.nascimento)} anos` : ""}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Coluna direita: detalhe da OS */}
        <Card style={{ padding: 20, minHeight: 300 }}>
          {!selecionado ? (
            <div style={{ padding: 40, textAlign: "center", color: "#94A3B8", fontSize: 13 }}>Escolha um paciente na fila ao lado.</div>
          ) : carregandoOs ? (
            <div style={{ padding: 40, textAlign: "center", color: "#94A3B8", fontSize: 13 }}>Carregando OS...</div>
          ) : osDetalhe ? (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
                <div>
                  <div style={{ fontSize: 16, fontWeight: 900, color: "#0F172A" }}>{osDetalhe.paciente}</div>
                  <div style={{ fontSize: 12, color: "#94A3B8" }}>
                    Nasc: {osDetalhe.nascimento} · OS {selecionado.os_serie}-{selecionado.os_num} · {osDetalhe.convenio}
                  </div>
                </div>
                <button onClick={imprimirEtiqueta} style={{
                  padding: "9px 16px", borderRadius: 10, border: "none",
                  background: `linear-gradient(135deg,${COR},${COR2})`, color: "#fff", fontWeight: 700, fontSize: 12.5, cursor: "pointer",
                }}>🏷️ Imprimir etiqueta</button>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
                {osDetalhe.itens.map(it => (
                  <label key={it.num} style={{
                    display: "flex", alignItems: "center", gap: 10, padding: "10px 12px",
                    background: "#FAFBFC", border: "1px solid #F1F5F9", borderRadius: 10, cursor: "pointer",
                  }}>
                    <input type="checkbox" checked={!!itensMarcados[it.num]} onChange={() => alternarItem(it.num)} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <span style={{ fontSize: 11, fontWeight: 800, color: COR }}>{it.cod}</span>
                      <span style={{ fontSize: 12.5, color: "#334155", marginLeft: 8 }}>{it.nome}</span>
                    </div>
                    {it.coleta_dthr ? (
                      <span style={{ fontSize: 10.5, fontWeight: 700, color: "#059669" }}>✓ coletado {it.coleta_dthr}</span>
                    ) : (
                      <span style={{ fontSize: 10.5, color: "#D97706" }}>aguardando</span>
                    )}
                  </label>
                ))}
              </div>

              {erro && (
                <div style={{ background: "#FEF2F2", border: "1px solid #FECACA", color: "#DC2626", borderRadius: 10, padding: "10px 14px", fontSize: 12.5, marginBottom: 12 }}>
                  ⚠ {erro}
                </div>
              )}
              {aviso && (
                <div style={{ background: "#ECFDF5", border: "1px solid #A7F3D0", color: "#059669", borderRadius: 10, padding: "10px 14px", fontSize: 12.5, marginBottom: 12 }}>
                  {aviso}
                </div>
              )}

              <button onClick={receberAmostra} disabled={enviando} style={{
                width: "100%", padding: "14px 20px", borderRadius: 12, border: "none",
                background: enviando ? "#CBD5E1" : `linear-gradient(135deg,${COR},${COR2})`,
                color: "#fff", fontSize: 14, fontWeight: 800, cursor: enviando ? "not-allowed" : "pointer",
              }}>
                {enviando ? "Registrando..." : "✓ Receber amostra selecionada"}
              </button>
            </>
          ) : (
            <div style={{ padding: 40, textAlign: "center", color: "#DC2626", fontSize: 13 }}>Não foi possível carregar a OS.</div>
          )}
        </Card>
      </div>
    </div>
  );
}
