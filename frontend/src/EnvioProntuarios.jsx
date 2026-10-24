import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./Login";

const API = `${window.location.protocol}//${window.location.host}`;
const COR = "#D97706";
const COR2 = "#92400E";
const SLA_HORAS = 24;

const STATUS_COR = {
  Pendente: { fg: "#D97706", bg: "#FFFBEB", border: "#FDE68A" },
  Enviado:  { fg: "#059669", bg: "#ECFDF5", border: "#A7F3D0" },
  Cancelado:{ fg: "#64748B", bg: "#F8FAFC", border: "#E2E8F0" },
};

const MOTIVOS = ["Enfermagem", "Cliente", "Inconsistência no ASO"];
const MOTIVO_COR = {
  "Enfermagem":              { fg: "#DB2777", bg: "#FDF2F8", border: "#FBCFE8" },
  "Cliente":                 { fg: "#2563EB", bg: "#EFF6FF", border: "#BFDBFE" },
  "Inconsistência no ASO":   { fg: "#DC2626", bg: "#FEF2F2", border: "#FECACA" },
};

const Card = ({ children, style }) => (
  <div style={{
    background: "#fff", borderRadius: 18,
    boxShadow: "0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.03)",
    ...style,
  }}>
    {children}
  </div>
);

function formatarPrazo(horasDecorridas) {
  const restantes = SLA_HORAS - horasDecorridas;
  const abs = Math.abs(restantes);
  const h = Math.floor(abs);
  const m = Math.round((abs - h) * 60);
  const txt = `${h}h${String(m).padStart(2, "0")}min`;
  if (restantes < 0) return { txt: `${txt} atrasado`, cor: "#DC2626" };
  if (restantes <= 4) return { txt: `${txt} restantes`, cor: "#DC2626" };
  if (restantes <= 12) return { txt: `${txt} restantes`, cor: "#D97706" };
  return { txt: `${txt} restantes`, cor: "#059669" };
}

function LinhaConfigEmpresa({ empresa, contato, pastas, onSalvar }) {
  const [email, setEmail] = useState(contato?.email || "");
  const [pasta, setPasta] = useState(contato?.pasta_nextcloud || "");
  const [buscaPasta, setBuscaPasta] = useState(contato?.pasta_nextcloud || "");
  const [dropdownAberto, setDropdownAberto] = useState(false);
  const [salvando, setSalvando] = useState(false);

  const sugestoes = buscaPasta.trim().length >= 2
    ? pastas.filter(p => p.toUpperCase().includes(buscaPasta.trim().toUpperCase())).slice(0, 30)
    : [];

  const salvar = async () => {
    setSalvando(true);
    await onSalvar({ empresa, email, pasta_nextcloud: pasta });
    setSalvando(false);
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr 1fr auto", gap: 8, alignItems: "center", padding: "8px 4px", borderBottom: "1px solid #F1F5F9" }}>
      <div style={{ fontSize: 12.5, fontWeight: 700, color: "#0F172A" }}>{empresa}</div>
      <input
        type="email" placeholder="e-mail@empresa.com" value={email}
        onChange={e => setEmail(e.target.value)}
        style={{ padding: "6px 8px", borderRadius: 6, border: "1.5px solid #E2E8F0", fontSize: 12 }}
      />
      <div style={{ position: "relative" }}>
        <input
          type="text" placeholder="🔎 pasta no Nextcloud..."
          value={buscaPasta}
          onChange={e => { setBuscaPasta(e.target.value); setPasta(e.target.value); setDropdownAberto(true); }}
          onFocus={() => setDropdownAberto(true)}
          onBlur={() => setTimeout(() => setDropdownAberto(false), 150)}
          style={{ padding: "6px 8px", borderRadius: 6, border: `1.5px solid ${pasta ? "#059669" : "#E2E8F0"}`, fontSize: 12, width: "100%", boxSizing: "border-box" }}
        />
        {dropdownAberto && sugestoes.length > 0 && (
          <div style={{
            position: "absolute", top: "100%", left: 0, right: 0, zIndex: 30, marginTop: 2,
            background: "#fff", border: "1px solid #E2E8F0", borderRadius: 8, boxShadow: "0 8px 24px rgba(0,0,0,.12)",
            maxHeight: 180, overflowY: "auto",
          }}>
            {sugestoes.map(p => (
              <div key={p} onMouseDown={() => { setPasta(p); setBuscaPasta(p); setDropdownAberto(false); }} style={{
                padding: "6px 10px", cursor: "pointer", fontSize: 12, borderBottom: "1px solid #F8FAFC",
              }}>{p}</div>
            ))}
          </div>
        )}
      </div>
      <button onClick={salvar} disabled={salvando} style={{
        padding: "6px 12px", borderRadius: 6, border: "none",
        background: salvando ? "#CBD5E1" : COR, color: "#fff", fontSize: 11.5, fontWeight: 700,
        cursor: salvando ? "not-allowed" : "pointer",
      }}>{salvando ? "..." : "Salvar"}</button>
    </div>
  );
}

export default function EnvioProntuarios() {
  const { user } = useAuth();
  const login = user?.login || "";

  const [itens, setItens] = useState([]);
  const [resumo, setResumo] = useState(null);
  const [filtroStatus, setFiltroStatus] = useState("Pendente");
  const [filtroData, setFiltroData] = useState("");
  const [busca, setBusca] = useState("");
  const [carregando, setCarregando] = useState(false);
  const [sincronizando, setSincronizando] = useState(false);
  const [avisoSync, setAvisoSync] = useState(null);
  const [agora, setAgora] = useState(Date.now()); // tick pro relógio ao vivo

  const [configAberto, setConfigAberto] = useState(false);
  const [carregandoConfig, setCarregandoConfig] = useState(false);
  const [empresasLista, setEmpresasLista] = useState([]);
  const [contatosPorEmpresa, setContatosPorEmpresa] = useState({});
  const [pastasNextcloud, setPastasNextcloud] = useState([]);

  const [modalAberto, setModalAberto] = useState(false);
  const [buscaPaciente, setBuscaPaciente] = useState("");
  const [resultadosPaciente, setResultadosPaciente] = useState(null);
  const [pacienteEscolhido, setPacienteEscolhido] = useState(null);
  const [empresaForm, setEmpresaForm] = useState("");
  const [obsForm, setObsForm] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(null);

  useEffect(() => {
    const t = setInterval(() => setAgora(Date.now()), 30000); // recalcula o relogio a cada 30s
    return () => clearInterval(t);
  }, []);

  const carregar = useCallback(() => {
    setCarregando(true);
    const qs = new URLSearchParams();
    if (filtroStatus) qs.set("status", filtroStatus);
    if (busca.trim()) qs.set("q", busca.trim());
    if (filtroData) qs.set("data", filtroData);
    Promise.all([
      fetch(`${API}/api/ocupacional/prontuarios?${qs}`).then(r => r.json()),
      fetch(`${API}/api/ocupacional/prontuarios/resumo`).then(r => r.json()),
    ]).then(([lista, res]) => {
      setItens(lista.prontuarios || []);
      setResumo(res);
    }).catch(() => { setItens([]); setResumo(null); })
      .finally(() => setCarregando(false));
  }, [filtroStatus, busca, filtroData]);

  useEffect(() => { carregar(); }, [carregar, agora]);

  const sincronizarHoje = async () => {
    setSincronizando(true); setAvisoSync(null);
    try {
      const qs = new URLSearchParams({ login: login || "" });
      const resp = await fetch(`${API}/api/ocupacional/prontuarios/sincronizar?${qs}`, { method: "POST" });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Erro ao sincronizar.");
      setAvisoSync(`✓ ${data.encontrados} atendimento(s) encontrado(s) hoje · ${data.novos} novo(s) adicionado(s).`);
      carregar();
    } catch (e) {
      setAvisoSync(`⚠ ${e.message || e}`);
    } finally {
      setSincronizando(false);
    }
  };

  useEffect(() => {
    if (!buscaPaciente.trim() || buscaPaciente.trim().length < 2) { setResultadosPaciente(null); return; }
    const t = setTimeout(() => {
      fetch(`${API}/api/atendimento/buscar-paciente?q=${encodeURIComponent(buscaPaciente.trim())}`)
        .then(r => r.json())
        .then(d => setResultadosPaciente(d.pacientes || []))
        .catch(() => setResultadosPaciente([]));
    }, 350);
    return () => clearTimeout(t);
  }, [buscaPaciente]);

  const abrirModal = () => {
    setBuscaPaciente(""); setResultadosPaciente(null); setPacienteEscolhido(null);
    setEmpresaForm(""); setObsForm(""); setErro(null);
    setModalAberto(true);
  };

  const salvarNovo = async () => {
    if (!pacienteEscolhido) { setErro("Selecione o paciente."); return; }
    setSalvando(true); setErro(null);
    try {
      const resp = await fetch(`${API}/api/ocupacional/prontuarios`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          paciente: pacienteEscolhido.nome,
          pac_reg: pacienteEscolhido.pac_reg,
          empresa: empresaForm.trim() || null,
          observacao: obsForm.trim() || null,
          criado_por: login,
        }),
      });
      if (!resp.ok) throw new Error((await resp.json()).detail || "Erro ao criar pendência.");
      setModalAberto(false);
      carregar();
    } catch (e) {
      setErro(String(e.message || e));
    } finally {
      setSalvando(false);
    }
  };

  const mudarStatus = async (id, novoStatus) => {
    await fetch(`${API}/api/ocupacional/prontuarios/${id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: novoStatus, atualizado_por: login }),
    });
    carregar();
  };

  const mudarMotivo = async (id, novoMotivo) => {
    await fetch(`${API}/api/ocupacional/prontuarios/${id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ motivo: novoMotivo || null, atualizado_por: login }),
    });
    carregar();
  };

  const excluir = async (id) => {
    if (!window.confirm("Excluir esse registro? Essa ação não pode ser desfeita.")) return;
    await fetch(`${API}/api/ocupacional/prontuarios/${id}`, { method: "DELETE" });
    carregar();
  };

  const abrirConfig = () => {
    setConfigAberto(true);
    setCarregandoConfig(true);
    Promise.all([
      fetch(`${API}/api/ocupacional/empresas-pendentes`).then(r => r.json()),
      fetch(`${API}/api/ocupacional/empresas-contato`).then(r => r.json()),
      fetch(`${API}/api/ocupacional/nextcloud-pastas`).then(r => r.json()),
    ]).then(([emp, contatos, pastas]) => {
      setEmpresasLista(emp.empresas || []);
      const mapa = {};
      (contatos.empresas || []).forEach(c => { mapa[c.empresa] = c; });
      setContatosPorEmpresa(mapa);
      setPastasNextcloud(pastas.pastas || []);
    }).finally(() => setCarregandoConfig(false));
  };

  const salvarContatoEmpresa = async (dados) => {
    const resp = await fetch(`${API}/api/ocupacional/empresas-contato`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(dados),
    });
    const salvo = await resp.json();
    setContatosPorEmpresa(prev => ({ ...prev, [dados.empresa]: salvo }));
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 900, color: "#0F172A" }}>📋 Gestão de Envio de Prontuários</div>
          <div style={{ fontSize: 12, color: "#94A3B8" }}>SLA de {SLA_HORAS}h por paciente, desde o momento em que entra como pendência</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={abrirConfig} title="Configurar e-mail e pasta do Nextcloud por empresa" style={{
            padding: "10px 16px", borderRadius: 10, border: "1.5px solid #E2E8F0",
            background: "#fff", color: "#64748B", fontSize: 13, fontWeight: 800, cursor: "pointer",
          }}>⚙️ Empresas</button>
          <button onClick={sincronizarHoje} disabled={sincronizando} style={{
            padding: "10px 16px", borderRadius: 10, border: `1.5px solid ${COR}`,
            background: "#fff", color: COR2, fontSize: 13, fontWeight: 800,
            cursor: sincronizando ? "not-allowed" : "pointer",
          }}>{sincronizando ? "Sincronizando..." : "🔄 Sincronizar hoje"}</button>
          <button onClick={abrirModal} style={{
            padding: "10px 18px", borderRadius: 10, border: "none",
            background: `linear-gradient(135deg,${COR},${COR2})`, color: "#fff",
            fontSize: 13, fontWeight: 800, cursor: "pointer",
          }}>+ Nova pendência</button>
        </div>
      </div>

      {avisoSync && (
        <div style={{
          background: avisoSync.startsWith("⚠") ? "#FEF2F2" : "#ECFDF5",
          border: `1px solid ${avisoSync.startsWith("⚠") ? "#FECACA" : "#A7F3D0"}`,
          color: avisoSync.startsWith("⚠") ? "#DC2626" : "#059669",
          borderRadius: 10, padding: "9px 14px", fontSize: 12.5, marginBottom: 14,
        }}>{avisoSync}</div>
      )}

      {resumo && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10, marginBottom: 16 }}>
          {[
            { label: "Pendentes", valor: resumo.por_status?.Pendente || 0, cor: "#D97706" },
            { label: "Atrasados (>24h)", valor: resumo.atrasados || 0, cor: "#DC2626" },
            { label: "Enviados", valor: resumo.por_status?.Enviado || 0, cor: "#059669" },
            { label: "Cancelados", valor: resumo.por_status?.Cancelado || 0, cor: "#64748B" },
          ].map(k => (
            <Card key={k.label} style={{ padding: "14px 16px" }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase" }}>{k.label}</div>
              <div style={{ fontSize: 24, fontWeight: 900, color: k.cor }}>{k.valor}</div>
            </Card>
          ))}
        </div>
      )}

      <Card style={{ padding: 18 }}>
        <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap", alignItems: "center" }}>
          {["Pendente", "Enviado", "Cancelado", ""].map(s => (
            <button key={s || "todos"} onClick={() => setFiltroStatus(s)} style={{
              padding: "7px 14px", borderRadius: 99, fontSize: 12, fontWeight: 700, cursor: "pointer",
              border: filtroStatus === s ? `1.5px solid ${COR}` : "1.5px solid #E2E8F0",
              background: filtroStatus === s ? `${COR}15` : "#fff",
              color: filtroStatus === s ? COR2 : "#64748B",
            }}>{s || "Todos"}</button>
          ))}
          <input
            type="date" value={filtroData} onChange={e => setFiltroData(e.target.value)}
            title="Filtrar pela data do atendimento"
            style={{ marginLeft: "auto", padding: "7px 10px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 12.5 }}
          />
          {filtroData && (
            <button onClick={() => setFiltroData("")} title="Limpar filtro de data" style={{
              border: "none", background: "transparent", color: "#94A3B8", cursor: "pointer", fontSize: 13,
            }}>✕</button>
          )}
          <input
            type="text" placeholder="🔎 Buscar paciente ou empresa..."
            value={busca} onChange={e => setBusca(e.target.value)}
            style={{ padding: "8px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 12.5, minWidth: 220 }}
          />
        </div>

        {carregando ? (
          <div style={{ padding: 30, textAlign: "center", color: "#94A3B8", fontSize: 13 }}>Carregando...</div>
        ) : itens.length === 0 ? (
          <div style={{ padding: 30, textAlign: "center", color: "#94A3B8", fontSize: 13 }}>Nenhum registro nesse filtro.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: "2px solid #F1F5F9" }}>
                  {["Paciente", "Empresa", "Atendimento", "Pendente desde", "Prazo (24h)", "Status", "Motivo", "Observação", ""].map(h => (
                    <th key={h} style={{ textAlign: "left", padding: "8px 10px", fontSize: 10.5, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {itens.map(p => {
                  const cores = STATUS_COR[p.status] || STATUS_COR.Pendente;
                  const prazo = p.status === "Pendente" ? formatarPrazo(p.horas_decorridas) : null;
                  return (
                    <tr key={p.id} style={{ borderBottom: "1px solid #F8FAFC" }}>
                      <td style={{ padding: "10px", fontWeight: 700, color: "#0F172A" }}>{p.paciente}</td>
                      <td style={{ padding: "10px", color: "#64748B" }}>{p.empresa || "—"}</td>
                      <td style={{ padding: "10px", color: "#64748B" }}>{p.data_atendimento ? p.data_atendimento.split("-").reverse().join("/") : "—"}</td>
                      <td style={{ padding: "10px", color: "#64748B" }}>{p.dthr_pendencia?.slice(0, 16).replace("T", " ")}</td>
                      <td style={{ padding: "10px" }}>
                        {prazo ? <span style={{ fontWeight: 800, color: prazo.cor }}>⏱ {prazo.txt}</span> : "—"}
                      </td>
                      <td style={{ padding: "10px" }}>
                        <select
                          value={p.status}
                          onChange={e => mudarStatus(p.id, e.target.value)}
                          style={{
                            padding: "4px 8px", borderRadius: 99, fontSize: 11.5, fontWeight: 800,
                            color: cores.fg, background: cores.bg, border: `1px solid ${cores.border}`, cursor: "pointer",
                          }}
                        >
                          <option value="Pendente">Pendente</option>
                          <option value="Enviado">Enviado</option>
                          <option value="Cancelado">Cancelado</option>
                        </select>
                      </td>
                      <td style={{ padding: "10px" }}>
                        {(() => {
                          const mc = MOTIVO_COR[p.motivo] || { fg: "#94A3B8", bg: "#F8FAFC", border: "#E2E8F0" };
                          return (
                            <select
                              value={p.motivo || ""}
                              onChange={e => mudarMotivo(p.id, e.target.value)}
                              style={{
                                padding: "4px 8px", borderRadius: 99, fontSize: 11.5, fontWeight: 800,
                                color: mc.fg, background: mc.bg, border: `1px solid ${mc.border}`, cursor: "pointer",
                              }}
                            >
                              <option value="">—</option>
                              {MOTIVOS.map(m => <option key={m} value={m}>{m}</option>)}
                            </select>
                          );
                        })()}
                      </td>
                      <td style={{ padding: "10px", color: "#94A3B8", fontSize: 12, maxWidth: 220 }}>
                        {p.link_nextcloud && (
                          <a href={p.link_nextcloud} target="_blank" rel="noreferrer" title="Abrir link do Nextcloud" style={{ marginRight: 6 }}>🔗</a>
                        )}
                        {p.observacao || "—"}
                      </td>
                      <td style={{ padding: "10px" }}>
                        <button onClick={() => excluir(p.id)} title="Excluir" style={{
                          border: "none", background: "transparent", color: "#DC2626", cursor: "pointer", fontSize: 13,
                        }}>🗑</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {modalAberto && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(17,24,39,0.6)", zIndex: 100,
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <div style={{
            background: "#fff", border: "1px solid #E2E8F0", borderRadius: 14,
            padding: 24, width: 440, display: "flex", flexDirection: "column", gap: 12,
            boxShadow: "0 20px 60px rgba(0,0,0,.25)",
          }}>
            <div style={{ fontSize: 16, fontWeight: 900, color: COR2 }}>+ Nova pendência de envio</div>

            <div style={{ position: "relative" }}>
              <label style={{ display: "block", fontSize: 10.5, fontWeight: 700, color: "#64748B", marginBottom: 4 }}>Paciente</label>
              <input
                type="text" placeholder="🔎 Nome, CPF ou nº de registro..."
                value={buscaPaciente}
                onChange={e => { setBuscaPaciente(e.target.value); setPacienteEscolhido(null); }}
                style={{ width: "100%", padding: "9px 10px", borderRadius: 8, border: `1.5px solid ${pacienteEscolhido ? "#059669" : "#E2E8F0"}`, fontSize: 13, boxSizing: "border-box" }}
              />
              {pacienteEscolhido && (
                <div style={{ fontSize: 11.5, color: "#059669", marginTop: 4, fontWeight: 700 }}>✓ {pacienteEscolhido.nome}</div>
              )}
              {resultadosPaciente && !pacienteEscolhido && (
                <div style={{
                  position: "absolute", top: "100%", left: 0, right: 0, zIndex: 20, marginTop: 4,
                  background: "#fff", border: "1px solid #E2E8F0", borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,.1)",
                  maxHeight: 200, overflowY: "auto",
                }}>
                  {resultadosPaciente.length === 0 ? (
                    <div style={{ padding: 12, fontSize: 12.5, color: "#94A3B8" }}>Nenhum paciente encontrado.</div>
                  ) : resultadosPaciente.map(p => (
                    <div key={p.pac_reg} onClick={() => { setPacienteEscolhido(p); setResultadosPaciente(null); setBuscaPaciente(p.nome); }} style={{
                      padding: "9px 12px", cursor: "pointer", borderBottom: "1px solid #F1F5F9", fontSize: 13,
                    }}>{p.nome}</div>
                  ))}
                </div>
              )}
            </div>

            <div>
              <label style={{ display: "block", fontSize: 10.5, fontWeight: 700, color: "#64748B", marginBottom: 4 }}>Empresa (opcional)</label>
              <input type="text" value={empresaForm} onChange={e => setEmpresaForm(e.target.value)}
                style={{ width: "100%", padding: "9px 10px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" }} />
            </div>

            <div>
              <label style={{ display: "block", fontSize: 10.5, fontWeight: 700, color: "#64748B", marginBottom: 4 }}>Observação (opcional)</label>
              <textarea value={obsForm} onChange={e => setObsForm(e.target.value)} rows={2}
                style={{ width: "100%", padding: "9px 10px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box", resize: "vertical", fontFamily: "inherit" }} />
            </div>

            {erro && (
              <div style={{ background: "#FEF2F2", border: "1px solid #FECACA", color: "#DC2626", borderRadius: 8, padding: "8px 12px", fontSize: 12 }}>⚠ {erro}</div>
            )}

            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => setModalAberto(false)} style={{
                flex: 1, padding: "10px", borderRadius: 8, border: "1px solid #E2E8F0",
                background: "#F9FAFB", cursor: "pointer", fontSize: 13, fontWeight: 700,
              }}>Cancelar</button>
              <button onClick={salvarNovo} disabled={salvando} style={{
                flex: 1, padding: "10px", borderRadius: 8, border: "none",
                background: salvando ? "#CBD5E1" : `linear-gradient(135deg,${COR},${COR2})`, color: "#fff",
                cursor: salvando ? "not-allowed" : "pointer", fontSize: 13, fontWeight: 700,
              }}>{salvando ? "Salvando..." : "Adicionar"}</button>
            </div>
          </div>
        </div>
      )}

      {configAberto && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(17,24,39,0.6)", zIndex: 100,
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <div style={{
            background: "#fff", border: "1px solid #E2E8F0", borderRadius: 14,
            padding: 24, width: 720, maxHeight: "82vh", display: "flex", flexDirection: "column", gap: 10,
            boxShadow: "0 20px 60px rgba(0,0,0,.25)",
          }}>
            <div style={{ fontSize: 16, fontWeight: 900, color: COR2 }}>⚙️ E-mail e pasta do Nextcloud por empresa</div>
            <div style={{ fontSize: 12, color: "#64748B", marginBottom: 4 }}>
              Configure uma vez por empresa — reaproveitado em todas as pendências dela. A pasta é escolhida
              de uma lista das pastas reais do Nextcloud (o nome nem sempre bate com o nome da empresa no Smart).
            </div>

            {carregandoConfig ? (
              <div style={{ padding: 30, textAlign: "center", color: "#94A3B8", fontSize: 13 }}>Carregando...</div>
            ) : empresasLista.length === 0 ? (
              <div style={{ padding: 30, textAlign: "center", color: "#94A3B8", fontSize: 13 }}>Nenhuma empresa nas pendências ainda.</div>
            ) : (
              <div style={{ overflowY: "auto", maxHeight: "55vh" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr 1fr auto", gap: 8, padding: "4px", fontSize: 10.5, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase" }}>
                  <div>Empresa</div><div>E-mail</div><div>Pasta no Nextcloud</div><div></div>
                </div>
                {empresasLista.map(emp => (
                  <LinhaConfigEmpresa
                    key={emp} empresa={emp} contato={contatosPorEmpresa[emp]}
                    pastas={pastasNextcloud} onSalvar={salvarContatoEmpresa}
                  />
                ))}
              </div>
            )}

            <button onClick={() => setConfigAberto(false)} style={{
              padding: "10px", borderRadius: 8, border: "1px solid #E2E8F0",
              background: "#F9FAFB", cursor: "pointer", fontSize: 13, fontWeight: 700, marginTop: 8,
            }}>Fechar</button>
          </div>
        </div>
      )}
    </div>
  );
}
