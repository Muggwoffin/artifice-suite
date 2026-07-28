const {Button,IconButton,Badge,Select,Sidebar,TitleBar,Card,Textarea,ProgressBar,EmptyState}=window.ArtificeDesignSystem_1fd848;

const PAGES=[
  {id:'12',label:'page-012.tif',meta:'done'},
  {id:'13',label:'page-013.tif',meta:'done'},
  {id:'14',label:'page-014.tif',meta:'review'},
  {id:'15',label:'page-015.tif',meta:'queued'},
  {id:'16',label:'page-016.tif',meta:'queued'}
];

function OcrApp(){
  const [active,setActive]=React.useState('14');
  const [running,setRunning]=React.useState(false);
  const [progress,setProgress]=React.useState(38);
  const page=PAGES.find(p=>p.id===active);

  React.useEffect(()=>{
    if(!running) return;
    const t=setInterval(()=>setProgress(p=>Math.min(100,p+7)),260);
    return ()=>clearInterval(t);
  },[running]);

  return (
    <div style={{display:'flex',flexDirection:'column',height:'100%',background:'var(--surface-page)',fontFamily:'var(--font-body)'}}>
      <TitleBar product="OCR" doc={page?.label} actions={
        <div style={{display:'flex',gap:8,alignItems:'center'}}>
          <Select options={["local: tesseract-best","local: paddleocr","gpt-4o-mini (vision)"]}/>
          <Button size="sm" onClick={()=>{setRunning(true);setProgress(0);}}>Run batch</Button>
        </div>
      }/>
      {running && <div style={{padding:'8px 16px',borderBottom:'1px solid var(--border-subtle)',background:'var(--surface-card)'}}><ProgressBar value={progress} label={`Recognizing text — ${progress}%`}/></div>}
      <div style={{display:'flex',flex:1,minHeight:0}}>
        <Sidebar items={PAGES.map(p=>({id:p.id,label:p.label,meta:p.meta}))} activeId={active} onSelect={setActive}/>
        <div style={{flex:1,display:'flex',gap:1,background:'var(--border-subtle)'}}>
          <div style={{flex:1,background:'var(--ink-100)',display:'flex',alignItems:'center',justifyContent:'center',color:'var(--ink-500)',fontFamily:'var(--font-mono)',fontSize:12}}>
            scanned page image — {page?.label}
          </div>
          <div style={{flex:1,background:'var(--surface-card)',padding:16,display:'flex',flexDirection:'column',gap:10}}>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
              <span style={{font:'var(--text-title)'}}>Extracted text</span>
              <Badge tone={page?.meta==='done'?'success':page?.meta==='review'?'warning':'neutral'}>{page?.meta}</Badge>
            </div>
            {page?.meta==='queued' ? <EmptyState title="Not yet processed." description="This page is waiting in the batch queue."/> :
              <Textarea rows={12} value={"...the survey party reached the ridge on the fourth\nday, having lost two mules to the crossing. what timber\nremained had been marked for the railway..."}/>}
          </div>
        </div>
      </div>
    </div>
  );
}
window.OcrApp=OcrApp;
