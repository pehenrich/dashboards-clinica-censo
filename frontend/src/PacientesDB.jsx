import { useState, useEffect } from "react";
import BriefingCard from "./BriefingCard";
import ServicosPorSexo from "./ServicosPorSexo";
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

// App.jsx:
//   import PacientesDB from "./PacientesDB";
//   NAV: { id:"pacientesdb", label:"Pacientes DB", icon:"users", color:"#0891B2", desc:"Base de pacientes" }
//   RENDER_MAP: pacientesdb: (p) => <PacientesDB periodo={p}/>

const API = `${window.location.protocol}//${window.location.host}`;

const MESES_PT = ["Janeiro","Fevereiro","Marco","Abril","Maio","Junho",
  "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"];

const C = {
  red:"#8B1A1A",green:"#059669",blue:"#0891B2",amber:"#D97706",
  purple:"#7C3AED",pink:"#DB2777",teal:"#0D9488",
  text:"#111827",sub:"#6B7280",faint:"#9CA3AF",border:"#F3F4F6",
};
const CORES=[C.red,C.blue,C.purple,C.green,C.amber,C.pink,C.teal,"#1E40AF","#92400E"];

const num = v => v!=null ? Number(v).toLocaleString("pt-BR") : "—";
const pct = v => v!=null ? `${Number(v).toFixed(1)}%` : "—";

function useFetch(path, deps={}) {
  const [data,setData]=useState(null);
  const [loading,setLoading]=useState(false);
  useEffect(()=>{
    if(!path)return;
    setLoading(true);
    const p=new URLSearchParams(Object.fromEntries(
      Object.entries(deps).filter(([,v])=>v!=null&&v!=="")
    ));
    fetch(`${API}${path}?${p}`)
      .then(r=>r.ok?r.json():null)
      .then(d=>{ setData(d); setLoading(false); })
      .catch(()=>setLoading(false));
  },[path,JSON.stringify(deps)]);
  return {data,loading};
}

const Skel = ({h=180}) => (
  <div style={{height:h,background:"#F3F4F6",borderRadius:10,animation:"pac-pulse 1.5s infinite"}}/>
);

function Card({children,title,subtitle,action,accent,noPad,style:ex={}}) {
  return (
    <div style={{background:"#fff",borderRadius:16,overflow:"hidden",
      boxShadow:"0 1px 4px rgba(0,0,0,0.07),0 0 0 1px rgba(0,0,0,0.04)",
      borderTop:accent?`3px solid ${accent}`:undefined,...ex}}>
      {(title||action)&&(
        <div style={{padding:"16px 20px 8px",display:"flex",alignItems:"flex-start",
          justifyContent:"space-between",gap:8}}>
          <div>
            <div style={{fontSize:13,fontWeight:700,color:C.text}}>{title}</div>
            {subtitle&&<div style={{fontSize:11,color:C.faint,marginTop:1}}>{subtitle}</div>}
          </div>
          {action&&<div style={{flexShrink:0}}>{action}</div>}
        </div>
      )}
      <div style={{padding:noPad?0:title?"0 20px 18px":"18px 20px"}}>{children}</div>
    </div>
  );
}

function KPI({label,value,sub,accent=C.red,loading,icon,trend}) {
  return (
    <div style={{background:"#fff",borderRadius:16,padding:"16px 18px",
      borderLeft:`4px solid ${accent}`,display:"flex",flexDirection:"column",gap:4,
      boxShadow:"0 1px 4px rgba(0,0,0,0.07),0 0 0 1px rgba(0,0,0,0.04)"}}>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between"}}>
        <span style={{fontSize:10,color:C.faint,fontWeight:700,textTransform:"uppercase",
          letterSpacing:"0.09em",lineHeight:1.2}}>{label}</span>
        {icon&&<span style={{fontSize:18,opacity:0.6}}>{icon}</span>}
      </div>
      {loading
        ? <div style={{height:30,width:"50%",background:"#F3F4F6",borderRadius:6,animation:"pac-pulse 1.5s infinite"}}/>
        : <div style={{fontSize:24,fontWeight:900,color:C.text,lineHeight:1.1,letterSpacing:"-0.5px"}}>{value}</div>
      }
      {sub&&(
        <span style={{fontSize:11,fontWeight:600,
          color:trend==="up"?C.green:trend==="down"?"#EF4444":C.faint}}>
          {trend==="up"?"↑ ":trend==="down"?"↓ ":""}{sub}
        </span>
      )}
    </div>
  );
}

function CTip({active,payload,label}) {
  if(!active||!payload?.length)return null;
  return (
    <div style={{background:"#fff",border:"1px solid #E5E7EB",borderRadius:10,
      padding:"10px 14px",fontSize:12,boxShadow:"0 8px 24px rgba(0,0,0,0.12)"}}>
      {label&&<div style={{color:C.text,marginBottom:5,fontWeight:700,fontSize:12}}>{label}</div>}
      {payload.map((p,i)=>(
        <div key={i} style={{color:p.color||C.sub,fontWeight:600,marginBottom:2}}>
          {p.name}: {Number(p.value).toLocaleString("pt-BR")}
        </div>
      ))}
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// MAPA DE CALOR
// ────────────────────────────────────────────────────────────
function MapaCalor({periodo,setor=""}) {
  const {data,loading} = useFetch("/api/pacientesdb/por-bairro",{periodo,setor});
  const [sel,setSel] = useState(null);
  const lista = data||[];
  const max = lista[0]?.total||1;

  const corCell = v => {
    const t = Math.pow(Math.min(v/max,1),0.55);
    return `rgb(${Math.round(255-t*116)},${Math.round(255-t*229)},${Math.round(255-t*229)})`;
  };

  const det = sel ? lista.find(x=>x.bairro===sel) : null;

  return (
    <Card title="Mapa de Calor — Logradouros"
      subtitle="Concentracao de pacientes por rua no periodo. Clique para detalhar.">
      {loading ? <Skel h={260}/> : lista.length===0 ? (
        <div style={{padding:48,textAlign:"center",color:C.faint,fontSize:13}}>Sem dados no periodo</div>
      ) : (
        <>
          <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(96px,1fr))",gap:6,marginBottom:12}}>
            {lista.map((b,i)=>{
              const ativo=sel===b.bairro;
              const claro=b.total/max<0.3;
              return (
                <div key={i} onClick={()=>setSel(ativo?null:b.bairro)}
                  style={{borderRadius:10,padding:"10px 6px",cursor:"pointer",textAlign:"center",
                    background:ativo?C.red:corCell(b.total),
                    border:`2px solid ${ativo?"#5a1111":"transparent"}`,
                    boxShadow:ativo?"0 4px 12px rgba(139,26,26,0.3)":"none",
                    transition:"all 0.15s"}}>
                  <div style={{fontSize:10,fontWeight:700,marginBottom:3,
                    color:ativo||!claro?"#fff":C.text,
                    overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>
                    {b.bairro}
                  </div>
                  <div style={{fontSize:17,fontWeight:900,lineHeight:1,
                    color:ativo||!claro?"#fff":C.text}}>
                    {num(b.total)}
                  </div>
                  <div style={{fontSize:9,marginTop:2,opacity:0.75,
                    color:ativo||!claro?"#fff":C.faint}}>
                    {pct(b.pct_total)}
                  </div>
                </div>
              );
            })}
          </div>

          {det&&(
            <div style={{background:"#FEF2F2",borderRadius:12,padding:"12px 16px",
              border:"1px solid #FECACA",display:"flex",flexWrap:"wrap",gap:16,alignItems:"center",marginBottom:10}}>
              <div style={{fontWeight:800,fontSize:15,color:C.red}}>📍 {det.bairro}</div>
              {[
                {l:"Atendidos",v:num(det.total),c:C.text},
                {l:"Novos",v:num(det.novos),c:C.green},
                {l:"Retorno",v:num(det.retorno),c:C.blue},
                {l:"Do total",v:pct(det.pct_total),c:C.purple},
              ].map(({l,v,c},i)=>(
                <div key={i}>
                  <div style={{fontSize:9,color:C.faint,fontWeight:700,textTransform:"uppercase"}}>{l}</div>
                  <div style={{fontSize:16,fontWeight:800,color:c}}>{v}</div>
                </div>
              ))}
              <button onClick={()=>setSel(null)}
                style={{marginLeft:"auto",background:"none",border:"none",color:C.red,fontSize:16,cursor:"pointer"}}>
                ✕
              </button>
            </div>
          )}

          <div style={{display:"flex",alignItems:"center",gap:8}}>
            <span style={{fontSize:9,color:C.faint}}>Menos</span>
            <div style={{flex:1,height:7,borderRadius:4,
              background:`linear-gradient(to right,#FFF5F5,#FCA5A5,${C.red})`}}/>
            <span style={{fontSize:9,color:C.faint}}>Mais</span>
          </div>
        </>
      )}
    </Card>
  );
}

// ────────────────────────────────────────────────────────────
// FAIXA ETARIA
// ────────────────────────────────────────────────────────────
function FaixaEtaria({periodo,setor=""}) {
  const {data,loading}=useFetch("/api/pacientes/faixa-etaria",{periodo,setor});
  return (
    <Card title="Faixa Etaria" subtitle="Por idade" accent={C.purple}>
      {loading?<Skel h={160}/>:(
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={data||[]} barSize={26} margin={{top:4,right:0,left:-24,bottom:0}}>
            <CartesianGrid strokeDasharray="2 4" stroke="#F3F4F6" vertical={false}/>
            <XAxis dataKey="faixa" tick={{fontSize:9,fill:C.faint}} axisLine={false} tickLine={false}/>
            <YAxis tick={{fontSize:9,fill:C.faint}} axisLine={false} tickLine={false}/>
            <Tooltip content={<CTip/>}/>
            <Bar dataKey="qtd" radius={[6,6,0,0]} name="Pacientes">
              {(data||[]).map((_,i)=><Cell key={i} fill={CORES[i%CORES.length]}/>)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}

// ────────────────────────────────────────────────────────────
// POR SEXO
// ────────────────────────────────────────────────────────────
function PorSexo({periodo,setor=""}) {
  const {data,loading}=useFetch("/api/pacientes/por-sexo",{periodo,setor});
  const total=(data||[]).reduce((s,r)=>s+(r.qtd||0),0);
  const SCOR={"M":"#0891B2","Masculino":"#0891B2","F":"#DB2777","Feminino":"#DB2777"};
  return (
    <Card title="Por Sexo" subtitle="Proporcao M/F" accent={C.pink}>
      {loading?<Skel h={160}/>:(
        <>
          <ResponsiveContainer width="100%" height={120}>
            <PieChart>
              <Pie data={data||[]} dataKey="qtd" nameKey="sexo"
                cx="50%" cy="50%" outerRadius={52} innerRadius={30} paddingAngle={3} labelLine={false}>
                {(data||[]).map((d,i)=><Cell key={i} fill={SCOR[d.sexo]||CORES[i]}/>)}
              </Pie>
              <Tooltip content={<CTip/>}/>
            </PieChart>
          </ResponsiveContainer>
          <div style={{display:"flex",gap:14,justifyContent:"center",marginTop:6}}>
            {(data||[]).map((d,i)=>(
              <div key={i} style={{display:"flex",alignItems:"center",gap:5}}>
                <div style={{width:8,height:8,borderRadius:"50%",background:SCOR[d.sexo]||CORES[i]}}/>
                <span style={{fontSize:11,color:C.sub,fontWeight:600}}>{d.sexo}</span>
                <span style={{fontSize:11,color:C.faint}}>
                  {total>0?`${((d.qtd/total)*100).toFixed(0)}%`:""}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}

// ────────────────────────────────────────────────────────────
// CRESCIMENTO
// ────────────────────────────────────────────────────────────
function CrescimentoBase({setor=""}) {
  const {data,loading}=useFetch("/api/pacientesdb/crescimento-base",{periodo:"ano",setor});
  const total=(data||[]).reduce((s,r)=>s+(r.novos||0),0);
  return (
    <Card title="Novos Cadastros no Ano"
      subtitle={`${num(total)} novos pacientes em 2026`} accent={C.green}>
      {loading?<Skel h={180}/>:(
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={data||[]} barSize={32} margin={{top:4,right:4,left:-20,bottom:0}}>
            <CartesianGrid strokeDasharray="2 4" stroke="#F3F4F6" vertical={false}/>
            <XAxis dataKey="mes" tick={{fontSize:10,fill:C.faint}} axisLine={false} tickLine={false}/>
            <YAxis tick={{fontSize:10,fill:C.faint}} axisLine={false} tickLine={false}/>
            <Tooltip content={<CTip/>}/>
            <Bar dataKey="novos" name="Novos pacientes" radius={[6,6,0,0]}>
              {(data||[]).map((_,i,arr)=>(
                <Cell key={i} fill={i===arr.length-1?"#A7F3D0":C.green}/>
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}

// ────────────────────────────────────────────────────────────
// RETORNO VS NOVOS
// ────────────────────────────────────────────────────────────
function RetornoVsNovos({setor=""}) {
  const {data,loading}=useFetch("/api/pacientesdb/retorno-vs-novos",{periodo:"ano",setor});
  const totN=(data||[]).reduce((s,r)=>s+(r.novos||0),0);
  const totR=(data||[]).reduce((s,r)=>s+(r.retorno||0),0);
  const tx=totN+totR>0?((totR/(totN+totR))*100).toFixed(0):0;
  return (
    <Card title="Retorno vs. Novos por Mes"
      subtitle={`Fidelizacao: ${tx}% de retorno no ano`} accent={C.blue}>
      {loading?<Skel h={180}/>:(
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={data||[]} barSize={13} barGap={3} margin={{top:4,right:4,left:-20,bottom:0}}>
            <CartesianGrid strokeDasharray="2 4" stroke="#F3F4F6" vertical={false}/>
            <XAxis dataKey="mes" tick={{fontSize:10,fill:C.faint}} axisLine={false} tickLine={false}/>
            <YAxis tick={{fontSize:10,fill:C.faint}} axisLine={false} tickLine={false}/>
            <Tooltip content={<CTip/>}/>
            <Legend iconSize={8} iconType="circle" wrapperStyle={{fontSize:11,paddingTop:4}}/>
            <Bar dataKey="novos"   fill={C.green} radius={[4,4,0,0]} name="Novos"/>
            <Bar dataKey="retorno" fill={C.blue}  radius={[4,4,0,0]} name="Retorno"/>
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}

// ────────────────────────────────────────────────────────────
// RANKING
// ────────────────────────────────────────────────────────────
function Ranking({periodo,setor=""}) {
  const anoAtual=new Date().getFullYear();
  const mesAtual=new Date().getMonth()+1;
  const [modo,setModo]=useState("30d");
  const [mesSel,setMesSel]=useState(mesAtual);
  const [limite,setLimite]=useState(20);
  const [busca,setBusca]=useState("");

  const params=(()=>{
    if(modo==="30d")  return {periodo:"30d",limite,setor};
    if(modo==="tudo") return {todo_periodo:true,limite,setor};
    if(modo==="mensal"){
      const ult=new Date(anoAtual,mesSel,0).getDate();
      return {
        inicio:`${anoAtual}-${String(mesSel).padStart(2,"0")}-01`,
        fim:`${anoAtual}-${String(mesSel).padStart(2,"0")}-${ult}`,
        limite,setor
      };
    }
    return {periodo:"30d",limite,setor};
  })();

  const {data,loading}=useFetch("/api/pacientes/top-atendimentos",params);

  const filtrados=(data||[]).filter(r=>
    !busca||
    r.nome?.toLowerCase().includes(busca.toLowerCase())||
    r.bairro?.toLowerCase().includes(busca.toLowerCase())||
    r.convenio?.toLowerCase().includes(busca.toLowerCase())
  );

  const maxV=filtrados[0]?.total_atendimentos||1;
  const MED=["🥇","🥈","🥉"];
  const RBGS=["#FFFBEB","#F0F9FF","#F0FFF4"];

  const btnM=(m,l)=>(
    <button key={m} onClick={()=>setModo(m)} style={{
      padding:"5px 12px",borderRadius:8,fontSize:11,fontWeight:700,cursor:"pointer",
      border:`1.5px solid ${modo===m?C.blue:"#E5E7EB"}`,
      background:modo===m?C.blue:"#fff",
      color:modo===m?"#fff":C.sub,transition:"all 0.13s",
    }}>{l}</button>
  );

  return (
    <Card title="🏆 Pacientes Mais Frequentes" subtitle="Ranking por numero de atendimentos">
      <div style={{display:"flex",flexWrap:"wrap",gap:6,marginBottom:10,alignItems:"center"}}>
        {[["30d","Mes atual"],["mensal","Mes especifico"],["tudo","Todo periodo"]].map(([m,l])=>btnM(m,l))}
        <div style={{marginLeft:"auto",display:"flex",gap:4,alignItems:"center"}}>
          <span style={{fontSize:10,color:C.faint,fontWeight:600}}>Top:</span>
          {[10,20,50].map(n=>(
            <button key={n} onClick={()=>setLimite(n)} style={{
              padding:"4px 10px",borderRadius:7,fontSize:11,fontWeight:700,cursor:"pointer",
              border:`1px solid ${limite===n?C.blue:"#E5E7EB"}`,
              background:limite===n?"#E0F2FE":"#fff",
              color:limite===n?C.blue:C.faint,
            }}>{n}</button>
          ))}
        </div>
      </div>

      {modo==="mensal"&&(
        <div style={{display:"flex",flexWrap:"wrap",gap:4,marginBottom:10}}>
          {MESES_PT.map((m,i)=>(
            <button key={i+1} onClick={()=>setMesSel(i+1)} style={{
              padding:"4px 10px",borderRadius:7,fontSize:10,fontWeight:700,cursor:"pointer",
              border:`1px solid ${mesSel===i+1?C.blue:"#E5E7EB"}`,
              background:mesSel===i+1?C.blue:"#F8FAFC",
              color:mesSel===i+1?"#fff":C.faint,
            }}>{m.slice(0,3)}</button>
          ))}
        </div>
      )}

      <div style={{position:"relative",marginBottom:12}}>
        <span style={{position:"absolute",left:10,top:"50%",transform:"translateY(-50%)",color:C.faint,fontSize:13}}>🔍</span>
        <input placeholder="Buscar nome, rua ou convenio..."
          value={busca} onChange={e=>setBusca(e.target.value)}
          style={{width:"100%",padding:"8px 12px 8px 30px",borderRadius:9,
            border:"1px solid #E5E7EB",background:"#F8FAFC",fontSize:12,
            outline:"none",boxSizing:"border-box"}}/>
      </div>

      {loading?<Skel h={300}/>:(
        <div style={{overflowY:"auto",maxHeight:400,borderRadius:10,border:"1px solid #F3F4F6"}}>
          <table style={{width:"100%",fontSize:12,borderCollapse:"collapse"}}>
            <thead style={{position:"sticky",top:0,background:"#F8FAFC",zIndex:1}}>
              <tr>
                {["#","Paciente","Sexo","Logradouro","Convenio","Atend.","Ultimo atend."].map(h=>(
                  <th key={h} style={{padding:"10px 12px",fontWeight:700,textAlign:"left",
                    fontSize:10,textTransform:"uppercase",color:C.faint,
                    borderBottom:"2px solid #F3F4F6",whiteSpace:"nowrap"}}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtrados.length===0?(
                <tr><td colSpan={7} style={{padding:32,textAlign:"center",color:C.faint}}>
                  Nenhum resultado
                </td></tr>
              ):filtrados.map((r,i)=>{
                const bg=i<3?RBGS[i]:"#fff";
                return (
                  <tr key={i}
                    style={{borderBottom:"1px solid #F9FAFB",background:bg,transition:"background 0.1s"}}
                    onMouseEnter={e=>e.currentTarget.style.background="#F0F9FF"}
                    onMouseLeave={e=>e.currentTarget.style.background=bg}>
                    <td style={{padding:"10px 12px",fontWeight:700,color:C.faint,width:36}}>
                      {i<3?MED[i]:`#${i+1}`}
                    </td>
                    <td style={{padding:"10px 12px",color:C.text,fontWeight:i<3?700:500,
                      maxWidth:160,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>
                      {r.nome}
                      {r.idade?<span style={{fontSize:10,color:C.faint,marginLeft:6}}>{r.idade}a</span>:null}
                    </td>
                    <td style={{padding:"10px 12px"}}>
                      <span style={{padding:"2px 8px",borderRadius:12,fontSize:10,fontWeight:700,
                        background:r.sexo==="M"?"#DBEAFE":"#FCE7F3",
                        color:r.sexo==="M"?C.blue:C.pink}}>
                        {r.sexo==="M"?"♂ M":"♀ F"}
                      </span>
                    </td>
                    <td style={{padding:"10px 12px",color:C.faint,fontSize:11,
                      maxWidth:110,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>
                      {r.bairro||"—"}
                    </td>
                    <td style={{padding:"10px 12px",color:C.faint,fontSize:11,
                      maxWidth:100,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>
                      {r.convenio||"—"}
                    </td>
                    <td style={{padding:"10px 12px"}}>
                      <div style={{display:"flex",alignItems:"center",gap:8}}>
                        <div style={{height:5,borderRadius:3,background:"#E0F2FE",width:50,flexShrink:0}}>
                          <div style={{height:"100%",borderRadius:3,background:C.blue,
                            width:`${Math.min((r.total_atendimentos/maxV)*100,100)}%`}}/>
                        </div>
                        <span style={{fontSize:15,fontWeight:900,color:C.blue,minWidth:20}}>
                          {r.total_atendimentos}
                        </span>
                      </div>
                    </td>
                    <td style={{padding:"10px 12px",color:C.faint,fontSize:11,whiteSpace:"nowrap"}}>
                      {r.ultimo_atendimento
                        ?new Date(r.ultimo_atendimento).toLocaleDateString("pt-BR"):"—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ────────────────────────────────────────────────────────────
// ANIVERSARIANTES
// ────────────────────────────────────────────────────────────
function Aniversariantes() {
  const hoje=new Date();
  const mesAtual=hoje.getMonth()+1;
  const diaHoje=hoje.getDate();
  const [mes,setMes]=useState(mesAtual);
  const [busca,setBusca]=useState("");
  const [soHoje,setSoHoje]=useState(false);

  const {data,loading}=useFetch("/api/pacientes/aniversariantes",{mes});

  const filtrados=(data||[]).filter(r=>{
    const mb=!busca||r.nome?.toLowerCase().includes(busca.toLowerCase());
    const mh=!soHoje||(r.dia===diaHoje&&mes===mesAtual);
    return mb&&mh;
  });

  const hojeLista=(data||[]).filter(r=>r.dia===diaHoje&&mes===mesAtual);

  return (
    <Card title="🎂 Aniversariantes"
      action={hojeLista.length>0?(
        <div style={{background:"#ECFDF5",color:C.green,borderRadius:8,
          padding:"4px 10px",fontSize:11,fontWeight:700,border:"1px solid #A7F3D0",whiteSpace:"nowrap"}}>
          🎉 {hojeLista.length} hoje!
        </div>
      ):null}>

      {/* Seletor de mes */}
      <div style={{display:"flex",flexWrap:"wrap",gap:4,marginBottom:10}}>
        {MESES_PT.map((m,i)=>{
          const eh=i+1===mesAtual;
          const sel=mes===i+1;
          return (
            <button key={i+1} onClick={()=>{setMes(i+1);setSoHoje(false);}} style={{
              padding:"4px 9px",borderRadius:7,fontSize:10,fontWeight:700,cursor:"pointer",
              border:`1px solid ${sel?C.red:eh?"#FECDD3":"#E5E7EB"}`,
              background:sel?C.red:eh?"#FEF2F2":"#F8FAFC",
              color:sel?"#fff":eh?C.red:C.faint,
              position:"relative",
            }}>
              {m.slice(0,3)}
              {eh&&!sel&&<span style={{position:"absolute",top:-3,right:-3,width:5,height:5,
                borderRadius:"50%",background:C.red}}/>}
            </button>
          );
        })}
      </div>

      {/* Busca + filtro hoje */}
      <div style={{display:"flex",gap:6,marginBottom:10}}>
        <input placeholder="Buscar paciente..."
          value={busca} onChange={e=>setBusca(e.target.value)}
          style={{flex:1,padding:"7px 12px",borderRadius:8,border:"1px solid #E5E7EB",
            background:"#F8FAFC",fontSize:12,outline:"none"}}/>
        {mes===mesAtual&&(
          <button onClick={()=>setSoHoje(v=>!v)} style={{
            padding:"7px 12px",borderRadius:8,whiteSpace:"nowrap",
            border:`1px solid ${soHoje?C.green:"#E5E7EB"}`,
            background:soHoje?"#ECFDF5":"#fff",
            color:soHoje?C.green:C.faint,
            fontSize:11,fontWeight:700,cursor:"pointer",
          }}>🎂 Hoje</button>
        )}
      </div>

      {!loading&&(
        <div style={{fontSize:11,color:C.faint,marginBottom:8}}>
          <span style={{color:C.red,fontWeight:700}}>{filtrados.length}</span> aniversariante{filtrados.length!==1?"s":""} em{" "}
          <span style={{color:C.text,fontWeight:600}}>{MESES_PT[mes-1]}</span>
        </div>
      )}

      {loading?<Skel h={240}/>:(
        <div style={{overflowY:"auto",maxHeight:400,display:"flex",flexDirection:"column",gap:6}}>
          {filtrados.length===0?(
            <div style={{padding:32,textAlign:"center",color:C.faint,fontSize:13}}>
              Nenhum aniversariante encontrado
            </div>
          ):filtrados.map((r,i)=>{
            const ehHoje=mes===mesAtual&&r.dia===diaHoje;
            const diasAte=mes===mesAtual?r.dia-diaHoje:null;
            return (
              <div key={i} style={{display:"flex",alignItems:"center",gap:10,
                padding:"10px 12px",borderRadius:10,
                border:`1px solid ${ehHoje?"#A7F3D0":"#F3F4F6"}`,
                background:ehHoje?"#ECFDF5":"#fff",
                transition:"background 0.1s"}}
                onMouseEnter={e=>{if(!ehHoje)e.currentTarget.style.background="#F8FAFC";}}
                onMouseLeave={e=>{if(!ehHoje)e.currentTarget.style.background="#fff";}}>

                {/* Avatar */}
                <div style={{width:38,height:38,borderRadius:"50%",flexShrink:0,
                  background:ehHoje?C.green:"#FEF2F2",
                  color:ehHoje?"#fff":C.red,
                  display:"flex",alignItems:"center",justifyContent:"center",
                  fontSize:ehHoje?18:14,fontWeight:800}}>
                  {ehHoje?"🎂":r.dia}
                </div>

                {/* Info */}
                <div style={{flex:1,minWidth:0}}>
                  <div style={{fontSize:13,fontWeight:700,color:C.text,
                    overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>
                    {r.nome}
                  </div>
                  <div style={{fontSize:10,color:C.faint,marginTop:2,display:"flex",gap:8,flexWrap:"wrap"}}>
                    {r.idade&&<span>{r.idade} anos</span>}
                    {r.fone&&<span>📞 {r.fone}</span>}
                    {r.celular&&<span>📱 {r.celular}</span>}
                    {r.whatsapp==="S"&&<span style={{color:"#22C55E",fontWeight:700}}>💬 WhatsApp</span>}
                  </div>
                </div>

                {/* Badges */}
                <div style={{display:"flex",flexDirection:"column",alignItems:"flex-end",gap:4,flexShrink:0}}>
                  <span style={{padding:"2px 7px",borderRadius:12,fontSize:10,fontWeight:700,
                    background:r.sexo==="M"?"#DBEAFE":"#FCE7F3",
                    color:r.sexo==="M"?C.blue:C.pink}}>
                    {r.sexo==="M"?"♂ M":"♀ F"}
                  </span>
                  {ehHoje&&<span style={{fontSize:10,fontWeight:700,color:C.green}}>Hoje! 🎉</span>}
                  {!ehHoje&&diasAte!=null&&diasAte>0&&(
                    <span style={{fontSize:10,color:C.faint}}>em {diasAte}d</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

// ────────────────────────────────────────────────────────────
// MAIN
// ────────────────────────────────────────────────────────────
const SETORES = [
  { cod:"",    nome:"Todos os Setores" },
  { cod:"RCN", nome:"Consultórios" },
  { cod:"ROC", nome:"Ocupacional" },
  { cod:"RDI", nome:"Diagnóstico" },
];

const useIsMobile = () => { const [m, setM] = useState(window.innerWidth < 768); useEffect(() => { const fn = () => setM(window.innerWidth < 768); window.addEventListener("resize", fn); return () => window.removeEventListener("resize", fn); }, []); return m; };

export default function PacientesDB({periodo="30d"}) {
  const isMobile = useIsMobile();
  const [setor, setSetor] = useState("");

  const {data:resumo,loading:lR}=useFetch("/api/pacientes/resumo",{periodo,setor});
  const {data:bairros,loading:lB}=useFetch("/api/pacientesdb/por-bairro",{periodo,setor});
  const topRua=bairros?.[0];

  return (
    <div style={{display:"flex",flexDirection:"column",gap:14}}>
      <style>{`
        @keyframes pac-pulse {0%,100%{opacity:1}50%{opacity:.45}}
      `}</style>

      <BriefingCard
        cor="#0891B2"
        cacheKey={`briefing_pacientesdb_${periodo}_${setor}`}
        disabled={lR || lB}
        promptFn={() => `Você é um analista de gestão clínica. Gere um briefing executivo em no máximo 4 frases, direto e profissional, sem markdown.

DADOS — Base de Pacientes (período: ${periodo}${setor ? ", setor: "+setor : ""}):
- Pacientes atendidos no período: ${resumo?.pacientes_atendidos ?? "n/d"}
- Novos cadastros: ${resumo?.novos_cadastros ?? "n/d"}
- Pacientes de retorno: ${resumo?.retorno ?? "n/d"}
- Base total de pacientes: ${resumo?.total_base ?? "n/d"}
- Rua/bairro com maior concentração: ${topRua ? topRua.bairro+" ("+topRua.total+" pacientes)" : "n/d"}

Destaque crescimento da base, fidelização de retornos e oportunidades de captação por área geográfica.`}
      />

      {/* ── FILTRO DE SETOR ── */}
      <div style={{display:"flex",alignItems:"center",gap:8,flexWrap:"wrap"}}>
        <span style={{fontSize:11,color:C.faint,fontWeight:700,textTransform:"uppercase",
          letterSpacing:"0.07em"}}>Setor:</span>
        {SETORES.map(s=>(
          <button key={s.cod} onClick={()=>setSetor(s.cod)} style={{
            padding:"6px 16px",borderRadius:9,fontSize:12,fontWeight:700,cursor:"pointer",
            border:`1.5px solid ${setor===s.cod?C.blue:"#E5E7EB"}`,
            background:setor===s.cod?C.blue:"#fff",
            color:setor===s.cod?"#fff":C.sub,
            transition:"all 0.13s",
            boxShadow:setor===s.cod?"0 2px 8px rgba(8,145,178,0.25)":"none",
          }}>{s.nome}</button>
        ))}
        {setor&&(
          <span style={{fontSize:11,color:C.faint,marginLeft:4}}>
            · filtrando por <strong style={{color:C.blue}}>
              {SETORES.find(s=>s.cod===setor)?.nome}
            </strong>
          </span>
        )}
      </div>

      {/* ROW 1 — KPIs */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(140px,1fr))",gap:12}}>
        <KPI label="Atendidos"       value={num(resumo?.pacientes_atendidos)} accent={C.red}    loading={lR} icon="👥"/>
        <KPI label="Novos Cadastros" value={num(resumo?.novos_cadastros)}     accent={C.green}  loading={lR} icon="✨" sub="no periodo" trend="up"/>
        <KPI label="Retorno"         value={num(resumo?.retorno)}             accent={C.blue}   loading={lR} icon="🔄" sub="mais de 1 atendimento"/>
        <KPI label="Base Total"      value={num(resumo?.total_base)}          accent={C.amber}  loading={lR} icon="🗄️"/>
        <KPI label="Rua Mais Freq."
          value={lB?"...":(topRua?.bairro||"—")}
          accent={C.purple} loading={lB} icon="📍"
          sub={topRua?`${num(topRua.total)} pacientes`:""}/>
      </div>

      {/* ROW 2 — Mapa + Faixa + Sexo */}
      <MapaCalor periodo={periodo} setor={setor}/>
      
      {/* ROW 3 — Crescimento + Retorno vs Novos */}
      <div style={{display:"grid",gridTemplateColumns:isMobile?"1fr":"1fr 1fr",gap:12}}>
        <CrescimentoBase setor={setor}/>
        <RetornoVsNovos setor={setor}/>
      </div>

      {/* ROW 4 — Ranking */}
      <Ranking periodo={periodo} setor={setor}/>

      {/* ROW 5 — Aniversariantes */}
      <Aniversariantes/>

      {/* ROW 6 — Serviços por Sexo */}
      <ServicosPorSexo periodo={periodo} setor={setor}/>
    </div>
  );
}