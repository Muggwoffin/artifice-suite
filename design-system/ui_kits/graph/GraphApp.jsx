const {Button,IconButton,Badge,Tag,Select,Sidebar,TitleBar,Panel,Input}=window.ArtificeDesignSystem_1fd848;

const DOCS=[
  {id:'1',label:'field-notes-1962.txt',meta:'112 nodes'},
  {id:'2',label:'correspondence.txt',meta:'64 nodes'},
  {id:'3',label:'census-extract.csv',meta:'340 nodes'}
];

const NODES=[
  {id:'p1',x:140,y:90,label:'Nyah Tran',type:'person'},
  {id:'p2',x:300,y:60,label:'Owusu Baidoo',type:'person'},
  {id:'l1',x:230,y:180,label:'border crossing',type:'event'},
  {id:'g1',x:400,y:170,label:'1962',type:'date'},
  {id:'g2',x:120,y:220,label:'refugee camp',type:'place'}
];
const EDGES=[['p1','l1'],['p2','l1'],['l1','g1'],['l1','g2']];
const COLORS={person:'var(--sage-600)',event:'var(--ink-700)',date:'var(--gold)',place:'var(--sage-400)'};

function GraphApp(){
  const [active,setActive]=React.useState('1');
  const [selected,setSelected]=React.useState('l1');
  const node=NODES.find(n=>n.id===selected);
  return (
    <div style={{display:'flex',flexDirection:'column',height:'100%',background:'var(--surface-page)',fontFamily:'var(--font-body)'}}>
      <TitleBar product="Graph" doc={DOCS.find(d=>d.id===active)?.label} actions={
        <div style={{display:'flex',gap:8,alignItems:'center'}}>
          <Select options={["local: llama-3.1-8b","gpt-4o-mini"]}/>
          <Button size="sm">Extract entities</Button>
        </div>
      }/>
      <div style={{display:'flex',flex:1,minHeight:0}}>
        <Sidebar items={DOCS} activeId={active} onSelect={setActive}/>
        <div style={{flex:1,position:'relative',background:'var(--parchment-200)'}}>
          <svg width="100%" height="100%" viewBox="0 0 480 280">
            {EDGES.map(([a,b],i)=>{
              const na=NODES.find(n=>n.id===a),nb=NODES.find(n=>n.id===b);
              return <line key={i} x1={na.x} y1={na.y} x2={nb.x} y2={nb.y} stroke="var(--ink-300)" strokeWidth="1.5"/>;
            })}
            {NODES.map(n=>(
              <g key={n.id} onClick={()=>setSelected(n.id)} style={{cursor:'pointer'}}>
                <circle cx={n.x} cy={n.y} r={selected===n.id?12:9} fill={COLORS[n.type]} stroke={selected===n.id?'var(--ink-900)':'none'} strokeWidth="2"/>
                <text x={n.x} y={n.y+24} textAnchor="middle" fontSize="11" fontFamily="Inter,sans-serif" fill="var(--ink-700)">{n.label}</text>
              </g>
            ))}
          </svg>
        </div>
        <div style={{width:300,borderLeft:'1px solid var(--border-subtle)',background:'var(--surface-card)',padding:16}}>
          <Panel title={node?.label} actions={<Badge tone="neutral">{node?.type}</Badge>}>
            <Input label="Label" value={node?.label}/>
            <div style={{marginTop:12,fontSize:12,color:'var(--text-secondary)'}}>Connected to {EDGES.filter(([a,b])=>a===selected||b===selected).length} nodes</div>
            <div style={{marginTop:10,display:'flex',gap:6,flexWrap:'wrap'}}>
              {NODES.filter(n=>n.id!==selected).slice(0,3).map(n=>(<Tag key={n.id}>{n.label}</Tag>))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
window.GraphApp=GraphApp;
