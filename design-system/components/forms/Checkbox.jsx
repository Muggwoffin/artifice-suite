import React from 'react';
export function Checkbox({label,checked,onChange}){
  return React.createElement('label',{style:{display:'inline-flex',alignItems:'center',gap:8,fontFamily:'var(--font-body)',fontSize:14,color:'var(--text-primary)',cursor:'pointer'}},
    React.createElement('input',{type:'checkbox',checked,onChange,style:{width:16,height:16,accentColor:'var(--sage-500)'}}),
    label
  );
}
