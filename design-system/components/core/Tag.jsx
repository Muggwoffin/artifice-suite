import React from 'react';
export function Tag({children,onRemove}){
  return React.createElement('span',{style:{display:'inline-flex',alignItems:'center',gap:4,background:'var(--surface-sunken)',color:'var(--text-primary)',fontFamily:'var(--font-mono)',fontSize:12,padding:'3px 8px',borderRadius:'var(--radius-sm)',border:'1px solid var(--border-subtle)'}},children,onRemove&&React.createElement('button',{onClick:onRemove,style:{background:'none',border:'none',cursor:'pointer',color:'var(--text-tertiary)',fontSize:12,padding:0}},'\u00d7'));
}
