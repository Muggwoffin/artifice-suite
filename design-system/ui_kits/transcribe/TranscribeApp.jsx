const {Button,IconButton,Badge,Tag,Select,Sidebar,TitleBar,Textarea,Dialog}=window.ArtificeDesignSystem_1fd848;

const FILES=[
  {id:'a',label:'1994-nyah-tran.wav',meta:'42m'},
  {id:'b',label:'1994-owusu-baidoo.wav',meta:'58m'},
  {id:'c',label:'1995-vasquez-mireles.wav',meta:'31m'}
];

const SEGMENTS=[
  {t:'00:00:04',speaker:'Interviewer',text:'Can you tell me about the crossing itself?'},
  {t:'00:00:11',speaker:'Nyah Tran',text:'The first winter we spent near the border, waiting for papers that never came.'},
  {t:'00:00:29',speaker:'Nyah Tran',text:'My brother kept a small radio. That was how we knew the war had not really ended.'}
];

function TranscribeApp(){
  const [active,setActive]=React.useState('a');
  const [showExport,setShowExport]=React.useState(false);
  return (
    <div style={{display:'flex',flexDirection:'column',height:'100%',background:'var(--surface-page)',fontFamily:'var(--font-body)',position:'relative'}}>
      <TitleBar product="Transcribe" doc={FILES.find(f=>f.id===active)?.label} actions={
        <div style={{display:'flex',gap:8,alignItems:'center'}}>
          <Select options={["local: whisper-large-v3","local: whisper-medium","gpt-4o-transcribe"]}/>
          <Button size="sm" onClick={()=>setShowExport(true)}>Export</Button>
        </div>
      }/>
      <div style={{display:'flex',flex:1,minHeight:0}}>
        <Sidebar items={FILES} activeId={active} onSelect={setActive}/>
        <div style={{flex:1,display:'flex',flexDirection:'column',minHeight:0}}>
          <div style={{height:72,borderBottom:'1px solid var(--border-subtle)',background:'var(--surface-card)',display:'flex',alignItems:'center',gap:12,padding:'0 16px'}}>
            <IconButton label="Play" icon={<span>&#9654;</span>}/>
            <div style={{flex:1,height:28,background:'repeating-linear-gradient(90deg,var(--sage-400) 0 2px,transparent 2px 5px)',borderRadius:4,opacity:0.6}}></div>
            <span style={{fontFamily:'var(--font-mono)',fontSize:12,color:'var(--text-secondary)'}}>00:00:29 / 00:42:10</span>
          </div>
          <div style={{flex:1,overflowY:'auto',padding:20,display:'flex',flexDirection:'column',gap:16}}>
            {SEGMENTS.map((s,i)=>(
              <div key={i} style={{display:'flex',gap:14}}>
                <span style={{fontFamily:'var(--font-mono)',fontSize:12,color:'var(--text-tertiary)',width:64,flexShrink:0,paddingTop:4}}>{s.t}</span>
                <div style={{flex:1}}>
                  <Tag>{s.speaker}</Tag>
                  <div style={{marginTop:6,font:'var(--text-body-lg)',color:'var(--text-primary)'}}>{s.text}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      {showExport && <Dialog title="Export transcript" actions={<><Button variant="secondary" size="sm" onClick={()=>setShowExport(false)}>Cancel</Button><Button size="sm" onClick={()=>setShowExport(false)}>Export as .docx</Button></>}>
        Includes speaker labels and timestamps. Names are not redacted.
      </Dialog>}
    </div>
  );
}
window.TranscribeApp=TranscribeApp;
