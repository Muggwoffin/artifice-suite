import React from 'react';
export function Button({variant='primary',size='md',icon,disabled,children,onClick}){
  const [hover,setHover]=React.useState(false);
  const base={fontFamily:'var(--font-label)',fontWeight:600,fontSize:size==='sm'?12:13,letterSpacing:'var(--label-tracking)',textTransform:'uppercase',cursor:disabled?'default':'pointer',display:'inline-flex',alignItems:'center',gap:6,padding:size==='sm'?'0.55rem 1rem':'0.8rem 1.4rem',borderRadius:'var(--radius-md)',transition:'background-color var(--duration-normal) ease,color var(--duration-normal) ease,box-shadow var(--duration-normal) ease,transform var(--duration-normal) ease',opacity:disabled?0.5:1};
  const variants={
    primary:hover&&!disabled?{background:'var(--ink)',color:'var(--paper-raised)',border:'1.5px solid var(--ink)',boxShadow:'var(--shadow-hard-hover)',transform:'translate(-1px,-1px)'}:{background:'var(--paper-raised)',color:'var(--ink)',border:'1.5px solid var(--ink)',boxShadow:'var(--shadow-hard)'},
    secondary:{background:'transparent',color:'var(--text-primary)',border:'1.5px solid var(--rule)'},
    ghost:{background:'transparent',color:'var(--text-primary)',border:'1.5px solid transparent'},
    danger:{background:'var(--state-danger)',color:'var(--paper-raised)',border:'1.5px solid var(--state-danger)'}
  };
  return React.createElement('button',{style:{...base,...variants[variant]},disabled,onClick,onMouseEnter:()=>setHover(true),onMouseLeave:()=>setHover(false)},icon,children);
}
