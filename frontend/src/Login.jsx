import { useState, useEffect, createContext, useContext } from "react";

const API = `${window.location.protocol}//${window.location.host}`;
const LOGO = "data:image/png;base64,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";

export const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    try { const s = sessionStorage.getItem("censo_user"); if (s) setUser(JSON.parse(s)); } catch {}
    setLoading(false);
  }, []);
  const login  = (u) => { setUser(u); sessionStorage.setItem("censo_user", JSON.stringify(u)); };
  const logout = ()  => { setUser(null); sessionStorage.removeItem("censo_user"); };
  const podeVer = (m) => { if (!user) return false; if (user.admin) return true; return user.modulos?.includes(m) ?? false; };
  if (loading) return <div style={{ height:"100vh", background:"#0f0202", display:"flex", alignItems:"center", justifyContent:"center" }}><img src={LOGO} style={{ height:55, opacity:.7 }}/></div>;
  return <AuthContext.Provider value={{ user, login, logout, podeVer }}>{children}</AuthContext.Provider>;
}

// ── LOGIN ─────────────────────────────────────────────────────────────────────
export default function Login({ onLogin }) {
  const [loginVal,  setLoginVal]    = useState("");
  const [senhaVal,  setSenhaVal]    = useState("");
  const [erro,      setErro]        = useState("");
  const [loading,   setLoading]     = useState(false);
  const [showSenha, setShowSenha]   = useState(false);

  const submit = async (e) => {
    e?.preventDefault();
    if (!loginVal.trim() || !senhaVal.trim()) { setErro("Preencha login e senha."); return; }
    setLoading(true); setErro("");
    try {
      const res  = await fetch(`${API}/api/auth/login`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ login: loginVal.trim(), senha: senhaVal }),
      });
      const data = await res.json();
      if (!res.ok) { setErro(data.detail || "Erro ao autenticar."); setLoading(false); return; }
      if (!data.modulos?.length && !data.admin) {
        setErro("Usuário sem acesso configurado. Contate o administrador.");
        setLoading(false); return;
      }
      onLogin(data);
    } catch { setErro("Não foi possível conectar ao servidor."); }
    setLoading(false);
  };

  const MODULES = ["Assistencial","Laboratório","Agendamentos","Estoque","Ocupacional","Produção"];

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
        html,body,#root{height:100%;font-family:'Inter','DM Sans',sans-serif}
        @keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}
        @keyframes fadeUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
        .lg-wrap{min-height:100vh;display:flex}
        .lg-left{
          flex:1;min-height:100vh;
          background: linear-gradient(145deg,#0d0101 0%,#1f0404 30%,#3b0a0a 65%,#5a1010 100%);
          display:flex;flex-direction:column;align-items:center;justify-content:center;
          padding:60px 48px;position:relative;overflow:hidden;
        }
        .lg-right{
          width:500px;flex-shrink:0;background:#fff;
          display:flex;flex-direction:column;justify-content:center;
          padding:64px 56px;
        }
        .lg-field{
          width:100%;padding:13px 16px;border-radius:10px;font-size:14px;
          font-family:inherit;color:#111827;background:#F8FAFC;
          border:1.5px solid #E2E8F0;outline:none;
          transition:border .15s,box-shadow .15s,background .15s;
        }
        .lg-field:focus{
          border-color:#8B1A1A;box-shadow:0 0 0 3px rgba(139,26,26,.1);background:#fff;
        }
        .lg-btn{
          width:100%;padding:14px;border-radius:11px;border:none;
          font-size:15px;font-weight:700;font-family:inherit;letter-spacing:.01em;
          cursor:pointer;transition:all .18s;color:#fff;
          background:linear-gradient(135deg,#7a1212 0%,#b52626 50%,#c0392b 100%);
          box-shadow:0 4px 18px rgba(139,26,26,.38);
        }
        .lg-btn:hover:not(:disabled){transform:translateY(-2px);box-shadow:0 8px 28px rgba(139,26,26,.5)}
        .lg-btn:active:not(:disabled){transform:translateY(0)}
        .lg-btn:disabled{background:#CBD5E1;box-shadow:none;cursor:not-allowed}
        @media(max-width:860px){
          .lg-wrap{flex-direction:column}
          .lg-left{min-height:340px;padding:40px 28px}
          .lg-right{width:100%;padding:40px 28px 56px}
        }
      `}</style>

      <div className="lg-wrap">

        {/* ── ESQUERDA ── */}
        <div className="lg-left">
          {/* Ornamentos SVG de fundo */}
          <svg style={{ position:"absolute",inset:0,width:"100%",height:"100%",pointerEvents:"none" }} viewBox="0 0 600 800" preserveAspectRatio="xMidYMid slice">
            <defs>
              <radialGradient id="g1" cx="70%" cy="25%" r="50%">
                <stop offset="0%" stopColor="#c0392b" stopOpacity=".18"/>
                <stop offset="100%" stopColor="#c0392b" stopOpacity="0"/>
              </radialGradient>
              <radialGradient id="g2" cx="20%" cy="80%" r="40%">
                <stop offset="0%" stopColor="#8B1A1A" stopOpacity=".14"/>
                <stop offset="100%" stopColor="#8B1A1A" stopOpacity="0"/>
              </radialGradient>
            </defs>
            <rect width="600" height="800" fill="url(#g1)"/>
            <rect width="600" height="800" fill="url(#g2)"/>
            <circle cx="540" cy="80"  r="180" fill="none" stroke="rgba(255,255,255,.04)" strokeWidth="1"/>
            <circle cx="540" cy="80"  r="120" fill="none" stroke="rgba(255,255,255,.05)" strokeWidth="1"/>
            <circle cx="60"  cy="720" r="220" fill="none" stroke="rgba(255,255,255,.04)" strokeWidth="1"/>
            <circle cx="60"  cy="720" r="140" fill="none" stroke="rgba(255,255,255,.04)" strokeWidth="1"/>
            <line x1="0" y1="400" x2="600" y2="400" stroke="rgba(255,255,255,.03)" strokeWidth="1"/>
          </svg>

          {/* Conteúdo */}
          <div style={{ position:"relative", textAlign:"center", maxWidth:400, animation:"fadeUp .7s ease both" }}>

            {/* Logo em card branco pequeno */}
            <div style={{
              display:"inline-flex", alignItems:"center", justifyContent:"center",
              background:"#fff", borderRadius:20, padding:"18px 32px",
              marginBottom:36, boxShadow:"0 20px 60px rgba(0,0,0,.35)",
            }}>
              <img src={LOGO} alt="Clínica Censo" style={{ height:64, width:"auto", objectFit:"contain" }}/>
            </div>

            <h1 style={{
              fontSize:32, fontWeight:800, color:"#fff",
              letterSpacing:"-0.6px", lineHeight:1.15, marginBottom:12,
            }}>
              Plataforma de<br/>Gestão Clínica
            </h1>
            <p style={{
              fontSize:15, color:"rgba(255,255,255,.5)", fontWeight:400,
              lineHeight:1.7, marginBottom:44,
            }}>
              Inteligência operacional integrada ao<br/>
              <span style={{ color:"rgba(255,255,255,.72)", fontWeight:500 }}>
                Smart Pixeon · Parauapebas · PA
              </span>
            </p>

            {/* Módulos em grid */}
            <div style={{
              display:"grid", gridTemplateColumns:"1fr 1fr 1fr",
              gap:8, maxWidth:360, margin:"0 auto",
            }}>
              {MODULES.map(m => (
                <div key={m} style={{
                  padding:"8px 10px", borderRadius:10, textAlign:"center",
                  background:"rgba(255,255,255,.07)",
                  border:"1px solid rgba(255,255,255,.11)",
                  color:"rgba(255,255,255,.65)", fontSize:12, fontWeight:500,
                }}>{m}</div>
              ))}
            </div>
          </div>
        </div>

        {/* ── DIREITA ── */}
        <div className="lg-right">
          <div style={{ animation:"fadeUp .5s .1s ease both" }}>

            {/* Logo + cabeçalho */}
            <div style={{ marginBottom:40, textAlign:"center" }}>
              <img src={LOGO} alt="Clínica Censo" style={{
                height:48, width:"auto", objectFit:"contain", marginBottom:24,
              }}/>
              <h2 style={{
                fontSize:24, fontWeight:800, color:"#0F172A",
                letterSpacing:"-0.4px", marginBottom:6,
              }}>Bem-vindo de volta</h2>
              <p style={{ fontSize:14, color:"#94A3B8", fontWeight:400 }}>
                Entre com suas credenciais do Smart Pixeon
              </p>
            </div>

            {/* Formulário */}
            <form onSubmit={submit} style={{ display:"flex", flexDirection:"column", gap:20 }}>

              <div>
                <label style={{
                  display:"block", fontSize:11, fontWeight:700, color:"#475569",
                  marginBottom:7, textTransform:"uppercase", letterSpacing:".08em",
                }}>Login</label>
                <input className="lg-field" type="text" autoComplete="username"
                  placeholder="Seu login do Smart Pixeon"
                  value={loginVal} onChange={e => setLoginVal(e.target.value)}/>
              </div>

              <div>
                <label style={{
                  display:"block", fontSize:11, fontWeight:700, color:"#475569",
                  marginBottom:7, textTransform:"uppercase", letterSpacing:".08em",
                }}>Senha</label>
                <div style={{ position:"relative" }}>
                  <input className="lg-field" type={showSenha?"text":"password"}
                    autoComplete="current-password"
                    placeholder="Sua senha do Smart Pixeon"
                    value={senhaVal} onChange={e => setSenhaVal(e.target.value)}
                    style={{ paddingRight:48 }}/>
                  <button type="button" onClick={() => setShowSenha(v=>!v)} style={{
                    position:"absolute", right:14, top:"50%", transform:"translateY(-50%)",
                    background:"none", border:"none", cursor:"pointer",
                    color:"#94A3B8", display:"flex", alignItems:"center", padding:4,
                    borderRadius:6,
                  }}>
                    {showSenha
                      ? <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                      : <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                    }
                  </button>
                </div>
              </div>

              {erro && (
                <div style={{
                  background:"#FFF5F5", border:"1px solid #FED7D7",
                  borderRadius:10, padding:"12px 16px", fontSize:13,
                  color:"#C53030", fontWeight:500,
                  display:"flex", alignItems:"center", gap:10,
                }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink:0 }}>
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                  {erro}
                </div>
              )}

              <button type="submit" disabled={loading} className="lg-btn" style={{ marginTop:4 }}>
                {loading
                  ? <span style={{ display:"flex", alignItems:"center", justifyContent:"center", gap:8 }}>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" style={{ animation:"spin 1s linear infinite" }}><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
                      Autenticando...
                    </span>
                  : "Entrar no Dashboard"
                }
              </button>
            </form>

            {/* Rodapé */}
            <div style={{ marginTop:36, textAlign:"center" }}>
              <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:16 }}>
                <div style={{ flex:1, height:1, background:"#F1F5F9" }}/>
                <span style={{ fontSize:11, color:"#CBD5E1", fontWeight:500, whiteSpace:"nowrap" }}>
                  credenciais Smart Pixeon
                </span>
                <div style={{ flex:1, height:1, background:"#F1F5F9" }}/>
              </div>
              <p style={{ fontSize:12, color:"#CBD5E1" }}>
                Parauapebas · PA · v2.0
              </p>
            </div>

          </div>
        </div>
      </div>
    </>
  );
}

// ── ADMIN PERMISSÕES ──────────────────────────────────────────────────────────
export function AdminPermissoes() {
  const { user } = useAuth();
  const [usuarios, setUsuarios] = useState([]);
  const [loading,  setLoading]  = useState(false);
  const [busca,    setBusca]    = useState("");
  const [sel,      setSel]      = useState(null);
  const [modulos,  setModulos]  = useState([]);
  const [selMods,  setSelMods]  = useState([]);
  const [salvando, setSalvando] = useState(false);
  const [msg,      setMsg]      = useState(null);

  useEffect(() => { fetch(`${API}/api/auth/modulos`).then(r=>r.json()).then(setModulos).catch(()=>{}); }, []);

  const carregar = (b="") => {
    setLoading(true);
    fetch(`${API}/api/auth/usuarios?busca=${encodeURIComponent(b)}`)
      .then(r=>r.json()).then(d=>{setUsuarios(d);setLoading(false);}).catch(()=>setLoading(false));
  };
  useEffect(()=>{carregar();},[]);

  const selUser = (u) => { setSel(u); setSelMods(u.modulos||[]); setMsg(null); };
  const toggle  = (id) => setSelMods(p=>p.includes(id)?p.filter(m=>m!==id):[...p,id]);

  const salvar = async () => {
    if(!sel)return; setSalvando(true); setMsg(null);
    try {
      const res = await fetch(`${API}/api/auth/permissoes`,{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({login:sel.login,modulos:selMods,login_admin:user?.login||""}),
      });
      const d = await res.json();
      if(!res.ok) throw new Error(d.detail||"Erro");
      setMsg({ok:true,txt:`Permissões de ${sel.nome||sel.login} salvas!`});
      setUsuarios(p=>p.map(u=>u.login===sel.login?{...u,modulos:selMods}:u));
      setSel(p=>({...p,modulos:selMods}));
    } catch(e){setMsg({ok:false,txt:e.message});}
    setSalvando(false);
  };

  const R="#8B1A1A", G="#059669", B="#F3F4F6";

  return (
    <div style={{display:"flex",flexDirection:"column",gap:16}}>
      <div style={{background:"#fff",borderRadius:16,padding:"18px 24px",
        boxShadow:"0 1px 4px rgba(0,0,0,.07)",borderLeft:`4px solid ${R}`,
        display:"flex",alignItems:"center",gap:14}}>
        <img src={LOGO} alt="Censo" style={{height:32,objectFit:"contain"}}/>
        <div>
          <div style={{fontSize:16,fontWeight:800,color:"#0F172A"}}>Gerenciar Permissões</div>
          <div style={{fontSize:13,color:"#64748B"}}>Defina o acesso de cada usuário aos módulos do dashboard</div>
        </div>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1.4fr",gap:16,alignItems:"start"}}>
        <div style={{background:"#fff",borderRadius:16,overflow:"hidden",boxShadow:"0 1px 4px rgba(0,0,0,.07)"}}>
          <div style={{padding:"14px 18px",borderBottom:`1px solid ${B}`}}>
            <div style={{fontSize:13,fontWeight:700,color:"#0F172A",marginBottom:10}}>Usuários ({usuarios.length})</div>
            <input placeholder="Buscar nome ou login..." value={busca}
              onChange={e=>{setBusca(e.target.value);carregar(e.target.value);}}
              style={{width:"100%",padding:"8px 12px",borderRadius:8,border:"1px solid #E2E8F0",
                background:"#F8FAFC",fontSize:12,outline:"none",boxSizing:"border-box"}}/>
          </div>
          <div style={{overflowY:"auto",maxHeight:540}}>
            {loading?<div style={{padding:32,textAlign:"center",color:"#94A3B8"}}>Carregando...</div>
            :usuarios.map((u,i)=>{
              const at=sel?.login===u.login;
              return(
                <div key={i} onClick={()=>selUser(u)} style={{
                  padding:"11px 18px",cursor:"pointer",borderBottom:`1px solid ${B}`,
                  background:at?"#FEF2F2":"transparent",
                  borderLeft:at?`3px solid ${R}`:"3px solid transparent",transition:"all .1s",
                }}
                  onMouseEnter={e=>{if(!at)e.currentTarget.style.background="#F8FAFC";}}
                  onMouseLeave={e=>{if(!at)e.currentTarget.style.background="transparent";}}>
                  <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
                    <div>
                      <div style={{fontSize:13,fontWeight:600,color:"#0F172A"}}>
                        {(u.nome_completo||u.nome||u.login).trim()}
                        {u.admin&&<span style={{marginLeft:6,fontSize:10,fontWeight:700,
                          background:"#FEF2F2",color:R,padding:"1px 6px",borderRadius:8}}>ADMIN</span>}
                      </div>
                      <div style={{fontSize:11,color:"#94A3B8",marginTop:1}}>{u.login}</div>
                    </div>
                    <div style={{fontSize:11,fontWeight:700,color:u.modulos?.length>0?G:"#CBD5E1"}}>
                      {u.admin?"Todos":`${u.modulos?.length||0} módulos`}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div style={{background:"#fff",borderRadius:16,overflow:"hidden",boxShadow:"0 1px 4px rgba(0,0,0,.07)"}}>
          {!sel?(
            <div style={{padding:64,textAlign:"center",color:"#CBD5E1"}}>
              <div style={{fontSize:40,marginBottom:12}}>←</div>
              <div style={{fontSize:14,fontWeight:600}}>Selecione um usuário</div>
              <div style={{fontSize:12,marginTop:6,color:"#E2E8F0"}}>para configurar os módulos</div>
            </div>
          ):(
            <>
              <div style={{padding:"18px 22px",borderBottom:`1px solid ${B}`,background:"#FEF2F2"}}>
                <div style={{fontSize:15,fontWeight:800,color:R}}>{(sel.nome_completo||sel.nome||sel.login).trim()}</div>
                <div style={{fontSize:12,color:"#64748B",marginTop:2}}>Login: {sel.login} · Nível Pixeon: {sel.nivel}</div>
                {sel.admin&&<div style={{fontSize:11,color:R,fontWeight:600,marginTop:4}}>⚠ Admin — acesso total automático</div>}
              </div>
              <div style={{padding:"18px 22px"}}>
                <div style={{display:"flex",gap:8,marginBottom:14}}>
                  <button onClick={()=>setSelMods(modulos.map(m=>m.id))} style={{
                    padding:"6px 14px",borderRadius:8,fontSize:12,fontWeight:700,
                    border:"1px solid #D1FAE5",background:"#ECFDF5",color:G,cursor:"pointer"}}>
                    ✓ Marcar todos
                  </button>
                  <button onClick={()=>setSelMods([])} style={{
                    padding:"6px 14px",borderRadius:8,fontSize:12,fontWeight:700,
                    border:"1px solid #FEE2E2",background:"#FEF2F2",color:"#DC2626",cursor:"pointer"}}>
                    ✕ Desmarcar todos
                  </button>
                </div>
                <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginBottom:18}}>
                  {modulos.map(m=>{
                    const at=selMods.includes(m.id);
                    return(
                      <div key={m.id} onClick={()=>toggle(m.id)} style={{
                        padding:"11px 14px",borderRadius:10,cursor:"pointer",
                        border:`1.5px solid ${at?R:"#E2E8F0"}`,
                        background:at?"#FEF2F2":"#F8FAFC",
                        display:"flex",alignItems:"center",gap:10,transition:"all .15s",
                      }}>
                        <div style={{width:18,height:18,borderRadius:5,flexShrink:0,
                          border:`2px solid ${at?R:"#CBD5E1"}`,background:at?R:"#fff",
                          display:"flex",alignItems:"center",justifyContent:"center"}}>
                          {at&&<svg width="10" height="10" viewBox="0 0 24 24" fill="none"
                            stroke="#fff" strokeWidth="3" strokeLinecap="round"><polyline points="20 6 9 17 4 12"/></svg>}
                        </div>
                        <span style={{fontSize:12,fontWeight:at?700:500,color:at?R:"#64748B"}}>{m.label}</span>
                      </div>
                    );
                  })}
                </div>
                {msg&&(
                  <div style={{padding:"10px 14px",borderRadius:8,marginBottom:14,fontSize:13,fontWeight:600,
                    background:msg.ok?"#ECFDF5":"#FEF2F2",
                    border:`1px solid ${msg.ok?"#A7F3D0":"#FECACA"}`,
                    color:msg.ok?G:"#DC2626"}}>
                    {msg.ok?"✓ ":"⚠ "}{msg.txt}
                  </div>
                )}
                <button onClick={salvar} disabled={salvando} style={{
                  width:"100%",padding:12,borderRadius:10,border:"none",
                  background:salvando?"#CBD5E1":`linear-gradient(135deg,#7a1212,#c0392b)`,
                  color:"#fff",fontSize:14,fontWeight:700,
                  cursor:salvando?"not-allowed":"pointer",
                  boxShadow:salvando?"none":"0 4px 14px rgba(139,26,26,.28)"}}>
                  {salvando?"Salvando...":`Salvar permissões — ${(sel.nome||sel.login).split(" ")[0]}`}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
