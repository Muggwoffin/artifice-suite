// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

import React from 'react';
export function Dialog({title,children,onClose,actions}){
  return React.createElement('div',{style:{position:'absolute',inset:0,background:'rgba(23,23,15,.4)',display:'flex',alignItems:'center',justifyContent:'center'}},
    React.createElement('div',{style:{background:'var(--surface-card-raised)',borderRadius:'var(--radius-lg)',boxShadow:'var(--shadow-lg)',width:360,padding:20,fontFamily:'var(--font-body)'}},
      React.createElement('div',{style:{font:'var(--text-title)',color:'var(--text-primary)',marginBottom:8}},title),
      React.createElement('div',{style:{font:'var(--text-body)',color:'var(--text-secondary)',marginBottom:16}},children),
      React.createElement('div',{style:{display:'flex',justifyContent:'flex-end',gap:8}},actions)
    )
  );
}
