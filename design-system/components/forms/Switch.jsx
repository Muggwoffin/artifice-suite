// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

import React from 'react';
export function Switch({label,checked,onChange}){
  return React.createElement('label',{style:{display:'inline-flex',alignItems:'center',gap:8,fontFamily:'var(--font-body)',fontSize:14,color:'var(--text-primary)',cursor:'pointer'}},
    React.createElement('span',{onClick:()=>onChange&&onChange(!checked),style:{width:32,height:18,borderRadius:'var(--radius-pill)',background:checked?'var(--sage-500)':'var(--parchment-500)',position:'relative',transition:'background var(--duration-fast) var(--ease-standard)',display:'inline-block'}},
      React.createElement('span',{style:{position:'absolute',top:2,left:checked?16:2,width:14,height:14,borderRadius:'50%',background:'var(--paper-raised)',transition:'left var(--duration-fast) var(--ease-standard)'}})
    ),
    label
  );
}
