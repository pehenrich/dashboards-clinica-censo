import { useState, useEffect, useRef, useCallback } from "react";

const API = `${window.location.protocol}//${window.location.host}`;

const CORES_SETOR = ["#8B1A1A", "#0891B2", "#D97706", "#7C3AED", "#10B981", "#DC2626", "#0D9488", "#DB2777"];
const LARGURA_NO = 190;
const ALTURA_NO = 78;

function iniciais(nome) {
  const partes = (nome || "").trim().split(/\s+/).filter(Boolean);
  if (!partes.length) return "?";
  return partes.length === 1 ? partes[0][0].toUpperCase() : (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
}

function NoOrganograma({ no, ativo, redimensionando, onMouseDown, onRedimensionarDown, onEditar }) {
  const [hover, setHover] = useState(false);
  const cor = no.cor || "#8B1A1A";
  const largura = no.largura || LARGURA_NO;
  const altura = no.altura || ALTURA_NO;
  const destacado = ativo || redimensionando;
  return (
    <div
      onMouseDown={(e) => onMouseDown(e, no)}
      onDoubleClick={() => onEditar(no)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        position: "absolute", left: no.pos_x, top: no.pos_y,
        width: largura, height: altura,
        background: "#fff", borderRadius: 12,
        border: "1px solid #EEF1F5", borderTop: `3px solid ${cor}`,
        boxShadow: destacado
          ? `0 10px 28px rgba(0,0,0,0.22), 0 0 0 2px ${cor}55`
          : hover ? "0 6px 16px rgba(15,23,42,0.14)" : "0 1px 3px rgba(15,23,42,0.08)",
        padding: "10px 12px 10px 14px", cursor: "grab", userSelect: "none", overflow: "hidden",
        display: "flex", alignItems: "center", gap: 10,
        zIndex: destacado ? 20 : 2,
        transform: destacado ? "translateY(-2px) scale(1.01)" : hover ? "translateY(-1px)" : "none",
        transition: destacado ? "none" : "box-shadow 0.15s, transform 0.15s",
      }}
      title="Arraste para mover · duplo clique para editar · puxe o canto pra redimensionar"
    >
      <div style={{
        flexShrink: 0, width: 34, height: 34, borderRadius: "50%",
        background: `linear-gradient(135deg, ${cor}, ${cor}CC)`,
        display: "flex", alignItems: "center", justifyContent: "center",
        color: "#fff", fontSize: 12.5, fontWeight: 800, letterSpacing: "-0.02em",
        boxShadow: `0 2px 6px ${cor}55`,
      }}>
        {iniciais(no.nome)}
      </div>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 800, color: "#111827", overflowWrap: "break-word", lineHeight: 1.2 }}>{no.nome}</div>
        {no.cargo && <div style={{ fontSize: 11.5, color: "#64748B", marginTop: 2, lineHeight: 1.25 }}>{no.cargo}</div>}
        {no.setor && (
          <div style={{
            display: "inline-block", fontSize: 9, color: cor, background: `${cor}14`,
            textTransform: "uppercase", letterSpacing: "0.04em", marginTop: 4, fontWeight: 800,
            padding: "2px 6px", borderRadius: 5,
          }}>
            {no.setor}
          </div>
        )}
      </div>
      <div
        onMouseDown={(e) => onRedimensionarDown(e, no)}
        style={{
          position: "absolute", right: 0, bottom: 0, width: 16, height: 16,
          cursor: "nwse-resize", zIndex: 21,
          background: "linear-gradient(135deg, transparent 50%, #CBD5E1 50%)",
          borderBottomRightRadius: 12,
          opacity: hover || destacado ? 1 : 0, transition: "opacity 0.15s",
        }}
        title="Redimensionar"
      />
    </div>
  );
}

function ModalNo({ no, nos, onSalvar, onExcluir, onFechar }) {
  const editando = !!no?.id;
  const [nome, setNome] = useState(no?.nome || "");
  const [cargo, setCargo] = useState(no?.cargo || "");
  const [setor, setSetor] = useState(no?.setor || "");
  const [paiId, setPaiId] = useState(no?.pai_id ?? "");
  const [cor, setCor] = useState(no?.cor || CORES_SETOR[0]);
  const [salvando, setSalvando] = useState(false);

  const opcoesPai = nos.filter((n) => n.id !== no?.id);

  const salvar = async () => {
    if (!nome.trim()) return;
    setSalvando(true);
    await onSalvar({
      nome: nome.trim(),
      cargo: cargo.trim() || null,
      setor: setor.trim() || null,
      pai_id: paiId === "" ? null : Number(paiId),
      cor,
    });
    setSalvando(false);
  };

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 9999, background: "rgba(0,0,0,0.45)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
    }} onClick={onFechar}>
      <div style={{
        background: "#fff", borderRadius: 16, padding: 24, width: "100%", maxWidth: 420,
        boxShadow: "0 8px 40px rgba(0,0,0,0.25)",
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{ fontSize: 16, fontWeight: 800, color: "#111827", marginBottom: 18 }}>
          {editando ? "Editar Cargo" : "Novo Cargo"}
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, color: "#64748B", fontWeight: 700, display: "block", marginBottom: 4 }}>Nome</label>
          <input value={nome} onChange={(e) => setNome(e.target.value)} autoFocus
            style={{ width: "100%", padding: "9px 12px", borderRadius: 8, border: "1px solid #E2E8F0", fontSize: 13.5, outline: "none", boxSizing: "border-box" }} />
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, color: "#64748B", fontWeight: 700, display: "block", marginBottom: 4 }}>Cargo</label>
          <input value={cargo} onChange={(e) => setCargo(e.target.value)} placeholder="Ex: Coordenador Financeiro"
            style={{ width: "100%", padding: "9px 12px", borderRadius: 8, border: "1px solid #E2E8F0", fontSize: 13.5, outline: "none", boxSizing: "border-box" }} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
          <div>
            <label style={{ fontSize: 11, color: "#64748B", fontWeight: 700, display: "block", marginBottom: 4 }}>Setor</label>
            <input value={setor} onChange={(e) => setSetor(e.target.value)} placeholder="Ex: Financeiro"
              style={{ width: "100%", padding: "9px 12px", borderRadius: 8, border: "1px solid #E2E8F0", fontSize: 13.5, outline: "none", boxSizing: "border-box" }} />
          </div>
          <div>
            <label style={{ fontSize: 11, color: "#64748B", fontWeight: 700, display: "block", marginBottom: 4 }}>Cor</label>
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap", paddingTop: 6 }}>
              {CORES_SETOR.map((c) => (
                <div key={c} onClick={() => setCor(c)} style={{
                  width: 20, height: 20, borderRadius: "50%", background: c, cursor: "pointer",
                  border: cor === c ? "2px solid #111827" : "2px solid transparent",
                }} />
              ))}
            </div>
          </div>
        </div>

        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: 11, color: "#64748B", fontWeight: 700, display: "block", marginBottom: 4 }}>Superior direto</label>
          <select value={paiId} onChange={(e) => setPaiId(e.target.value)}
            style={{ width: "100%", padding: "9px 12px", borderRadius: 8, border: "1px solid #E2E8F0", fontSize: 13.5, outline: "none", boxSizing: "border-box" }}>
            <option value="">— Nenhum (topo do organograma) —</option>
            {opcoesPai.map((n) => <option key={n.id} value={n.id}>{n.nome}{n.cargo ? ` — ${n.cargo}` : ""}</option>)}
          </select>
        </div>

        <div style={{ display: "flex", gap: 8, justifyContent: "space-between" }}>
          {editando ? (
            <button onClick={() => onExcluir(no.id)} style={{
              padding: "10px 16px", borderRadius: 8, border: "1.5px solid #EF4444",
              background: "#fff", color: "#EF4444", fontSize: 13, fontWeight: 700, cursor: "pointer",
            }}>Excluir</button>
          ) : <div />}
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={onFechar} style={{
              padding: "10px 18px", borderRadius: 8, border: "1.5px solid #E2E8F0",
              background: "#fff", color: "#64748B", fontSize: 13, fontWeight: 700, cursor: "pointer",
            }}>Cancelar</button>
            <button onClick={salvar} disabled={!nome.trim() || salvando} style={{
              padding: "10px 20px", borderRadius: 8, border: "none",
              background: nome.trim() ? "#8B1A1A" : "#E2E8F0",
              color: nome.trim() ? "#fff" : "#9CA3AF",
              fontSize: 13, fontWeight: 700, cursor: nome.trim() ? "pointer" : "not-allowed",
            }}>{salvando ? "Salvando..." : "Salvar"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function LinhasConexao({ nos }) {
  const byId = Object.fromEntries(nos.map((n) => [n.id, n]));
  return (
    <svg style={{ position: "absolute", left: 0, top: 0, width: "100%", height: "100%", pointerEvents: "none", overflow: "visible" }}>
      {nos.filter((n) => n.pai_id && byId[n.pai_id]).map((n) => {
        const pai = byId[n.pai_id];
        const x1 = pai.pos_x + (pai.largura || LARGURA_NO) / 2, y1 = pai.pos_y + (pai.altura || ALTURA_NO);
        const x2 = n.pos_x + (n.largura || LARGURA_NO) / 2, y2 = n.pos_y;
        const midY = (y1 + y2) / 2;
        // Linhas retas (cotovelo): desce do pai, atravessa na horizontal, desce até o filho —
        // mesmo estilo clássico de organograma, sem curvas.
        return (
          <path key={n.id} d={`M ${x1} ${y1} L ${x1} ${midY} L ${x2} ${midY} L ${x2} ${y2}`}
            stroke="#CBD5E1" strokeWidth={2} fill="none" strokeLinejoin="round" strokeLinecap="round" />
        );
      })}
    </svg>
  );
}

export default function Gestao() {
  const [nos, setNos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalNo, setModalNo] = useState(undefined); // undefined=fechado, null=novo, {...}=editar
  const [arrastando, setArrastando] = useState(null);
  const [redimensionando, setRedimensionando] = useState(null);
  const [baixandoPdf, setBaixandoPdf] = useState(false);
  const [telaCheia, setTelaCheia] = useState(false);
  const containerRef = useRef(null);
  const raizRef = useRef(null);
  const dragRef = useRef(null);
  const resizeRef = useRef(null);

  const carregar = useCallback(() => {
    setLoading(true);
    fetch(`${API}/api/organograma/nos`).then((r) => r.json()).then((d) => { setNos(d || []); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  useEffect(() => {
    const handler = () => setTelaCheia(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

  const alternarTelaCheia = () => {
    if (!document.fullscreenElement) raizRef.current?.requestFullscreen();
    else document.exitFullscreen();
  };

  const iniciarArrasto = (e, no) => {
    if (e.button !== 0) return;
    const rect = containerRef.current.getBoundingClientRect();
    dragRef.current = {
      id: no.id,
      offsetX: e.clientX - rect.left - no.pos_x + containerRef.current.scrollLeft,
      offsetY: e.clientY - rect.top - no.pos_y + containerRef.current.scrollTop,
    };
    setArrastando(no.id);
    e.preventDefault();
  };

  const MIN_LARGURA = 120, MIN_ALTURA = 56;

  const iniciarRedimensionamento = (e, no) => {
    if (e.button !== 0) return;
    resizeRef.current = {
      id: no.id, startX: e.clientX, startY: e.clientY,
      largura: no.largura || LARGURA_NO, altura: no.altura || ALTURA_NO,
    };
    setRedimensionando(no.id);
    e.preventDefault();
    e.stopPropagation();
  };

  useEffect(() => {
    const mover = (e) => {
      if (dragRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        const novoX = Math.max(0, e.clientX - rect.left - dragRef.current.offsetX + containerRef.current.scrollLeft);
        const novoY = Math.max(0, e.clientY - rect.top - dragRef.current.offsetY + containerRef.current.scrollTop);
        setNos((prev) => prev.map((n) => n.id === dragRef.current.id ? { ...n, pos_x: novoX, pos_y: novoY } : n));
      } else if (resizeRef.current) {
        const { id, startX, startY, largura, altura } = resizeRef.current;
        const novaLargura = Math.max(MIN_LARGURA, largura + (e.clientX - startX));
        const novaAltura = Math.max(MIN_ALTURA, altura + (e.clientY - startY));
        setNos((prev) => prev.map((n) => n.id === id ? { ...n, largura: novaLargura, altura: novaAltura } : n));
      }
    };
    const soltar = () => {
      if (dragRef.current) {
        const id = dragRef.current.id;
        const no = nos.find((n) => n.id === id);
        dragRef.current = null;
        setArrastando(null);
        if (no) {
          fetch(`${API}/api/organograma/nos/${id}`, {
            method: "PUT", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pos_x: no.pos_x, pos_y: no.pos_y }),
          }).catch(() => {});
        }
      } else if (resizeRef.current) {
        const id = resizeRef.current.id;
        const no = nos.find((n) => n.id === id);
        resizeRef.current = null;
        setRedimensionando(null);
        if (no) {
          fetch(`${API}/api/organograma/nos/${id}`, {
            method: "PUT", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ largura: no.largura, altura: no.altura }),
          }).catch(() => {});
        }
      }
    };
    window.addEventListener("mousemove", mover);
    window.addEventListener("mouseup", soltar);
    return () => { window.removeEventListener("mousemove", mover); window.removeEventListener("mouseup", soltar); };
  }, [nos]);

  const salvarNo = async (dados) => {
    if (modalNo?.id) {
      await fetch(`${API}/api/organograma/nos/${modalNo.id}`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
      });
    } else {
      const scrollTop = containerRef.current?.scrollTop || 0;
      const scrollLeft = containerRef.current?.scrollLeft || 0;
      await fetch(`${API}/api/organograma/nos`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...dados, pos_x: scrollLeft + 60, pos_y: scrollTop + 40 }),
      });
    }
    setModalNo(undefined);
    carregar();
  };

  const excluirNo = async (id) => {
    if (!window.confirm("Excluir este cargo? Quem estiver abaixo dele fica sem superior direto.")) return;
    await fetch(`${API}/api/organograma/nos/${id}`, { method: "DELETE" });
    setModalNo(undefined);
    carregar();
  };

  const baixarPdf = async () => {
    setBaixandoPdf(true);
    try {
      const r = await fetch(`${API}/api/organograma/pdf`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const blob = await r.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "Organograma.pdf";
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (e) {
      alert("Erro ao gerar PDF: " + e.message);
    } finally {
      setBaixandoPdf(false);
    }
  };

  const larguraCanvas = Math.max(1400, ...nos.map((n) => n.pos_x + (n.largura || LARGURA_NO) + 200));
  const alturaCanvas = Math.max(900, ...nos.map((n) => n.pos_y + (n.altura || ALTURA_NO) + 200));

  return (
    <div ref={raizRef} style={{
      display: "flex", flexDirection: "column", gap: 14,
      height: telaCheia ? "100vh" : "calc(100vh - 220px)", minHeight: 500,
      background: telaCheia ? "#fff" : "transparent",
      padding: telaCheia ? 16 : 0, boxSizing: "border-box",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 800, color: "#111827" }}>🗂️ Organograma</div>
          <div style={{ fontSize: 12, color: "#94A3B8" }}>Arraste os cargos para organizar · duplo clique para editar</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => setModalNo(null)} style={{
            padding: "9px 18px", borderRadius: 10, border: "none",
            background: "#8B1A1A", color: "#fff", fontSize: 13, fontWeight: 700, cursor: "pointer",
          }}>+ Novo Cargo</button>
          <button onClick={baixarPdf} disabled={baixandoPdf || !nos.length} style={{
            padding: "9px 18px", borderRadius: 10, border: "1.5px solid #8B1A1A",
            background: "#fff", color: "#8B1A1A", fontSize: 13, fontWeight: 700,
            cursor: nos.length ? "pointer" : "not-allowed", opacity: nos.length ? 1 : 0.5,
          }}>{baixandoPdf ? "Gerando..." : "🖨️ Imprimir / PDF"}</button>
          <button onClick={alternarTelaCheia} title={telaCheia ? "Sair da tela cheia" : "Tela cheia"} style={{
            width: 38, height: 38, padding: 0, borderRadius: 10, border: "1.5px solid #E2E8F0",
            background: "#fff", color: "#475569", fontSize: 16, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>{telaCheia ? "✕" : "⛶"}</button>
        </div>
      </div>

      <div
        ref={containerRef}
        style={{
          flex: 1, background: "#F8FAFC", borderRadius: 14, position: "relative",
          overflow: "auto", boxShadow: "0 1px 4px rgba(0,0,0,0.07)",
          backgroundImage: "radial-gradient(circle, #E2E8F0 1px, transparent 1px)",
          backgroundSize: "22px 22px",
        }}
      >
        <div style={{ position: "relative", width: larguraCanvas, height: alturaCanvas }}>
          {loading ? (
            <div style={{ padding: 40, color: "#94A3B8", fontSize: 13 }}>Carregando...</div>
          ) : nos.length === 0 ? (
            <div style={{ padding: 60, textAlign: "center", color: "#94A3B8", fontSize: 13 }}>
              Organograma vazio. Clique em "+ Novo Cargo" para começar.
            </div>
          ) : (
            <>
              <LinhasConexao nos={nos} />
              {nos.map((no) => (
                <NoOrganograma key={no.id} no={no} ativo={arrastando === no.id} redimensionando={redimensionando === no.id}
                  onMouseDown={iniciarArrasto} onRedimensionarDown={iniciarRedimensionamento} onEditar={setModalNo} />
              ))}
            </>
          )}
        </div>
      </div>

      {modalNo !== undefined && (
        <ModalNo no={modalNo} nos={nos} onSalvar={salvarNo} onExcluir={excluirNo} onFechar={() => setModalNo(undefined)} />
      )}
    </div>
  );
}
