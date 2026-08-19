import { useState } from "react";
import { LOGO } from "./Login";

const API = `${window.location.protocol}//${window.location.host}`;

function imprimirResultados(dados) {
  const linhasExames = dados.resultados.map(ex => `
    <div style="margin-bottom:22px;page-break-inside:avoid;">
      <div style="display:flex;justify-content:space-between;border-bottom:1px solid #ccc;padding-bottom:4px;margin-bottom:8px;">
        <strong>${ex.servico}</strong>
        <span>${ex.data ? new Date(ex.data).toLocaleDateString("pt-BR") : ""}</span>
      </div>
      ${ex.medico ? `<div style="font-size:12px;color:#555;margin-bottom:6px;">Dr(a). ${ex.medico}</div>` : ""}
      ${ex.valor ? `<div style="font-size:15px;font-weight:700;margin-bottom:6px;">${ex.valor}</div>` : ""}
      ${ex.campos.map(c => `<div style="font-size:13px;">${c.rotulo}: <strong>${c.valor}</strong></div>`).join("")}
    </div>
  `).join("");

  const html = `
    <html><head><title>Resultados - ${dados.nome}</title>
    <style>
      body{font-family:Arial,sans-serif;padding:32px;color:#111;}
      h1{font-size:18px;border-bottom:2px solid #8B1A1A;padding-bottom:8px;}
    </style></head>
    <body>
      <h1>Resultados de Exames — ${dados.nome}</h1>
      <p style="color:#666;font-size:12px;">Emitido em ${new Date().toLocaleString("pt-BR")}</p>
      ${linhasExames}
    </body></html>`;

  const janela = window.open("", "_blank", "width=900,height=1000");
  janela.document.write(html);
  janela.document.close();
  janela.focus();
  setTimeout(() => janela.print(), 300);
}

export default function MeusResultados() {
  const [cpf, setCpf]                 = useState("");
  const [nascimento, setNascimento]   = useState("");
  const [loading, setLoading]         = useState(false);
  const [erro, setErro]               = useState("");
  const [dados, setDados]             = useState(null); // null = form; objeto = resultados

  const formatarCpf = (v) => {
    const d = v.replace(/\D/g, "").slice(0, 11);
    return d
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d{1,2})$/, "$1-$2");
  };

  const submit = async (e) => {
    e?.preventDefault();
    if (!cpf.trim() || !nascimento) { setErro("Preencha CPF e data de nascimento."); return; }
    setErro(""); setLoading(true);
    try {
      const res = await fetch(`${API}/api/publico/resultados`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cpf, nascimento }),
      });
      const data = await res.json();
      if (!res.ok) { setErro(data.detail || "Não foi possível verificar seus dados."); setLoading(false); return; }
      setDados(data);
    } catch {
      setErro("Falha de conexão. Tente novamente.");
    }
    setLoading(false);
  };

  const R = "#8B1A1A";

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
        html,body,#root{height:100%;font-family:'Inter',sans-serif}
        @keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}
        .mr-field{
          width:100%;padding:13px 16px;border-radius:10px;font-size:14px;
          font-family:inherit;color:#111827;background:#F8FAFC;
          border:1.5px solid #E2E8F0;outline:none;
          transition:border .15s,box-shadow .15s,background .15s;
        }
        .mr-field:focus{border-color:${R};box-shadow:0 0 0 3px rgba(139,26,26,.1);background:#fff}
        .mr-btn{
          width:100%;padding:14px;border-radius:11px;border:none;
          font-size:15px;font-weight:700;font-family:inherit;
          cursor:pointer;transition:all .18s;color:#fff;
          background:linear-gradient(135deg,#7a1212 0%,#b52626 50%,#c0392b 100%);
          box-shadow:0 4px 18px rgba(139,26,26,.38);
        }
        .mr-btn:hover:not(:disabled){transform:translateY(-2px);box-shadow:0 8px 28px rgba(139,26,26,.5)}
        .mr-btn:disabled{background:#CBD5E1;box-shadow:none;cursor:not-allowed}
      `}</style>

      <div style={{
        minHeight:"100vh", background:"#F8FAFC", display:"flex",
        alignItems:"center", justifyContent:"center", padding:"32px 16px",
      }}>
        <div style={{ width:"100%", maxWidth:460 }}>

          <div style={{ textAlign:"center", marginBottom:28 }}>
            <img src={LOGO} alt="Clínica Censo" style={{ height:48, marginBottom:20 }}/>
            <h1 style={{ fontSize:22, fontWeight:800, color:"#0F172A", marginBottom:6 }}>
              Meus Resultados
            </h1>
            <p style={{ fontSize:13.5, color:"#64748B" }}>
              Consulte seus exames realizados na clínica
            </p>
          </div>

          <div style={{
            background:"#fff", borderRadius:16, padding:"32px 28px",
            boxShadow:"0 1px 4px rgba(0,0,0,.07)",
          }}>
            {!dados ? (
              <form onSubmit={submit} style={{ display:"flex", flexDirection:"column", gap:18 }}>
                <div>
                  <label style={{
                    display:"block", fontSize:11, fontWeight:700, color:"#475569",
                    marginBottom:7, textTransform:"uppercase", letterSpacing:".08em",
                  }}>CPF</label>
                  <input className="mr-field" inputMode="numeric" placeholder="000.000.000-00"
                    value={cpf} onChange={e => setCpf(formatarCpf(e.target.value))}/>
                </div>

                <div>
                  <label style={{
                    display:"block", fontSize:11, fontWeight:700, color:"#475569",
                    marginBottom:7, textTransform:"uppercase", letterSpacing:".08em",
                  }}>Data de Nascimento</label>
                  <input className="mr-field" type="date"
                    value={nascimento} onChange={e => setNascimento(e.target.value)}/>
                </div>

                {erro && (
                  <div style={{
                    background:"#FFF5F5", border:"1px solid #FED7D7", borderRadius:10,
                    padding:"12px 16px", fontSize:13, color:"#C53030", fontWeight:500,
                  }}>
                    {erro}
                  </div>
                )}

                <button type="submit" disabled={loading} className="mr-btn">
                  {loading ? "Verificando..." : "Consultar"}
                </button>
              </form>
            ) : (
              <div>
                <div style={{ textAlign:"center", marginBottom:24 }}>
                  <div style={{ fontSize:17, fontWeight:800, color:"#0F172A" }}>
                    Olá, {dados.nome}
                  </div>
                  <div style={{ fontSize:13, color:"#64748B", marginTop:2 }}>
                    {dados.total} exame{dados.total !== 1 ? "s" : ""} liberado{dados.total !== 1 ? "s" : ""}
                  </div>
                </div>

                {dados.total === 0 ? (
                  <div style={{ padding:"24px 0", textAlign:"center", color:"#94A3B8", fontSize:13.5 }}>
                    Nenhum exame interno liberado até o momento.
                  </div>
                ) : (
                  <button onClick={() => imprimirResultados(dados)} className="mr-btn">
                    Imprimir / Baixar PDF
                  </button>
                )}

                <button onClick={() => { setDados(null); setCpf(""); setNascimento(""); }} style={{
                  width:"100%", marginTop:12, padding:12, borderRadius:10,
                  border:"1px solid #E2E8F0", background:"#fff", color:"#64748B",
                  fontSize:13, fontWeight:600, cursor:"pointer",
                }}>
                  Consultar outro CPF
                </button>
              </div>
            )}
          </div>

          <p style={{ textAlign:"center", fontSize:11.5, color:"#CBD5E1", marginTop:20 }}>
            Parauapebas · PA
          </p>
        </div>
      </div>
    </>
  );
}
