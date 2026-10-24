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

// Filas fixas de coleta (psv_cod de cada "Coleta X" em produção). Pra qualquer
// outra, usa a busca por nome (campo "Trocar fila" abaixo).
const FILAS_PADRAO = [
  { codigo: 145841, nome: "Coleta Diagnóstico" },
  { codigo: 351625, nome: "Coleta Censo Imagem" },
  { codigo: 25871, nome: "Coleta Ocupacional" },
  { codigo: 361626, nome: "Coleta CMI" },
];

export default function Coleta() {
  const { user } = useAuth();
  const login = user?.login || "";

  const [fila, setFila] = useState(FILAS_PADRAO[0]);
  const [buscaFila, setBuscaFila] = useState("");
  const [resultadosFila, setResultadosFila] = useState(null);
  const [mostrarColetados, setMostrarColetados] = useState(false);
  const [buscaOs, setBuscaOs] = useState("");
  const [resultadosOs, setResultadosOs] = useState(null);

  const [pacientes, setPacientes] = useState([]);
  const [carregandoFila, setCarregandoFila] = useState(false);
  const [selecionado, setSelecionado] = useState(null);
  const [osDetalhe, setOsDetalhe] = useState(null);
  const [carregandoOs, setCarregandoOs] = useState(false);
  const [itensMarcados, setItensMarcados] = useState({});
  const [enviando, setEnviando] = useState(false);
  const [chamando, setChamando] = useState(false);
  const [erro, setErro] = useState(null);
  const [aviso, setAviso] = useState(null);

  const carregarFila = useCallback(() => {
    if (!fila) return;
    setCarregandoFila(true);
    fetch(`${API}/api/coleta/fila?fila_psv_cod=${fila.codigo}&mostrar_coletados=${mostrarColetados}`)
      .then(r => r.json()).then(setPacientes).catch(() => setPacientes([]))
      .finally(() => setCarregandoFila(false));
  }, [fila, mostrarColetados]);

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

  // Busca manual de OS — pra achar um atendimento que não apareceu sozinho na
  // fila (ex.: paciente com mais de uma OS no dia e a desambiguação do
  // backend escolheu a errada, ou que nem passou pela senha de recepção).
  useEffect(() => {
    if (!buscaOs.trim() || buscaOs.trim().length < 2) { setResultadosOs(null); return; }
    const t = setTimeout(() => {
      fetch(`${API}/api/coleta/buscar-os?q=${encodeURIComponent(buscaOs.trim())}`)
        .then(r => r.json()).then(d => setResultadosOs(d.resultados || []))
        .catch(() => setResultadosOs([]));
    }, 300);
    return () => clearTimeout(t);
  }, [buscaOs]);

  const abrirPaciente = (p) => {
    setSelecionado(p);
    setOsDetalhe(null);
    setErro(null);
    setAviso(null);
    if (!p.os_serie) return;
    setCarregandoOs(true);
    fetch(`${API}/api/coleta/os/${p.os_serie}/${p.os_num}`)
      .then(r => r.json())
      .then(d => {
        setOsDetalhe(d);
        const marcados = {};
        d.itens.forEach(it => { marcados[it.num] = !it.coleta_dthr && it.exame_sangue === 1; });
        setItensMarcados(marcados);
      })
      .catch(() => setErro("Não foi possível carregar a OS."))
      .finally(() => setCarregandoOs(false));
  };

  const abrirOsBuscada = (r) => {
    abrirPaciente({
      pac_reg: r.pac_reg, paciente: r.paciente, nascimento: r.nascimento,
      os_serie: r.serie, os_num: r.num, chegada: null, preferencial: "N",
      chamado: 0, chamado_em: null, coletado: 0, coletado_em: null,
    });
    setBuscaOs("");
    setResultadosOs(null);
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
        body: JSON.stringify({
          serie: selecionado.os_serie, num: selecionado.os_num, itens, login,
          fila_psv_cod: fila.codigo, pac_reg: selecionado.pac_reg,
        }),
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

  const imprimirEtiqueta = (itensEspecificos) => {
    if (!selecionado) return;
    const itens = itensEspecificos || Object.keys(itensMarcados).filter(n => itensMarcados[n]).map(Number);
    const qs = itens.length > 0 ? `?itens=${itens.join(",")}` : "";
    window.open(`${API}/api/coleta/etiqueta/${selecionado.os_serie}/${selecionado.os_num}${qs}`, "_blank");
  };

  const chamarPaciente = async () => {
    if (!selecionado) return;
    setChamando(true); setErro(null); setAviso(null);
    try {
      const resp = await fetch(`${API}/api/coleta/chamar`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fila_psv_cod: fila.codigo, pac_reg: selecionado.pac_reg, login }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Erro ao chamar paciente.");
      if (!data.itens_atualizados) {
        setAviso("Paciente já havia sido chamado.");
      } else {
        setAviso("📢 Paciente chamado no painel.");
      }
      setSelecionado(prev => prev ? { ...prev, chamado: 1 } : prev);
      carregarFila();
    } catch (e) {
      setErro(String(e.message || e));
    } finally {
      setChamando(false);
    }
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

          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
            {FILAS_PADRAO.map(p => (
              <button key={p.codigo} onClick={() => { setFila(p); setSelecionado(null); setOsDetalhe(null); }} style={{
                padding: "6px 12px", borderRadius: 99, fontSize: 12, fontWeight: 700, cursor: "pointer",
                border: fila?.codigo === p.codigo ? `1.5px solid ${COR}` : "1.5px solid #E2E8F0",
                background: fila?.codigo === p.codigo ? `${COR}1A` : "#fff",
                color: fila?.codigo === p.codigo ? COR2 : "#64748B",
              }}>{p.nome}</button>
            ))}
          </div>

          <label style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10, fontSize: 12, color: "#64748B", cursor: "pointer" }}>
            <input type="checkbox" checked={mostrarColetados} onChange={e => setMostrarColetados(e.target.checked)} />
            Mostrar já coletados hoje
          </label>

          <div style={{ position: "relative", marginBottom: 12 }}>
            <input type="text" value={buscaFila} onChange={e => setBuscaFila(e.target.value)}
              placeholder="+ Outra fila (buscar por nome)..."
              style={{ width: "100%", padding: "8px 10px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 12.5, boxSizing: "border-box" }} />
            {resultadosFila !== null && (
              <div style={{
                position: "absolute", top: "100%", left: 0, right: 0, zIndex: 50, marginTop: 4,
                background: "#fff", border: "1px solid #E2E8F0", borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,.15)", maxHeight: 220, overflowY: "auto",
              }}>
                {resultadosFila.length === 0 ? (
                  <div style={{ padding: 12, fontSize: 12, color: "#94A3B8", textAlign: "center" }}>Nada encontrado.</div>
                ) : resultadosFila.map(r => (
                  <div key={r.codigo} onClick={() => { setFila({ codigo: r.codigo, nome: r.nome }); setBuscaFila(""); setResultadosFila(null); setSelecionado(null); setOsDetalhe(null); }}
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
                <div key={p.pac_reg} onClick={() => abrirPaciente(p)} style={{
                  padding: "10px 12px", borderRadius: 10, cursor: "pointer",
                  opacity: p.coletado === 1 ? 0.6 : 1,
                  border: selecionado?.pac_reg === p.pac_reg ? `2px solid ${COR}` : "1.5px solid #F1F5F9",
                  background: selecionado?.pac_reg === p.pac_reg ? `${COR}0D` : p.coletado === 1 ? "#F8FAFC" : "#FAFBFC",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>{p.paciente}</span>
                    <div style={{ display: "flex", gap: 4 }}>
                      {p.coletado === 1 && <span style={{ fontSize: 9, fontWeight: 800, color: "#059669", background: "#ECFDF5", padding: "1px 6px", borderRadius: 99 }}>✓ COLETADO</span>}
                      {p.chamado === 1 && p.coletado !== 1 && <span style={{ fontSize: 9, fontWeight: 800, color: "#0369A1", background: "#EFF6FF", padding: "1px 6px", borderRadius: 99 }}>📢 CHAMADO</span>}
                      {p.preferencial === "S" && <span style={{ fontSize: 9, fontWeight: 800, color: "#DC2626", background: "#FEF2F2", padding: "1px 6px", borderRadius: 99 }}>PREF</span>}
                    </div>
                  </div>
                  <div style={{ fontSize: 11, color: "#94A3B8" }}>
                    {p.os_serie ? `OS ${p.os_serie}-${p.os_num} · ` : "sem OS ainda · "}chegou {p.chegada}{idade(p.nascimento) != null ? ` · ${idade(p.nascimento)} anos` : ""}
                    {p.coletado === 1 && p.coletado_em ? ` · coletado ${p.coletado_em}` : (p.chamado === 1 && p.chamado_em ? ` · chamado ${p.chamado_em}` : "")}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div style={{ position: "relative", marginTop: 14 }}>
            <input type="text" value={buscaOs} onChange={e => setBuscaOs(e.target.value)}
              placeholder="Buscar OS direto (nome ou serie-num)..."
              style={{ width: "100%", padding: "8px 10px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 12.5, boxSizing: "border-box" }} />
            {resultadosOs !== null && (
              <div style={{
                position: "absolute", bottom: "100%", left: 0, right: 0, zIndex: 50, marginBottom: 4,
                background: "#fff", border: "1px solid #E2E8F0", borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,.15)", maxHeight: 220, overflowY: "auto",
              }}>
                {resultadosOs.length === 0 ? (
                  <div style={{ padding: 12, fontSize: 12, color: "#94A3B8", textAlign: "center" }}>Nada encontrado.</div>
                ) : resultadosOs.map(r => (
                  <div key={`${r.serie}-${r.num}`} onClick={() => abrirOsBuscada(r)}
                    style={{ padding: "8px 12px", cursor: "pointer", fontSize: 12.5 }}
                    onMouseEnter={e => e.currentTarget.style.background = "#EEF2FF"}
                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                    <div style={{ fontWeight: 700 }}>{r.paciente}</div>
                    <div style={{ fontSize: 11, color: "#94A3B8" }}>OS {r.serie}-{r.num} · {r.os_dthr}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>

        {/* Coluna direita: detalhe da OS */}
        <Card style={{ padding: 20, minHeight: 300 }}>
          {!selecionado ? (
            <div style={{ padding: 40, textAlign: "center", color: "#94A3B8", fontSize: 13 }}>Escolha um paciente na fila ao lado.</div>
          ) : !selecionado.os_serie ? (
            <div style={{ padding: 20 }}>
              <div style={{ fontSize: 16, fontWeight: 900, color: "#0F172A", marginBottom: 6 }}>{selecionado.paciente}</div>
              <div style={{ fontSize: 12.5, color: "#D97706", marginBottom: 16 }}>⚠ Esse paciente ainda não tem OS aberta — não dá pra receber amostra nem imprimir etiqueta até a OS existir. Ainda é possível chamar no painel.</div>
              {erro && (
                <div style={{ background: "#FEF2F2", border: "1px solid #FECACA", color: "#DC2626", borderRadius: 10, padding: "10px 14px", fontSize: 12.5, marginBottom: 12 }}>⚠ {erro}</div>
              )}
              {aviso && (
                <div style={{ background: "#ECFDF5", border: "1px solid #A7F3D0", color: "#059669", borderRadius: 10, padding: "10px 14px", fontSize: 12.5, marginBottom: 12 }}>{aviso}</div>
              )}
              <button onClick={chamarPaciente} disabled={chamando || selecionado?.chamado === 1} style={{
                padding: "9px 16px", borderRadius: 10, border: `1.5px solid ${COR}`,
                background: selecionado?.chamado === 1 ? "#F1F5F9" : "#fff", color: selecionado?.chamado === 1 ? "#94A3B8" : COR2, fontWeight: 700, fontSize: 12.5,
                cursor: (chamando || selecionado?.chamado === 1) ? "not-allowed" : "pointer",
              }}>{selecionado?.chamado === 1 ? "📢 Já chamado" : chamando ? "Chamando..." : "📢 Chamar no painel"}</button>
            </div>
          ) : carregandoOs ? (
            <div style={{ padding: 40, textAlign: "center", color: "#94A3B8", fontSize: 13 }}>Carregando OS...</div>
          ) : osDetalhe ? (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
                <div>
                  <div style={{ fontSize: 16, fontWeight: 900, color: "#0F172A" }}>
                    {osDetalhe.paciente}
                    {selecionado?.coletado === 1 && <span style={{ fontSize: 11, fontWeight: 800, color: "#059669", background: "#ECFDF5", padding: "2px 8px", borderRadius: 99, marginLeft: 8, verticalAlign: "middle" }}>✓ COLETADO {selecionado?.coletado_em || ""}</span>}
                  </div>
                  <div style={{ fontSize: 12, color: "#94A3B8" }}>
                    Nasc: {osDetalhe.nascimento} · OS {selecionado.os_serie}-{selecionado.os_num} · {osDetalhe.convenio}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button onClick={chamarPaciente} disabled={chamando || selecionado?.chamado === 1 || selecionado?.coletado === 1} style={{
                    padding: "9px 16px", borderRadius: 10, border: `1.5px solid ${COR}`,
                    background: (selecionado?.chamado === 1 || selecionado?.coletado === 1) ? "#F1F5F9" : "#fff", color: (selecionado?.chamado === 1 || selecionado?.coletado === 1) ? "#94A3B8" : COR2, fontWeight: 700, fontSize: 12.5,
                    cursor: (chamando || selecionado?.chamado === 1 || selecionado?.coletado === 1) ? "not-allowed" : "pointer",
                  }}>{selecionado?.chamado === 1 ? "📢 Já chamado" : chamando ? "Chamando..." : "📢 Chamar no painel"}</button>
                  <button onClick={imprimirEtiqueta} style={{
                    padding: "9px 16px", borderRadius: 10, border: "none",
                    background: `linear-gradient(135deg,${COR},${COR2})`, color: "#fff", fontWeight: 700, fontSize: 12.5, cursor: "pointer",
                  }}>🏷️ Imprimir etiqueta</button>
                </div>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
                {osDetalhe.itens.map(it => (
                  <div key={it.num} style={{
                    display: "flex", alignItems: "center", gap: 10, padding: "10px 12px",
                    background: "#FAFBFC", border: "1px solid #F1F5F9", borderRadius: 10,
                  }}>
                    <label style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0, cursor: "pointer" }}>
                      <input type="checkbox" checked={!!itensMarcados[it.num]} onChange={() => alternarItem(it.num)} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <span style={{ fontSize: 11, fontWeight: 800, color: COR }}>{it.cod}</span>
                        <span style={{ fontSize: 12.5, color: "#334155", marginLeft: 8 }}>{it.nome}</span>
                      </div>
                    </label>
                    {it.coleta_dthr ? (
                      <span style={{ fontSize: 10.5, fontWeight: 700, color: "#059669" }}>✓ coletado {it.coleta_dthr}</span>
                    ) : (
                      <span style={{ fontSize: 10.5, color: "#D97706" }}>aguardando</span>
                    )}
                    <button onClick={() => imprimirEtiqueta([it.num])} title="Imprimir só esta etiqueta" style={{
                      border: "none", background: "transparent", cursor: "pointer", fontSize: 13, padding: "2px 4px",
                    }}>🏷️</button>
                  </div>
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

              <button onClick={receberAmostra} disabled={enviando || selecionado?.coletado === 1} style={{
                width: "100%", padding: "14px 20px", borderRadius: 12, border: "none",
                background: (enviando || selecionado?.coletado === 1) ? "#CBD5E1" : `linear-gradient(135deg,${COR},${COR2})`,
                color: "#fff", fontSize: 14, fontWeight: 800, cursor: (enviando || selecionado?.coletado === 1) ? "not-allowed" : "pointer",
              }}>
                {selecionado?.coletado === 1 ? "✓ Já recebido" : enviando ? "Registrando..." : "✓ Receber amostra selecionada"}
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
