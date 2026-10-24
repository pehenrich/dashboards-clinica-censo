import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./Login";

const API = `${window.location.protocol}//${window.location.host}`;
const COR = "#DB2777";
const COR2 = "#9D174D";

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

const CAMPOS_VITAIS = [
  { chave: "pa_sistolica",  rotulo: "PA Sistólica",  unidade: "mmHg" },
  { chave: "pa_diastolica", rotulo: "PA Diastólica", unidade: "mmHg" },
  { chave: "freq_cardiaca", rotulo: "Freq. Cardíaca", unidade: "bpm" },
  { chave: "freq_resp",     rotulo: "Freq. Respiratória", unidade: "irpm" },
  { chave: "temperatura",   rotulo: "Temperatura",   unidade: "°C" },
  { chave: "spo2",          rotulo: "Saturação O2",  unidade: "%" },
  { chave: "peso",          rotulo: "Peso",          unidade: "kg" },
  { chave: "altura",        rotulo: "Altura",        unidade: "cm" },
  { chave: "glicemia",      rotulo: "Glicemia",      unidade: "mg/dL" },
];

const CAMPOS_VAZIOS = Object.fromEntries([...CAMPOS_VITAIS.map(c => [c.chave, ""]), ["observacoes", ""]]);

const CONFIG_KEY = "enfermagem_config";
function carregarConfig() {
  try { return JSON.parse(localStorage.getItem(CONFIG_KEY)) || null; }
  catch { return null; }
}
function salvarConfigStorage(cfg) { localStorage.setItem(CONFIG_KEY, JSON.stringify(cfg)); }

export default function Enfermagem() {
  const { user } = useAuth();
  const login = user?.login || "";

  const [todasFilas, setTodasFilas] = useState([]);
  const [filaCodigos, setFilaCodigos] = useState(() => carregarConfig()?.fila_codigos || []);
  const [modalAberto, setModalAberto] = useState(false);
  const [selecaoModal, setSelecaoModal] = useState(new Set());
  const [mostrarChamados, setMostrarChamados] = useState(false);

  const [senhas, setSenhas] = useState([]);
  const [carregandoFila, setCarregandoFila] = useState(false);
  const [selecionada, setSelecionada] = useState(null); // senha escolhida na fila
  const [chamando, setChamando] = useState(false);

  const [buscaPaciente, setBuscaPaciente] = useState("");
  const [resultadosPaciente, setResultadosPaciente] = useState(null);
  const [buscandoPaciente, setBuscandoPaciente] = useState(false);
  const [pacienteEncontrado, setPacienteEncontrado] = useState(null);

  const [campos, setCampos] = useState(CAMPOS_VAZIOS);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(null);
  const [aviso, setAviso] = useState(null);

  const nomeCategoria = (codigo) => todasFilas.find(f => f.codigo === codigo)?.nome || `Categoria ${codigo}`;

  useEffect(() => {
    fetch(`${API}/api/enfermagem/filas`)
      .then(r => r.json())
      .then(d => {
        setTodasFilas(d);
        if (!carregarConfig()) setModalAberto(true); // primeira vez nesse navegador
      })
      .catch(() => setTodasFilas([]));
  }, []);

  const abrirConfig = () => {
    setSelecaoModal(new Set(filaCodigos));
    setModalAberto(true);
  };

  const salvarConfig = () => {
    const cods = Array.from(selecaoModal);
    setFilaCodigos(cods);
    salvarConfigStorage({ fila_codigos: cods });
    setModalAberto(false);
  };

  const alternarFila = (codigo) => {
    setSelecaoModal(prev => {
      const novo = new Set(prev);
      novo.has(codigo) ? novo.delete(codigo) : novo.add(codigo);
      return novo;
    });
  };

  const carregarFila = useCallback(() => {
    if (!filaCodigos.length) { setSenhas([]); return; }
    setCarregandoFila(true);
    fetch(`${API}/api/enfermagem/fila?fila_codigos=${filaCodigos.join(",")}&mostrar_chamados=${mostrarChamados}`)
      .then(r => r.json()).then(setSenhas).catch(() => setSenhas([]))
      .finally(() => setCarregandoFila(false));
  }, [filaCodigos, mostrarChamados]);

  useEffect(() => { carregarFila(); }, [carregarFila]);

  const abrirSenha = (s) => {
    setSelecionada(s);
    setBuscaPaciente(""); setResultadosPaciente(null); setPacienteEncontrado(null);
    setCampos(CAMPOS_VAZIOS);
    setErro(null); setAviso(null);
  };

  useEffect(() => {
    if (!buscaPaciente.trim() || buscaPaciente.trim().length < 2) { setResultadosPaciente(null); return; }
    setBuscandoPaciente(true);
    const t = setTimeout(() => {
      fetch(`${API}/api/atendimento/buscar-paciente?q=${encodeURIComponent(buscaPaciente.trim())}`)
        .then(r => r.json())
        .then(d => setResultadosPaciente(d.pacientes || []))
        .catch(() => setResultadosPaciente([]))
        .finally(() => setBuscandoPaciente(false));
    }, 350);
    return () => clearTimeout(t);
  }, [buscaPaciente]);

  const selecionarPaciente = (p) => {
    setPacienteEncontrado(p);
    setResultadosPaciente(null);
    setBuscaPaciente(p.nome);
  };

  const atualizarCampo = (chave, valor) => setCampos(prev => ({ ...prev, [chave]: valor }));

  const chamarSenha = async () => {
    if (!selecionada) return;
    setChamando(true); setErro(null); setAviso(null);
    try {
      const resp = await fetch(`${API}/api/enfermagem/chamar`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chegada_raw: selecionada.chegada_raw,
          categoria_codigo: selecionada.categoria_codigo,
          login,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Erro ao chamar senha.");
      if (!data.itens_atualizados) {
        setAviso("Essa senha não está mais disponível (provavelmente já foi processada pela recepção).");
      } else {
        setAviso("📢 Senha chamada no painel — continua na fila normalmente.");
      }
      setSelecionada(prev => prev ? { ...prev, chamado: 1 } : prev);
      carregarFila();
    } catch (e) {
      setErro(String(e.message || e));
    } finally {
      setChamando(false);
    }
  };

  const salvarTriagem = async () => {
    if (!selecionada) return;
    if (!pacienteEncontrado) { setErro("Pesquise e selecione o paciente antes de salvar."); return; }
    const algumPreenchido = Object.values(campos).some(v => String(v || "").trim());
    if (!algumPreenchido) { setErro("Preencha ao menos um campo da triagem."); return; }
    if (!user?.psv_cod) {
      setErro("Sua conta não tem um código de profissional (psv_cod) vinculado no Smart — fale com o suporte antes de salvar.");
      return;
    }
    setSalvando(true); setErro(null); setAviso(null);
    try {
      const resp = await fetch(`${API}/api/enfermagem/salvar-triagem`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          paciente: pacienteEncontrado.pac_reg,
          medico: user.psv_cod,
          login,
          campos,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Erro ao salvar triagem.");
      setAviso(`✓ Triagem de ${pacienteEncontrado.nome} salva no prontuário.`);
      setCampos(CAMPOS_VAZIOS);
      setPacienteEncontrado(null);
      setBuscaPaciente("");
      carregarFila();
    } catch (e) {
      setErro(String(e.message || e));
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto" }}>
      <div style={{
        background: `linear-gradient(135deg, ${COR} 0%, ${COR2} 100%)`,
        borderRadius: 20, padding: "24px 30px", marginBottom: 18, color: "#fff",
      }}>
        <div style={{ fontSize: 20, fontWeight: 900 }}>💗 Enfermagem — Triagem Ocupacional</div>
        <div style={{ fontSize: 13, opacity: .85 }}>Senha do totem, chamada e identificação do paciente antes da recepção, com registro de sinais vitais no prontuário</div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: 16, alignItems: "start" }}>
        {/* Coluna esquerda: fila */}
        <Card style={{ padding: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 800, color: "#0F172A" }}>
              Fila ({filaCodigos.length} categoria{filaCodigos.length === 1 ? "" : "s"})
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button onClick={abrirConfig} title="Configurar filas" style={{
                border: "none", background: "transparent", color: COR, cursor: "pointer", fontSize: 13, fontWeight: 700,
              }}>⚙️</button>
              <button onClick={carregarFila} title="Atualizar" style={{
                border: "none", background: "transparent", color: COR, cursor: "pointer", fontSize: 13, fontWeight: 700,
              }}>⟳</button>
            </div>
          </div>

          {filaCodigos.length === 0 && (
            <div style={{ padding: "10px 12px", borderRadius: 8, background: "#FEF2F2", color: "#DC2626", fontSize: 12, marginBottom: 10 }}>
              Nenhuma fila selecionada. Clique em ⚙️ pra escolher quais categorias do totem essa tela deve acompanhar.
            </div>
          )}

          <label style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 12, fontSize: 12, color: "#64748B", cursor: "pointer" }}>
            <input type="checkbox" checked={mostrarChamados} onChange={e => setMostrarChamados(e.target.checked)} />
            Mostrar já chamadas hoje
          </label>

          {carregandoFila ? (
            <div style={{ padding: 20, textAlign: "center", color: "#94A3B8", fontSize: 12.5 }}>Carregando...</div>
          ) : senhas.length === 0 ? (
            <div style={{ padding: 20, textAlign: "center", color: "#94A3B8", fontSize: 12.5 }}>Ninguém aguardando nessa fila.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {senhas.map(s => (
                <div key={s.chegada_raw + s.categoria_codigo} onClick={() => abrirSenha(s)} style={{
                  padding: "10px 12px", borderRadius: 10, cursor: "pointer",
                  opacity: s.chamado === 1 ? 0.7 : 1,
                  border: selecionada?.chegada_raw === s.chegada_raw ? `2px solid ${COR}` : "1.5px solid #F1F5F9",
                  background: selecionada?.chegada_raw === s.chegada_raw ? `${COR}0D` : "#FAFBFC",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 15, fontWeight: 800, color: "#0F172A" }}>{s.senha}</span>
                    <div style={{ display: "flex", gap: 4 }}>
                      {s.chamado === 1 && <span style={{ fontSize: 9, fontWeight: 800, color: "#0369A1", background: "#EFF6FF", padding: "1px 6px", borderRadius: 99 }}>📢 CHAMADA</span>}
                      {s.preferencial === "S" && <span style={{ fontSize: 9, fontWeight: 800, color: "#DC2626", background: "#FEF2F2", padding: "1px 6px", borderRadius: 99 }}>PREF</span>}
                    </div>
                  </div>
                  <div style={{ fontSize: 11, color: "#94A3B8" }}>{nomeCategoria(s.categoria_codigo)}</div>
                  <div style={{ fontSize: 11, color: "#94A3B8" }}>
                    chegou {s.chegada}{s.chamado === 1 && s.chamado_em ? ` · chamada ${s.chamado_em}` : ""}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Coluna direita: triagem */}
        <Card style={{ padding: 20, minHeight: 300 }}>
          {!selecionada ? (
            <div style={{ padding: 40, textAlign: "center", color: "#94A3B8", fontSize: 13 }}>Escolha uma senha na fila ao lado.</div>
          ) : (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
                <div>
                  <div style={{ fontSize: 20, fontWeight: 900, color: "#0F172A" }}>{selecionada.senha}</div>
                  <div style={{ fontSize: 12, color: "#94A3B8" }}>
                    {nomeCategoria(selecionada.categoria_codigo)} · chegou {selecionada.chegada}
                  </div>
                </div>
                <button onClick={chamarSenha} disabled={chamando} style={{
                  padding: "9px 16px", borderRadius: 10, border: `1.5px solid ${COR}`,
                  background: "#fff", color: COR2, fontWeight: 700, fontSize: 12.5,
                  cursor: chamando ? "not-allowed" : "pointer", whiteSpace: "nowrap",
                }}>{chamando ? "Chamando..." : selecionada?.chamado === 1 ? "🔁 Chamar novamente" : "📢 Chamar no painel"}</button>
              </div>

              <div style={{ fontSize: 12.5, fontWeight: 800, color: "#0F172A", marginBottom: 8 }}>Identificar paciente</div>
              <div style={{ position: "relative", marginBottom: 16 }}>
                <input
                  type="text" placeholder="🔎 Nome, CPF ou nº de registro..."
                  value={buscaPaciente}
                  onChange={e => { setBuscaPaciente(e.target.value); setPacienteEncontrado(null); }}
                  style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: `1.5px solid ${pacienteEncontrado ? "#059669" : "#E2E8F0"}`, fontSize: 13, boxSizing: "border-box" }}
                />
                {pacienteEncontrado && (
                  <div style={{ fontSize: 11.5, color: "#059669", marginTop: 4, fontWeight: 700 }}>
                    ✓ {pacienteEncontrado.nome}{idade(pacienteEncontrado.nascimento) != null ? ` · ${idade(pacienteEncontrado.nascimento)} anos` : ""}{pacienteEncontrado.cpf ? ` · CPF ${pacienteEncontrado.cpf}` : ""}
                  </div>
                )}
                {resultadosPaciente && !pacienteEncontrado && (
                  <div style={{
                    position: "absolute", top: "100%", left: 0, right: 0, zIndex: 20, marginTop: 4,
                    background: "#fff", border: "1px solid #E2E8F0", borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,.1)",
                    maxHeight: 220, overflowY: "auto",
                  }}>
                    {buscandoPaciente ? (
                      <div style={{ padding: 12, fontSize: 12.5, color: "#94A3B8" }}>Buscando...</div>
                    ) : resultadosPaciente.length === 0 ? (
                      <div style={{ padding: 12, fontSize: 12.5, color: "#94A3B8" }}>Nenhum paciente encontrado.</div>
                    ) : resultadosPaciente.map(p => (
                      <div key={p.pac_reg} onClick={() => selecionarPaciente(p)} style={{
                        padding: "9px 12px", cursor: "pointer", borderBottom: "1px solid #F1F5F9", fontSize: 13,
                      }}>
                        <div style={{ fontWeight: 700, color: "#0F172A" }}>{p.nome}</div>
                        <div style={{ fontSize: 11, color: "#94A3B8" }}>
                          {idade(p.nascimento) != null ? `${idade(p.nascimento)} anos` : ""}{p.cpf ? ` · CPF ${p.cpf}` : ""}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div style={{ fontSize: 12.5, fontWeight: 800, color: "#0F172A", marginBottom: 10 }}>Sinais vitais</div>
              <div style={{
                display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 10, marginBottom: 16,
                opacity: pacienteEncontrado ? 1 : 0.5, pointerEvents: pacienteEncontrado ? "auto" : "none",
              }}>
                {CAMPOS_VITAIS.map(c => (
                  <div key={c.chave}>
                    <label style={{ display: "block", fontSize: 10.5, fontWeight: 700, color: "#64748B", marginBottom: 4 }}>
                      {c.rotulo} <span style={{ fontWeight: 400, color: "#94A3B8" }}>({c.unidade})</span>
                    </label>
                    <input
                      type="text" value={campos[c.chave]}
                      onChange={e => atualizarCampo(c.chave, e.target.value)}
                      style={{ width: "100%", padding: "8px 10px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" }}
                    />
                  </div>
                ))}
              </div>

              <div style={{ marginBottom: 16, opacity: pacienteEncontrado ? 1 : 0.5, pointerEvents: pacienteEncontrado ? "auto" : "none" }}>
                <label style={{ display: "block", fontSize: 10.5, fontWeight: 700, color: "#64748B", marginBottom: 4 }}>
                  Observações da enfermagem
                </label>
                <textarea
                  value={campos.observacoes}
                  onChange={e => atualizarCampo("observacoes", e.target.value)}
                  rows={3}
                  style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box", resize: "vertical", fontFamily: "inherit" }}
                />
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

              <button onClick={salvarTriagem} disabled={salvando || !pacienteEncontrado} style={{
                width: "100%", padding: "14px 20px", borderRadius: 12, border: "none",
                background: (salvando || !pacienteEncontrado) ? "#CBD5E1" : `linear-gradient(135deg,${COR},${COR2})`,
                color: "#fff", fontSize: 14, fontWeight: 800, cursor: (salvando || !pacienteEncontrado) ? "not-allowed" : "pointer",
              }}>
                {salvando ? "Salvando..." : !pacienteEncontrado ? "Identifique o paciente primeiro" : "✓ Salvar triagem no prontuário"}
              </button>
            </>
          )}
        </Card>
      </div>

      {modalAberto && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(17,24,39,0.6)", zIndex: 100,
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <div style={{
            background: "#fff", border: "1px solid #E2E8F0", borderRadius: 14,
            padding: 24, width: 440, maxHeight: "80vh", display: "flex", flexDirection: "column",
            gap: 10, boxShadow: "0 20px 60px rgba(0,0,0,.25)",
          }}>
            <div style={{ fontSize: 16, fontWeight: 900, color: COR2 }}>⚙️ Configurar Enfermagem</div>
            <div style={{ fontSize: 12, color: "#64748B", marginBottom: 4 }}>
              Marque as categorias/filas do totem do Ocupacional que essa tela deve acompanhar.
            </div>
            <div style={{ overflowY: "auto", border: "1px solid #E2E8F0", borderRadius: 8, padding: "6px 8px", minHeight: 100, maxHeight: 320 }}>
              {todasFilas.length === 0 ? (
                <div style={{ color: "#94A3B8", fontSize: 12.5, padding: 8 }}>Carregando filas...</div>
              ) : todasFilas.map(f => (
                <label key={f.codigo} style={{
                  display: "flex", alignItems: "center", gap: 8, padding: "6px 4px",
                  fontSize: 13, borderBottom: "1px solid #F1F5F9", cursor: "pointer",
                }}>
                  <input
                    type="checkbox"
                    checked={selecaoModal.has(f.codigo)}
                    onChange={() => alternarFila(f.codigo)}
                  />
                  <span>{f.nome} <small style={{ color: "#94A3B8" }}>({f.prefixo} · {f.qtd} senhas/30d)</small></span>
                </label>
              ))}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
              <button onClick={() => setSelecaoModal(new Set(todasFilas.map(f => f.codigo)))} style={{
                flex: 1, padding: "8px 10px", borderRadius: 8, border: "1px solid #E2E8F0",
                background: "#F9FAFB", cursor: "pointer", fontSize: 12.5, fontWeight: 600,
              }}>Marcar todos</button>
              <button onClick={() => setSelecaoModal(new Set())} style={{
                flex: 1, padding: "8px 10px", borderRadius: 8, border: "1px solid #E2E8F0",
                background: "#F9FAFB", cursor: "pointer", fontSize: 12.5, fontWeight: 600,
              }}>Limpar</button>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              {filaCodigos.length > 0 && (
                <button onClick={() => setModalAberto(false)} style={{
                  flex: 1, padding: "10px", borderRadius: 8, border: "1px solid #E2E8F0",
                  background: "#F9FAFB", cursor: "pointer", fontSize: 13, fontWeight: 700,
                }}>Fechar</button>
              )}
              <button onClick={salvarConfig} style={{
                flex: 1, padding: "10px", borderRadius: 8, border: "none",
                background: `linear-gradient(135deg,${COR},${COR2})`, color: "#fff",
                cursor: "pointer", fontSize: 13, fontWeight: 700,
              }}>Salvar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
