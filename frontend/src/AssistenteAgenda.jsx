import { useState, useRef, useEffect } from "react";
import { useAuth } from "./Login";

const API = `${window.location.protocol}//${window.location.host}`;

const VINHO = "#8B1A1A";
const AMBAR = "#D97706";
const CINZA_ESCURO = "#1E293B";
const CINZA_TXT = "#64748B";
const CINZA_FUNDO = "#F7F6F3";
const CINZA_LINHA = "#E2E5EA";

// ════════════════════════════════════════════════════════════════════════
// ABA 1 — ASSISTENTE DE AGENDA (IA)
// ════════════════════════════════════════════════════════════════════════
const SUGESTOES = [
  "Temos dermatologista disponível?",
  "Dr. Malcher atende aqui?",
  "Quais horários de ultrassonografia esse mês?",
  "Quais médicos têm agenda aberta hoje?",
];

function formatarData(iso) {
  const [ano, mes, dia] = iso.split("-");
  return `${dia}/${mes}`;
}

function CardMedico({ medico }) {
  return (
    <div style={{
      background: "#fff", border: `1px solid ${CINZA_LINHA}`, borderRadius: 10,
      padding: "12px 14px", marginBottom: 8,
    }}>
      <div style={{ fontSize: 13.5, fontWeight: 700, color: CINZA_ESCURO, marginBottom: medico.especialidade ? 1 : 8 }}>
        Dr(a). {medico.medico_nome}
      </div>
      {medico.especialidade && (
        <div style={{ fontSize: 11.5, color: CINZA_TXT, marginBottom: 8 }}>{medico.especialidade}</div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {medico.proximas_datas.map((d, i) => (
          <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
            <span style={{
              fontSize: 11.5, fontWeight: 700, color: VINHO, background: "#FBEAEA",
              borderRadius: 6, padding: "2px 7px", minWidth: 40, textAlign: "center", flexShrink: 0,
            }}>
              {formatarData(d.data)}
            </span>
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
              {d.horarios.slice(0, 8).map((h, j) => (
                <span key={j} style={{
                  fontSize: 11, color: CINZA_ESCURO, background: CINZA_FUNDO,
                  borderRadius: 5, padding: "2px 6px", border: `1px solid ${CINZA_LINHA}`,
                }}>{h}</span>
              ))}
              {d.horarios.length > 8 && (
                <span style={{ fontSize: 11, color: CINZA_TXT, alignSelf: "center" }}>
                  +{d.horarios.length - 8}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function BolhaAssistente({ msg }) {
  return (
    <div style={{ display: "flex", gap: 10, marginBottom: 16, maxWidth: 620 }}>
      <div style={{
        width: 30, height: 30, borderRadius: "50%", background: VINHO, color: "#fff",
        display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700,
        flexShrink: 0,
      }}>IA</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        {msg.tipo === "disponibilidade_especialidade" && msg.especialidade_encontrada && (
          <div style={{ fontSize: 12.5, fontWeight: 700, color: CINZA_ESCURO, marginBottom: 8 }}>
            📅 {msg.especialidade_encontrada} — horários disponíveis
          </div>
        )}
        {msg.tipo === "disponibilidade_medico" && msg.encontrado && (
          <div style={{ fontSize: 12.5, fontWeight: 700, color: CINZA_ESCURO, marginBottom: 8 }}>
            🔎 Busca por "{msg.medico_buscado}"
          </div>
        )}
        {msg.tipo === "disponibilidade_hoje" && msg.encontrada && (
          <div style={{ fontSize: 12.5, fontWeight: 700, color: CINZA_ESCURO, marginBottom: 8 }}>
            📅 Médicos com agenda aberta hoje
          </div>
        )}
        {msg.mensagem && (
          <div style={{
            background: "#fff", border: `1px solid ${CINZA_LINHA}`, borderRadius: 10,
            padding: "10px 13px", fontSize: 13, color: CINZA_ESCURO, lineHeight: 1.5, marginBottom: msg.medicos?.length ? 8 : 0,
          }}>
            {msg.mensagem}
          </div>
        )}
        {msg.medicos?.filter(m => m.proximas_datas?.length > 0).map((m, i) => <CardMedico key={i} medico={m} />)}
      </div>
    </div>
  );
}

function BolhaUsuario({ texto }) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
      <div style={{
        background: VINHO, color: "#fff", borderRadius: "12px 12px 2px 12px",
        padding: "9px 14px", fontSize: 13.5, maxWidth: 480, lineHeight: 1.4,
      }}>
        {texto}
      </div>
    </div>
  );
}

function AbaAssistenteIA() {
  const [mensagens, setMensagens] = useState([
    { autor: "assistente", mensagem: "Oi! Pergunte sobre a agenda de uma especialidade (\"temos dermatologista?\"), de um médico específico (\"Dr. Malcher atende aqui?\") ou peça a lista geral de hoje (\"quais médicos têm agenda aberta hoje?\")." },
  ]);
  const [entrada, setEntrada] = useState("");
  const [carregando, setCarregando] = useState(false);
  const fimRef = useRef(null);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens, carregando]);

  async function enviar(texto) {
    const pergunta = (texto ?? entrada).trim();
    if (!pergunta || carregando) return;
    setMensagens(m => [...m, { autor: "usuario", texto: pergunta }]);
    setEntrada("");
    setCarregando(true);
    try {
      const resp = await fetch(`${API}/api/agenda/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mensagem: pergunta }),
      });
      const dados = await resp.json();
      setMensagens(m => [...m, { autor: "assistente", ...dados }]);
    } catch (e) {
      setMensagens(m => [...m, { autor: "assistente", mensagem: "Não consegui consultar agora — tenta de novo em instantes." }]);
    }
    setCarregando(false);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
        {mensagens.map((m, i) => (
          m.autor === "usuario"
            ? <BolhaUsuario key={i} texto={m.texto} />
            : <BolhaAssistente key={i} msg={m} />
        ))}
        {carregando && (
          <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
            <div style={{
              width: 30, height: 30, borderRadius: "50%", background: VINHO, color: "#fff",
              display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700,
            }}>IA</div>
            <div style={{
              background: "#fff", border: `1px solid ${CINZA_LINHA}`, borderRadius: 10,
              padding: "10px 14px", fontSize: 13, color: CINZA_TXT,
            }}>Consultando agenda…</div>
          </div>
        )}
        <div ref={fimRef} />
      </div>

      {mensagens.length <= 1 && (
        <div style={{ padding: "0 24px 10px", display: "flex", gap: 8, flexWrap: "wrap" }}>
          {SUGESTOES.map((s, i) => (
            <button key={i} onClick={() => enviar(s)} style={{
              fontSize: 11.5, color: VINHO, background: "#FBEAEA", border: `1px solid #F0D5D5`,
              borderRadius: 20, padding: "6px 12px", cursor: "pointer", fontWeight: 600,
            }}>{s}</button>
          ))}
        </div>
      )}

      <div style={{ padding: 16, borderTop: `1px solid ${CINZA_LINHA}`, background: "#fff", display: "flex", gap: 10 }}>
        <input
          value={entrada}
          onChange={e => setEntrada(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") enviar(); }}
          placeholder="Pergunte sobre a agenda de uma especialidade..."
          disabled={carregando}
          style={{
            flex: 1, padding: "10px 14px", borderRadius: 10, border: `1px solid ${CINZA_LINHA}`,
            fontSize: 13.5, outline: "none", color: CINZA_ESCURO,
          }}
        />
        <button onClick={() => enviar()} disabled={carregando || !entrada.trim()} style={{
          padding: "10px 20px", borderRadius: 10, border: "none",
          background: carregando || !entrada.trim() ? "#D1D5DB" : VINHO, color: "#fff",
          fontSize: 13.5, fontWeight: 700, cursor: carregando || !entrada.trim() ? "default" : "pointer",
        }}>Enviar</button>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════
// ABA 2 — CHAT INTERNO (canais por setor + DM entre usuários)
// ════════════════════════════════════════════════════════════════════════
function iniciais(nome) {
  if (!nome) return "?";
  const partes = nome.trim().split(/\s+/);
  return (partes[0][0] + (partes[1]?.[0] || "")).toUpperCase();
}

function formatarHora(iso) {
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function ModalNovaConversa({ onFechar, onIniciarDm, onCriarGrupo }) {
  const [modo, setModo] = useState("dm"); // "dm" | "grupo"
  const [busca, setBusca] = useState("");
  const [usuarios, setUsuarios] = useState([]);
  const [nomeGrupo, setNomeGrupo] = useState("");
  const [selecionados, setSelecionados] = useState([]); // [{login, nome}]

  useEffect(() => {
    const t = setTimeout(() => {
      fetch(`${API}/api/chat/usuarios${busca ? `?busca=${encodeURIComponent(busca)}` : ""}`)
        .then(r => r.json()).then(d => setUsuarios((d.usuarios || []).slice(0, 30)));
    }, 250);
    return () => clearTimeout(t);
  }, [busca]);

  function toggleSelecionado(u) {
    setSelecionados(sel => sel.some(s => s.login === u.login)
      ? sel.filter(s => s.login !== u.login)
      : [...sel, u]);
  }

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={onFechar}>
      <div style={{ background: "#fff", borderRadius: 12, width: 400, maxHeight: "78vh", display: "flex", flexDirection: "column", overflow: "hidden" }}
        onClick={e => e.stopPropagation()}>
        <div style={{ padding: 16, borderBottom: `1px solid ${CINZA_LINHA}` }}>
          <div style={{ display: "flex", gap: 4, marginBottom: 12 }}>
            {[{ id: "dm", label: "Conversa direta" }, { id: "grupo", label: "Novo grupo" }].map(t => (
              <button key={t.id} onClick={() => setModo(t.id)} style={{
                flex: 1, padding: "7px 10px", borderRadius: 8, border: "none", cursor: "pointer",
                fontSize: 12.5, fontWeight: 700,
                background: modo === t.id ? VINHO : CINZA_FUNDO,
                color: modo === t.id ? "#fff" : CINZA_TXT,
              }}>{t.label}</button>
            ))}
          </div>
          {modo === "grupo" && (
            <input autoFocus value={nomeGrupo} onChange={e => setNomeGrupo(e.target.value)} placeholder="Nome do grupo..."
              style={{ width: "100%", padding: "8px 12px", borderRadius: 8, border: `1px solid ${CINZA_LINHA}`, fontSize: 13, outline: "none", marginBottom: 10, boxSizing: "border-box" }} />
          )}
          <input value={busca} onChange={e => setBusca(e.target.value)} placeholder="Buscar pessoa..."
            style={{ width: "100%", padding: "8px 12px", borderRadius: 8, border: `1px solid ${CINZA_LINHA}`, fontSize: 13, outline: "none", boxSizing: "border-box" }} />
          {modo === "grupo" && selecionados.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
              {selecionados.map(s => (
                <span key={s.login} onClick={() => toggleSelecionado(s)} style={{
                  fontSize: 11, color: VINHO, background: "#FBEAEA", borderRadius: 14, padding: "4px 10px",
                  cursor: "pointer", fontWeight: 600,
                }}>{s.nome} ✕</span>
              ))}
            </div>
          )}
        </div>
        <div style={{ overflowY: "auto", flex: 1 }}>
          {usuarios.map(u => {
            const marcado = selecionados.some(s => s.login === u.login);
            return (
              <div key={u.login} onClick={() => modo === "dm" ? onIniciarDm(u) : toggleSelecionado(u)} style={{
                display: "flex", alignItems: "center", gap: 10, padding: "10px 16px", cursor: "pointer",
                background: marcado ? CINZA_FUNDO : "transparent",
              }}
                onMouseEnter={e => e.currentTarget.style.background = CINZA_FUNDO}
                onMouseLeave={e => e.currentTarget.style.background = marcado ? CINZA_FUNDO : "transparent"}>
                {modo === "grupo" && (
                  <input type="checkbox" checked={marcado} readOnly style={{ width: 15, height: 15, flexShrink: 0 }} />
                )}
                <div style={{
                  width: 32, height: 32, borderRadius: "50%", background: AMBAR, color: "#fff",
                  display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, flexShrink: 0,
                }}>{iniciais(u.nome)}</div>
                <div style={{ fontSize: 13, color: CINZA_ESCURO, fontWeight: 600 }}>{u.nome}</div>
              </div>
            );
          })}
          {usuarios.length === 0 && (
            <div style={{ padding: 20, fontSize: 12.5, color: CINZA_TXT, textAlign: "center" }}>Nenhum usuário encontrado</div>
          )}
        </div>
        {modo === "grupo" && (
          <div style={{ padding: 14, borderTop: `1px solid ${CINZA_LINHA}` }}>
            <button
              disabled={!nomeGrupo.trim() || selecionados.length === 0}
              onClick={() => onCriarGrupo(nomeGrupo.trim(), selecionados)}
              style={{
                width: "100%", padding: "10px", borderRadius: 8, border: "none",
                background: (!nomeGrupo.trim() || selecionados.length === 0) ? "#D1D5DB" : VINHO,
                color: "#fff", fontSize: 13, fontWeight: 700,
                cursor: (!nomeGrupo.trim() || selecionados.length === 0) ? "default" : "pointer",
              }}>Criar grupo {selecionados.length > 0 ? `(${selecionados.length})` : ""}</button>
          </div>
        )}
      </div>
    </div>
  );
}

function AbaChatInterno() {
  const { user } = useAuth();
  const [canais, setCanais] = useState([]);
  const [canalAtivo, setCanalAtivo] = useState(null);
  const [mensagens, setMensagens] = useState([]);
  const [entrada, setEntrada] = useState("");
  const [importante, setImportante] = useState(false);
  const [modalAberto, setModalAberto] = useState(false);
  const fimRef = useRef(null);
  const login = user?.login || "";
  const nome = user?.nome || user?.login || "Você";

  function carregarCanais() {
    if (!login) return;
    fetch(`${API}/api/chat/canais?login=${encodeURIComponent(login)}`)
      .then(r => r.json()).then(setCanais).catch(() => {});
  }

  function carregarMensagens(canalId) {
    if (!canalId) return;
    fetch(`${API}/api/chat/mensagens?canal=${encodeURIComponent(canalId)}`)
      .then(r => r.json()).then(setMensagens).catch(() => {});
  }

  useEffect(() => { carregarCanais(); }, [login]);
  useEffect(() => {
    if (!canalAtivo && canais.length > 0) setCanalAtivo(canais[0].id);
  }, [canais]);

  useEffect(() => {
    carregarMensagens(canalAtivo);
    if (canalAtivo && login) {
      fetch(`${API}/api/chat/marcar-lido`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ canal_id: canalAtivo, login }),
      }).then(carregarCanais);
    }
  }, [canalAtivo]);

  // Polling: mensagens do canal ativo a cada 4s, lista de canais (unread) a cada 8s
  useEffect(() => {
    const t1 = setInterval(() => carregarMensagens(canalAtivo), 4000);
    const t2 = setInterval(carregarCanais, 8000);
    return () => { clearInterval(t1); clearInterval(t2); };
  }, [canalAtivo, login]);

  useEffect(() => { fimRef.current?.scrollIntoView({ behavior: "smooth" }); }, [mensagens]);

  async function enviar() {
    const texto = entrada.trim();
    if (!texto || !canalAtivo) return;
    setEntrada("");
    const eraImportante = importante;
    setImportante(false);
    await fetch(`${API}/api/chat/mensagens`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ canal_id: canalAtivo, remetente_login: login, remetente_nome: nome, texto, importante: eraImportante }),
    });
    carregarMensagens(canalAtivo);
  }

  async function iniciarDm(outro) {
    setModalAberto(false);
    const resp = await fetch(`${API}/api/chat/dm/iniciar`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ login_a: login, nome_a: nome, login_b: outro.login, nome_b: outro.nome }),
    });
    const d = await resp.json();
    carregarCanais();
    setCanalAtivo(d.canal_id);
  }

  async function criarGrupo(nomeGrupo, participantes) {
    setModalAberto(false);
    const resp = await fetch(`${API}/api/chat/grupo/criar`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nome: nomeGrupo, criador_login: login, criador_nome: nome, participantes }),
    });
    const d = await resp.json();
    carregarCanais();
    setCanalAtivo(d.canal_id);
  }

  const canalAtivoObj = canais.find(c => c.id === canalAtivo);

  return (
    <div style={{ display: "flex", height: "100%" }}>
      {/* Sidebar de canais */}
      <div style={{ width: 260, borderRight: `1px solid ${CINZA_LINHA}`, display: "flex", flexDirection: "column", background: "#fff" }}>
        <div style={{ padding: "14px 16px", borderBottom: `1px solid ${CINZA_LINHA}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontSize: 12.5, fontWeight: 700, color: CINZA_TXT, textTransform: "uppercase", letterSpacing: ".03em" }}>Conversas</div>
          <button onClick={() => setModalAberto(true)} title="Nova conversa" style={{
            width: 24, height: 24, borderRadius: 6, border: "none", background: VINHO, color: "#fff",
            fontSize: 15, fontWeight: 700, cursor: "pointer", lineHeight: 1,
          }}>+</button>
        </div>
        <div style={{ flex: 1, overflowY: "auto" }}>
          {canais.map(c => (
            <div key={c.id} onClick={() => setCanalAtivo(c.id)} style={{
              padding: "10px 16px", cursor: "pointer", borderBottom: `1px solid ${CINZA_FUNDO}`,
              background: canalAtivo === c.id ? "#FBEAEA" : "transparent",
              borderLeft: canalAtivo === c.id ? `3px solid ${VINHO}` : "3px solid transparent",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: CINZA_ESCURO, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {c.nome}
                </div>
                {c.nao_lidas > 0 && (
                  <span style={{
                    background: VINHO, color: "#fff", fontSize: 10, fontWeight: 700, borderRadius: 10,
                    minWidth: 16, height: 16, display: "flex", alignItems: "center", justifyContent: "center", padding: "0 4px",
                  }}>{c.nao_lidas}</span>
                )}
              </div>
              {c.ultima_mensagem && (
                <div style={{ fontSize: 11, color: CINZA_TXT, marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {c.ultima_mensagem.remetente_nome}: {c.ultima_mensagem.texto}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Painel de mensagens */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {canalAtivoObj ? (
          <>
            <div style={{ padding: "14px 20px", borderBottom: `1px solid ${CINZA_LINHA}`, background: "#fff", fontSize: 14, fontWeight: 700, color: CINZA_ESCURO }}>
              {canalAtivoObj.nome}
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "18px 20px" }}>
              {mensagens.map(m => {
                const minha = m.remetente_login === login.toLowerCase();
                return (
                  <div key={m.id} style={{ display: "flex", justifyContent: minha ? "flex-end" : "flex-start", marginBottom: 10 }}>
                    <div style={{ maxWidth: 460 }}>
                      {!minha && <div style={{ fontSize: 10.5, color: CINZA_TXT, marginBottom: 2, marginLeft: 4 }}>{m.remetente_nome}</div>}
                      <div style={{
                        background: m.importante ? "#FDF3E7" : (minha ? VINHO : "#fff"),
                        color: m.importante ? CINZA_ESCURO : (minha ? "#fff" : CINZA_ESCURO),
                        border: m.importante ? `1.5px solid ${AMBAR}` : (minha ? "none" : `1px solid ${CINZA_LINHA}`),
                        borderRadius: minha ? "12px 12px 2px 12px" : "12px 12px 12px 2px",
                        padding: "8px 13px", fontSize: 13.5, lineHeight: 1.4,
                      }}>
                        {m.importante ? <span style={{ fontWeight: 700, color: AMBAR }}>🚨 IMPORTANTE — </span> : null}
                        {m.texto}
                        <div style={{ fontSize: 9.5, color: m.importante ? CINZA_TXT : (minha ? "rgba(255,255,255,0.7)" : CINZA_TXT), marginTop: 3, textAlign: "right" }}>
                          {formatarHora(m.criado_em)}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
              <div ref={fimRef} />
            </div>
            <div style={{ padding: 14, borderTop: `1px solid ${CINZA_LINHA}`, background: "#fff", display: "flex", gap: 8, alignItems: "center" }}>
              <button
                onClick={() => setImportante(v => !v)}
                title="Marcar como importante — aparece em destaque pra quem receber"
                style={{
                  padding: "9px 11px", borderRadius: 10, border: `1px solid ${importante ? AMBAR : CINZA_LINHA}`,
                  background: importante ? "#FDF3E7" : "#fff", cursor: "pointer", fontSize: 15, flexShrink: 0, lineHeight: 1,
                }}>🚨</button>
              <input
                value={entrada}
                onChange={e => setEntrada(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") enviar(); }}
                placeholder={importante ? "Mensagem importante — vai aparecer em destaque..." : "Escreva uma mensagem..."}
                style={{ flex: 1, padding: "9px 13px", borderRadius: 10, border: `1px solid ${importante ? AMBAR : CINZA_LINHA}`, fontSize: 13.5, outline: "none" }}
              />
              <button onClick={enviar} disabled={!entrada.trim()} style={{
                padding: "9px 18px", borderRadius: 10, border: "none",
                background: !entrada.trim() ? "#D1D5DB" : VINHO, color: "#fff", fontSize: 13.5, fontWeight: 700,
                cursor: !entrada.trim() ? "default" : "pointer",
              }}>Enviar</button>
            </div>
          </>
        ) : (
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: CINZA_TXT, fontSize: 13 }}>
            Selecione uma conversa
          </div>
        )}
      </div>

      {modalAberto && <ModalNovaConversa onFechar={() => setModalAberto(false)} onIniciarDm={iniciarDm} onCriarGrupo={criarGrupo} />}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════
// PÁGINA PRINCIPAL — abas
// ════════════════════════════════════════════════════════════════════════
export default function AssistenteAgenda() {
  const [aba, setAba] = useState("ia");

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: CINZA_FUNDO }}>
      <div style={{ padding: "16px 24px 0", background: "#fff", borderBottom: `1px solid ${CINZA_LINHA}` }}>
        <div style={{ fontSize: 18, fontWeight: 800, color: CINZA_ESCURO, marginBottom: 2 }}>Assistente & Chat</div>
        <div style={{ fontSize: 12.5, color: CINZA_TXT, marginBottom: 12 }}>
          Consulta de agenda por IA e comunicação interna entre setores
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          {[
            { id: "ia", label: "🤖 Assistente de Agenda" },
            { id: "chat", label: "💬 Chat Interno" },
          ].map(t => (
            <button key={t.id} onClick={() => setAba(t.id)} style={{
              padding: "8px 16px", borderRadius: "8px 8px 0 0", border: "none", cursor: "pointer",
              fontSize: 13, fontWeight: 700,
              background: aba === t.id ? CINZA_FUNDO : "transparent",
              color: aba === t.id ? VINHO : CINZA_TXT,
              borderBottom: aba === t.id ? `2px solid ${VINHO}` : "2px solid transparent",
            }}>{t.label}</button>
          ))}
        </div>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        {aba === "ia" ? <AbaAssistenteIA /> : <AbaChatInterno />}
      </div>
    </div>
  );
}
