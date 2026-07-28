import React from 'react';
export function Panel({title,actions,children}){
  return React.createElement('div',{style:{background:'var(--surface-card-raised)',border:'1px solid var(--border-subtle)',borderRadius:'var(--radius-xl)',fontFamily:'var(--font-body)',overflow:'hidden',boxShadow:'var(--shadow-paper)'}},
    (title||actions)&&React.createElement('div',{style:{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'10px 14px',borderBottom:'1px solid var(--border-subtle)'}},
      React.createElement('span',{style:{font:'var(--text-title)',color:'var(--text-primary)'}},title),
      actions
    ),
    React.createElement('div',{style:{padding:14}},children)
  );
}
