const {Button,IconButton,Badge,Tag,Input,Select,Sidebar,TitleBar,Tabs,Card,Panel,Toast}=window.ArtificeDesignSystem_1fd848;

const DOCS=[
  {id:'1',label:'chapter-three.md',meta:'2.1k w'},
  {id:'2',label:'letter-to-editor.md',meta:'420 w'},
  {id:'3',label:'grant-narrative.md',meta:'1.8k w'}
];

const SUGGESTIONS=[
  {id:1,type:'clarity',before:'in order to',after:'to',note:'Cut the wind-up.'},
  {id:2,type:'redundancy',before:'past history',after:'history',note:'"History" is already past.'},
  {id:3,type:'passive',before:'was reviewed by the committee',after:'the committee reviewed',note:'Prefer active voice.'}
];

function DraftApp(){
  const [activeDoc,setActiveDoc]=React.useState('1');
  const [tab,setTab]=React.useState('Suggestions');
  const [resolved,setResolved]=React.useState({});
  const [toast,setToast]=React.useState(null);

  const act=(id,verb)=>{
    setResolved(r=>({...r,[id]:verb}));
    setToast(`${verb==='accept'?'Accepted':'Rejected'} suggestion ${id}.`);
    setTimeout(()=>setToast(null),2200);
  };

  return (
    <div style={{display:'flex',flexDirection:'column',height:'100%',background:'var(--surface-page)',fontFamily:'var(--font-body)'}}>
      <TitleBar product="Draft" doc={DOCS.find(d=>d.id===activeDoc)?.label} actions={
        <div style={{display:'flex',gap:8,alignItems:'center'}}>
          <Select options={["local: llama-3.1-8b","gpt-4o-mini","claude-3-haiku"]}/>
          <Button size="sm">Save</Button>
        </div>
      }/>
      <div style={{display:'flex',flex:1,minHeight:0}}>
        <Sidebar items={DOCS} activeId={activeDoc} onSelect={setActiveDoc} footer={<Button size="sm" variant="ghost">+ New document</Button>}/>
        <div style={{flex:1,padding:24,overflowY:'auto',maxWidth:640}}>
          <div style={{font:'var(--text-display-md)',color:'var(--text-primary)',marginBottom:16}}>Chapter Three</div>
          <div style={{font:'var(--text-body-lg)',color:'var(--text-primary)',lineHeight:1.8}}>
            The committee's decision, <span style={{background:'var(--sage-100)',borderBottom:'2px solid var(--sage-500)',padding:'0 2px'}}>was reviewed by the committee</span> in order to determine whether the grant merited renewal. Given its past history of underfunding, the outcome was hardly a surprise.
          </div>
        </div>
        <div style={{width:340,borderLeft:'1px solid var(--border-subtle)',background:'var(--surface-card)',padding:16,overflowY:'auto'}}>
          <Tabs items={["Suggestions","Style notes"]} active={tab} onChange={setTab}/>
          <div style={{marginTop:14,display:'flex',flexDirection:'column',gap:10}}>
            {tab==='Suggestions' ? SUGGESTIONS.map(s=>{
              const r=resolved[s.id];
              return (
                <Card key={s.id} meta={s.type}>
                  <div style={{fontSize:13,marginBottom:8}}>
                    <span style={{textDecoration:'line-through',color:'var(--text-tertiary)'}}>{s.before}</span>
                    {' → '}
                    <span style={{color:'var(--sage-700)',fontWeight:600}}>{s.after}</span>
                  </div>
                  <div style={{fontSize:12,color:'var(--text-secondary)',marginBottom:10,fontStyle:'italic'}}>{s.note}</div>
                  {r ? <Badge tone={r==='accept'?'success':'neutral'}>{r==='accept'?'Accepted':'Rejected'}</Badge> :
                    <div style={{display:'flex',gap:6}}>
                      <Button size="sm" onClick={()=>act(s.id,'accept')}>Accept</Button>
                      <Button size="sm" variant="ghost" onClick={()=>act(s.id,'reject')}>Reject</Button>
                    </div>}
                </Card>
              );
            }) : <Panel title="Style notes">This document favors active voice and concision — consistent with prior chapters.</Panel>}
          </div>
        </div>
      </div>
      {toast && <div style={{position:'absolute',bottom:20,right:20}}><Toast tone="success">{toast}</Toast></div>}
    </div>
  );
}
window.DraftApp=DraftApp;
