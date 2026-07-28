import React from 'react';
export function ProgressBar({value=0,label}){
  return React.createElement('div',{style:{fontFamily:'var(--font-body)'}},
    label&&React.createElement('div',{style:{fontSize:12,color:'var(--text-secondary)',marginBottom:4}},label),
    React.createElement('div',{style:{height:6,background:'var(--parchment-400)',borderRadius:'var(--radius-pill)',overflow:'hidden'}},
      React.createElement('div',{style:{width:`${value}%`,height:'100%',background:'var(--sage-500)',transition:'width var(--duration-slow) var(--ease-standard)'}})
    )
  );
}
