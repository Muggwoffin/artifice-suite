// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: MIT

import React from 'react';
export function IconButton({icon,label,active,onClick}){
  return React.createElement('button',{title:label,'aria-label':label,onClick,style:{width:32,height:32,display:'inline-flex',alignItems:'center',justifyContent:'center',background:active?'var(--sage-100)':'transparent',color:active?'var(--sage-700)':'var(--text-secondary)',border:'none',borderRadius:'var(--radius-sm)',cursor:'pointer'}},icon);
}
