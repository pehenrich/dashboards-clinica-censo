import { useState, useRef, useCallback } from "react";

const API = `${window.location.protocol}//${window.location.host}`;

function destacar(contexto, palavra) {
  if (!palavra) return contexto;
  const partes = contexto.split(new RegExp(`(${palavra.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"));
  return partes.map((parte, i) =>
    parte.toLowerCase() === palavra.toLowerCase()
      ? <mark key={i} style={{ background: "#FDE68A", color: "#78350F", padding: "0 3px", borderRadius: 4, fontWeight: 700 }}>{parte}</mark>
      : parte
  );
}

export default function EditorPDF() {
  const [arquivo, setArquivo]         = useState(null);
  const [palavraAtual, setPalavraAtual] = useState("");
  const [palavraNova, setPalavraNova]   = useState("");
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [buscando, setBuscando]       = useState(false);
  const [substituindo, setSubstituindo] = useState(false);
  const [resultado, setResultado]     = useState(null); // { total, paginas }
  const [erro, setErro]               = useState(null);
  const [ok, setOk]                   = useState(null);
  const inputRef = useRef(null);

  const resetarResultado = useCallback(() => {
    setResultado(null);
    setErro(null);
    setOk(null);
  }, []);

  const escolherArquivo = (file) => {
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setErro("Selecione um arquivo PDF.");
      return;
    }
    setArquivo(file);
    resetarResultado();
  };

  const buscar = async () => {
    if (!arquivo) { setErro("Selecione um PDF primeiro."); return; }
    if (!palavraAtual.trim()) { setErro("Digite a palavra a procurar."); return; }
    resetarResultado();
    setBuscando(true);
    try {
      const fd = new FormData();
      fd.append("arquivo", arquivo);
      fd.append("palavra", palavraAtual.trim());
      fd.append("case_sensitive", caseSensitive ? "true" : "false");
      const r = await fetch(`${API}/api/pdf/buscar-palavra`, { method: "POST", body: fd });
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${r.status}`); }
      const data = await r.json();
      setResultado(data);
      if (data.total === 0) setErro(`"${palavraAtual}" não foi encontrada nesse PDF.`);
    } catch (e) {
      setErro(String(e.message || e));
    } finally {
      setBuscando(false);
    }
  };

  const substituir = async () => {
    if (!arquivo) { setErro("Selecione um PDF primeiro."); return; }
    if (!palavraAtual.trim() || !palavraNova.trim()) { setErro("Preencha a palavra atual e a palavra nova."); return; }
    setErro(null);
    setOk(null);
    setSubstituindo(true);
    try {
      const fd = new FormData();
      fd.append("arquivo", arquivo);
      fd.append("palavra_antiga", palavraAtual.trim());
      fd.append("palavra_nova", palavraNova.trim());
      fd.append("case_sensitive", caseSensitive ? "true" : "false");
      const r = await fetch(`${API}/api/pdf/substituir-palavra`, { method: "POST", body: fd });
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${r.status}`); }
      const blob = await r.blob();
      const nomeArquivo = (r.headers.get("content-disposition") || "").match(/filename="?([^"]+)"?/)?.[1]
        || `${arquivo.name.replace(/\.pdf$/i, "")}_editado.pdf`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = nomeArquivo;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      setOk(`Pronto — "${palavraAtual}" trocado por "${palavraNova}". Download iniciado (${nomeArquivo}).`);
    } catch (e) {
      setErro(String(e.message || e));
    } finally {
      setSubstituindo(false);
    }
  };

  return (
    <div>
      <div style={{
        background: "linear-gradient(135deg, #1E293B 0%, #334155 100%)",
        borderRadius: 20, padding: "24px 28px", marginBottom: 20,
        boxShadow: "0 8px 32px rgba(30,41,59,0.35)",
      }}>
        <div style={{ fontSize: 18, fontWeight: 900, color: "#fff", marginBottom: 4 }}>Editor de PDF</div>
        <div style={{ fontSize: 12.5, color: "rgba(255,255,255,0.65)" }}>
          Corrige uma palavra errada num PDF já emitido (ex.: ASO) sem precisar reemitir o documento.
        </div>
      </div>

      <div style={{ background: "#fff", borderRadius: 16, padding: 24, boxShadow: "0 2px 8px rgba(0,0,0,0.07), 0 0 0 1px rgba(0,0,0,0.04)", marginBottom: 16 }}>
        <div
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); escolherArquivo(e.dataTransfer.files?.[0]); }}
          style={{
            border: `2px dashed ${arquivo ? "#10B981" : "#CBD5E1"}`,
            borderRadius: 14, padding: "28px 20px", textAlign: "center",
            cursor: "pointer", background: arquivo ? "#ECFDF5" : "#F8FAFC",
            transition: "all .15s",
          }}
        >
          <input ref={inputRef} type="file" accept="application/pdf,.pdf" style={{ display: "none" }}
            onChange={(e) => escolherArquivo(e.target.files?.[0])} />
          {arquivo ? (
            <div>
              <div style={{ fontSize: 14, fontWeight: 800, color: "#059669" }}>📄 {arquivo.name}</div>
              <div style={{ fontSize: 11.5, color: "#64748B", marginTop: 4 }}>
                {(arquivo.size / 1024).toFixed(0)} KB — clique ou arraste outro arquivo pra trocar
              </div>
            </div>
          ) : (
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: "#475569" }}>Clique ou arraste um PDF aqui</div>
              <div style={{ fontSize: 11.5, color: "#94A3B8", marginTop: 4 }}>Ex.: um ASO com um termo errado</div>
            </div>
          )}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 18 }}>
          <div>
            <label style={{ fontSize: 11.5, fontWeight: 700, color: "#475569", display: "block", marginBottom: 5 }}>Palavra atual (a errada)</label>
            <input value={palavraAtual} onChange={(e) => { setPalavraAtual(e.target.value); resetarResultado(); }}
              placeholder='ex.: "Cendo"'
              style={{ width: "100%", boxSizing: "border-box", padding: "9px 12px", borderRadius: 10, border: "1.5px solid #E2E8F0", fontSize: 13.5 }} />
          </div>
          <div>
            <label style={{ fontSize: 11.5, fontWeight: 700, color: "#475569", display: "block", marginBottom: 5 }}>Palavra nova (correta)</label>
            <input value={palavraNova} onChange={(e) => setPalavraNova(e.target.value)}
              placeholder='ex.: "Censo"'
              style={{ width: "100%", boxSizing: "border-box", padding: "9px 12px", borderRadius: 10, border: "1.5px solid #E2E8F0", fontSize: 13.5 }} />
          </div>
        </div>

        <label style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 12, fontSize: 12.5, color: "#64748B", cursor: "pointer" }}>
          <input type="checkbox" checked={caseSensitive} onChange={(e) => setCaseSensitive(e.target.checked)} />
          Diferenciar maiúsculas/minúsculas
        </label>

        <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
          <button onClick={buscar} disabled={buscando || !arquivo || !palavraAtual.trim()}
            style={{
              padding: "10px 18px", borderRadius: 10, border: "1.5px solid #CBD5E1", background: "#fff",
              color: "#334155", fontWeight: 700, fontSize: 13, cursor: "pointer",
              opacity: (buscando || !arquivo || !palavraAtual.trim()) ? 0.55 : 1,
            }}>
            {buscando ? "Procurando..." : "🔍 Onde aparece?"}
          </button>
          <button onClick={substituir} disabled={substituindo || !arquivo || !palavraAtual.trim() || !palavraNova.trim()}
            style={{
              padding: "10px 18px", borderRadius: 10, border: "none", background: "#059669",
              color: "#fff", fontWeight: 700, fontSize: 13, cursor: "pointer",
              opacity: (substituindo || !arquivo || !palavraAtual.trim() || !palavraNova.trim()) ? 0.55 : 1,
            }}>
            {substituindo ? "Editando..." : "✓ Trocar e baixar PDF"}
          </button>
        </div>

        {erro && (
          <div style={{ background: "#FEF2F2", border: "1.5px solid #FECACA", color: "#DC2626", borderRadius: 10, padding: "10px 14px", fontSize: 13, marginTop: 14 }}>
            ⚠ {erro}
          </div>
        )}
        {ok && (
          <div style={{ background: "#ECFDF5", border: "1.5px solid #A7F3D0", color: "#059669", borderRadius: 10, padding: "10px 14px", fontSize: 13, marginTop: 14 }}>
            ✓ {ok}
          </div>
        )}
      </div>

      {resultado && resultado.total > 0 && (
        <div style={{ background: "#fff", borderRadius: 16, padding: 24, boxShadow: "0 2px 8px rgba(0,0,0,0.07), 0 0 0 1px rgba(0,0,0,0.04)" }}>
          <div style={{ fontSize: 13.5, fontWeight: 800, color: "#111827", marginBottom: 14 }}>
            {resultado.total} ocorrência{resultado.total > 1 ? "s" : ""} encontrada{resultado.total > 1 ? "s" : ""} em {resultado.paginas.length} página{resultado.paginas.length > 1 ? "s" : ""}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {resultado.paginas.map((p) => (
              <div key={p.pagina} style={{ background: "#F8FAFC", borderRadius: 10, padding: "10px 14px" }}>
                <div style={{ fontSize: 11, fontWeight: 800, color: "#64748B", textTransform: "uppercase", marginBottom: 6 }}>
                  Página {p.pagina} — {p.ocorrencias} ocorrência{p.ocorrencias > 1 ? "s" : ""}
                </div>
                {p.contextos.map((c, i) => (
                  <div key={i} style={{ fontSize: 12.5, color: "#334155", lineHeight: 1.6 }}>{destacar(c, palavraAtual)}</div>
                ))}
              </div>
            ))}
          </div>
          <div style={{ fontSize: 11.5, color: "#94A3B8", marginTop: 14 }}>
            A troca substitui a palavra inteira em todas as ocorrências acima. Se a palavra nova for bem mais longa que a original, o texto pode se sobrepor ao vizinho — confira o PDF baixado antes de enviar.
          </div>
        </div>
      )}
    </div>
  );
}
