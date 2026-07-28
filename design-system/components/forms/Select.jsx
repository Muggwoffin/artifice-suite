import React from 'react';
export function Select({label,options=[],value,onChange}){
  return React.createElement('label',{style:{display:'flex',flexDirection:'column',gap:4,fontFamily:'var(--font-body)'}},
    label&&React.createElement('span',{style:{fontSize:12,fontWeight:500,color:'var(--text-secondary)'}},label),
    React.createElement('select',{value,onChange,style:{fontFamily:'var(--font-body)',fontSize:14,color:'var(--text-primary)',background:'var(--surface-card-raised)',border:'1px solid var(--border-default)',borderRadius:'var(--radius-sm)',padding:'8px 10px'}},
      options.map(o=>React.createElement('option',{key:o,value:o},o))
    )
  );
}
