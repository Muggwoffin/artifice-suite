// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: MIT

/* @ds-bundle: {"format":4,"namespace":"ArtificeDesignSystem_1fd848","components":[{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"IconButton","sourcePath":"components/core/IconButton.jsx"},{"name":"Tag","sourcePath":"components/core/Tag.jsx"},{"name":"Dialog","sourcePath":"components/feedback/Dialog.jsx"},{"name":"EmptyState","sourcePath":"components/feedback/EmptyState.jsx"},{"name":"ProgressBar","sourcePath":"components/feedback/ProgressBar.jsx"},{"name":"Toast","sourcePath":"components/feedback/Toast.jsx"},{"name":"Checkbox","sourcePath":"components/forms/Checkbox.jsx"},{"name":"Input","sourcePath":"components/forms/Input.jsx"},{"name":"Select","sourcePath":"components/forms/Select.jsx"},{"name":"Switch","sourcePath":"components/forms/Switch.jsx"},{"name":"Textarea","sourcePath":"components/forms/Textarea.jsx"},{"name":"Sidebar","sourcePath":"components/navigation/Sidebar.jsx"},{"name":"Tabs","sourcePath":"components/navigation/Tabs.jsx"},{"name":"TitleBar","sourcePath":"components/navigation/TitleBar.jsx"},{"name":"Card","sourcePath":"components/surfaces/Card.jsx"},{"name":"Panel","sourcePath":"components/surfaces/Panel.jsx"}],"sourceHashes":{"components/core/Badge.jsx":"7c59b3abf3f9","components/core/Button.jsx":"1cbd27b92ea3","components/core/IconButton.jsx":"1fd31ba0b5fe","components/core/Tag.jsx":"47bffc87c6bf","components/feedback/Dialog.jsx":"4881a7ea34eb","components/feedback/EmptyState.jsx":"c8247a10684e","components/feedback/ProgressBar.jsx":"d91b4cb7d207","components/feedback/Toast.jsx":"5e481c82474d","components/forms/Checkbox.jsx":"b19fef66f929","components/forms/Input.jsx":"bed58382836a","components/forms/Select.jsx":"c2206a24ad28","components/forms/Switch.jsx":"34dbebd56b49","components/forms/Textarea.jsx":"ce453274d9bc","components/navigation/Sidebar.jsx":"98a18aee011d","components/navigation/Tabs.jsx":"e1e6a47d6a43","components/navigation/TitleBar.jsx":"e595c9593252","components/surfaces/Card.jsx":"8dd84b79cc2c","components/surfaces/Panel.jsx":"b0ebb93bd13e","ui_kits/draft/DraftApp.jsx":"3badde51c1b8","ui_kits/graph/GraphApp.jsx":"546b2bcf451d","ui_kits/ocr/OcrApp.jsx":"8c6652b7bc1d","ui_kits/transcribe/TranscribeApp.jsx":"c94f7e59b696"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.ArtificeDesignSystem_1fd848 = window.ArtificeDesignSystem_1fd848 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/core/Badge.jsx
try { (() => {
function Badge({
  tone = 'neutral',
  children
}) {
  const tones = {
    neutral: {
      background: 'var(--parchment-400)',
      color: 'var(--ink-700)'
    },
    success: {
      background: 'var(--sage-100)',
      color: 'var(--sage-700)'
    },
    warning: {
      background: 'var(--state-warning-soft)',
      color: 'var(--state-warning)'
    },
    danger: {
      background: 'var(--state-danger-soft)',
      color: 'var(--state-danger)'
    }
  };
  return React.createElement('span', {
    style: {
      ...tones[tone],
      fontFamily: 'var(--font-body)',
      fontSize: 11,
      fontWeight: 600,
      letterSpacing: 'var(--tracking-label)',
      textTransform: 'uppercase',
      padding: '3px 8px',
      borderRadius: 'var(--radius-pill)',
      display: 'inline-block'
    }
  }, children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function Button({
  variant = 'primary',
  size = 'md',
  icon,
  disabled,
  children,
  onClick
}) {
  const [hover, setHover] = React.useState(false);
  const base = {
    fontFamily: 'var(--font-label)',
    fontWeight: 600,
    fontSize: size === 'sm' ? 12 : 13,
    letterSpacing: 'var(--label-tracking)',
    textTransform: 'uppercase',
    cursor: disabled ? 'default' : 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: size === 'sm' ? '0.55rem 1rem' : '0.8rem 1.4rem',
    borderRadius: 'var(--radius-md)',
    transition: 'background-color var(--duration-normal) ease,color var(--duration-normal) ease,box-shadow var(--duration-normal) ease,transform var(--duration-normal) ease',
    opacity: disabled ? 0.5 : 1
  };
  const variants = {
    primary: hover && !disabled ? {
      background: 'var(--ink)',
      color: 'var(--paper-raised)',
      border: '1.5px solid var(--ink)',
      boxShadow: 'var(--shadow-hard-hover)',
      transform: 'translate(-1px,-1px)'
    } : {
      background: 'var(--paper-raised)',
      color: 'var(--ink)',
      border: '1.5px solid var(--ink)',
      boxShadow: 'var(--shadow-hard)'
    },
    secondary: {
      background: 'transparent',
      color: 'var(--text-primary)',
      border: '1.5px solid var(--rule)'
    },
    ghost: {
      background: 'transparent',
      color: 'var(--text-primary)',
      border: '1.5px solid transparent'
    },
    danger: {
      background: 'var(--state-danger)',
      color: 'var(--paper-raised)',
      border: '1.5px solid var(--state-danger)'
    }
  };
  return React.createElement('button', {
    style: {
      ...base,
      ...variants[variant]
    },
    disabled,
    onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false)
  }, icon, children);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/IconButton.jsx
try { (() => {
function IconButton({
  icon,
  label,
  active,
  onClick
}) {
  return React.createElement('button', {
    title: label,
    'aria-label': label,
    onClick,
    style: {
      width: 32,
      height: 32,
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: active ? 'var(--sage-100)' : 'transparent',
      color: active ? 'var(--sage-700)' : 'var(--text-secondary)',
      border: 'none',
      borderRadius: 'var(--radius-sm)',
      cursor: 'pointer'
    }
  }, icon);
}
Object.assign(__ds_scope, { IconButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/IconButton.jsx", error: String((e && e.message) || e) }); }

// components/core/Tag.jsx
try { (() => {
function Tag({
  children,
  onRemove
}) {
  return React.createElement('span', {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      background: 'var(--surface-sunken)',
      color: 'var(--text-primary)',
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      padding: '3px 8px',
      borderRadius: 'var(--radius-sm)',
      border: '1px solid var(--border-subtle)'
    }
  }, children, onRemove && React.createElement('button', {
    onClick: onRemove,
    style: {
      background: 'none',
      border: 'none',
      cursor: 'pointer',
      color: 'var(--text-tertiary)',
      fontSize: 12,
      padding: 0
    }
  }, '\u00d7'));
}
Object.assign(__ds_scope, { Tag });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Tag.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Dialog.jsx
try { (() => {
function Dialog({
  title,
  children,
  onClose,
  actions
}) {
  return React.createElement('div', {
    style: {
      position: 'absolute',
      inset: 0,
      background: 'rgba(23,23,15,.4)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center'
    }
  }, React.createElement('div', {
    style: {
      background: 'var(--surface-card-raised)',
      borderRadius: 'var(--radius-lg)',
      boxShadow: 'var(--shadow-lg)',
      width: 360,
      padding: 20,
      fontFamily: 'var(--font-body)'
    }
  }, React.createElement('div', {
    style: {
      font: 'var(--text-title)',
      color: 'var(--text-primary)',
      marginBottom: 8
    }
  }, title), React.createElement('div', {
    style: {
      font: 'var(--text-body)',
      color: 'var(--text-secondary)',
      marginBottom: 16
    }
  }, children), React.createElement('div', {
    style: {
      display: 'flex',
      justifyContent: 'flex-end',
      gap: 8
    }
  }, actions)));
}
Object.assign(__ds_scope, { Dialog });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Dialog.jsx", error: String((e && e.message) || e) }); }

// components/feedback/EmptyState.jsx
try { (() => {
function EmptyState({
  title,
  description,
  action
}) {
  return React.createElement('div', {
    style: {
      textAlign: 'center',
      padding: '40px 20px',
      fontFamily: 'var(--font-body)'
    }
  }, React.createElement('div', {
    style: {
      font: 'var(--text-headline)',
      color: 'var(--text-primary)',
      marginBottom: 6
    }
  }, title), React.createElement('div', {
    style: {
      font: 'var(--text-body)',
      color: 'var(--text-tertiary)',
      marginBottom: 16
    }
  }, description), action);
}
Object.assign(__ds_scope, { EmptyState });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/EmptyState.jsx", error: String((e && e.message) || e) }); }

// components/feedback/ProgressBar.jsx
try { (() => {
function ProgressBar({
  value = 0,
  label
}) {
  return React.createElement('div', {
    style: {
      fontFamily: 'var(--font-body)'
    }
  }, label && React.createElement('div', {
    style: {
      fontSize: 12,
      color: 'var(--text-secondary)',
      marginBottom: 4
    }
  }, label), React.createElement('div', {
    style: {
      height: 6,
      background: 'var(--parchment-400)',
      borderRadius: 'var(--radius-pill)',
      overflow: 'hidden'
    }
  }, React.createElement('div', {
    style: {
      width: `${value}%`,
      height: '100%',
      background: 'var(--sage-500)',
      transition: 'width var(--duration-slow) var(--ease-standard)'
    }
  })));
}
Object.assign(__ds_scope, { ProgressBar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/ProgressBar.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Toast.jsx
try { (() => {
function Toast({
  tone = 'neutral',
  children,
  onClose
}) {
  const tones = {
    neutral: 'var(--ink)',
    success: 'var(--accent-darker)',
    danger: 'var(--state-danger)'
  };
  return React.createElement('div', {
    style: {
      background: tones[tone],
      color: 'var(--paper-raised)',
      fontFamily: 'var(--font-label)',
      fontSize: 13,
      padding: '10px 14px',
      borderRadius: 'var(--radius-md)',
      boxShadow: 'var(--shadow-md)',
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      maxWidth: 320
    }
  }, React.createElement('span', {
    style: {
      flex: 1
    }
  }, children), onClose && React.createElement('button', {
    onClick: onClose,
    style: {
      background: 'none',
      border: 'none',
      color: 'inherit',
      opacity: 0.7,
      cursor: 'pointer'
    }
  }, '\u00d7'));
}
Object.assign(__ds_scope, { Toast });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Toast.jsx", error: String((e && e.message) || e) }); }

// components/forms/Checkbox.jsx
try { (() => {
function Checkbox({
  label,
  checked,
  onChange
}) {
  return React.createElement('label', {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 8,
      fontFamily: 'var(--font-body)',
      fontSize: 14,
      color: 'var(--text-primary)',
      cursor: 'pointer'
    }
  }, React.createElement('input', {
    type: 'checkbox',
    checked,
    onChange,
    style: {
      width: 16,
      height: 16,
      accentColor: 'var(--sage-500)'
    }
  }), label);
}
Object.assign(__ds_scope, { Checkbox });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Checkbox.jsx", error: String((e && e.message) || e) }); }

// components/forms/Input.jsx
try { (() => {
const base = {
  fontFamily: 'var(--font-body)',
  fontSize: 14,
  color: 'var(--text-primary)',
  background: 'var(--surface-card-raised)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-sm)',
  padding: '8px 10px',
  outline: 'none'
};
function Input({
  label,
  placeholder,
  value,
  onChange
}) {
  return React.createElement('label', {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
      fontFamily: 'var(--font-body)'
    }
  }, label && React.createElement('span', {
    style: {
      fontSize: 12,
      fontWeight: 500,
      color: 'var(--text-secondary)'
    }
  }, label), React.createElement('input', {
    style: base,
    placeholder,
    value,
    onChange
  }));
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Input.jsx", error: String((e && e.message) || e) }); }

// components/forms/Select.jsx
try { (() => {
function Select({
  label,
  options = [],
  value,
  onChange
}) {
  return React.createElement('label', {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
      fontFamily: 'var(--font-body)'
    }
  }, label && React.createElement('span', {
    style: {
      fontSize: 12,
      fontWeight: 500,
      color: 'var(--text-secondary)'
    }
  }, label), React.createElement('select', {
    value,
    onChange,
    style: {
      fontFamily: 'var(--font-body)',
      fontSize: 14,
      color: 'var(--text-primary)',
      background: 'var(--surface-card-raised)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-sm)',
      padding: '8px 10px'
    }
  }, options.map(o => React.createElement('option', {
    key: o,
    value: o
  }, o))));
}
Object.assign(__ds_scope, { Select });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Select.jsx", error: String((e && e.message) || e) }); }

// components/forms/Switch.jsx
try { (() => {
function Switch({
  label,
  checked,
  onChange
}) {
  return React.createElement('label', {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 8,
      fontFamily: 'var(--font-body)',
      fontSize: 14,
      color: 'var(--text-primary)',
      cursor: 'pointer'
    }
  }, React.createElement('span', {
    onClick: () => onChange && onChange(!checked),
    style: {
      width: 32,
      height: 18,
      borderRadius: 'var(--radius-pill)',
      background: checked ? 'var(--sage-500)' : 'var(--parchment-500)',
      position: 'relative',
      transition: 'background var(--duration-fast) var(--ease-standard)',
      display: 'inline-block'
    }
  }, React.createElement('span', {
    style: {
      position: 'absolute',
      top: 2,
      left: checked ? 16 : 2,
      width: 14,
      height: 14,
      borderRadius: '50%',
      background: 'var(--paper-raised)',
      transition: 'left var(--duration-fast) var(--ease-standard)'
    }
  })), label);
}
Object.assign(__ds_scope, { Switch });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Switch.jsx", error: String((e && e.message) || e) }); }

// components/forms/Textarea.jsx
try { (() => {
function Textarea({
  label,
  placeholder,
  rows = 4,
  value,
  onChange
}) {
  return React.createElement('label', {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
      fontFamily: 'var(--font-body)'
    }
  }, label && React.createElement('span', {
    style: {
      fontSize: 12,
      fontWeight: 500,
      color: 'var(--text-secondary)'
    }
  }, label), React.createElement('textarea', {
    rows,
    placeholder,
    value,
    onChange,
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 13,
      lineHeight: 1.6,
      color: 'var(--text-primary)',
      background: 'var(--surface-card-raised)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-sm)',
      padding: '8px 10px',
      outline: 'none',
      resize: 'vertical'
    }
  }));
}
Object.assign(__ds_scope, { Textarea });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Textarea.jsx", error: String((e && e.message) || e) }); }

// components/navigation/Sidebar.jsx
try { (() => {
function Sidebar({
  items = [],
  activeId,
  onSelect,
  footer
}) {
  return React.createElement('div', {
    style: {
      width: 220,
      background: 'var(--parchment-200)',
      borderRight: '1px solid var(--border-subtle)',
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      fontFamily: 'var(--font-body)'
    }
  }, React.createElement('div', {
    style: {
      flex: 1,
      overflowY: 'auto',
      padding: 8
    }
  }, items.map(it => React.createElement('div', {
    key: it.id,
    onClick: () => onSelect && onSelect(it.id),
    style: {
      padding: '7px 10px',
      borderRadius: 'var(--radius-sm)',
      fontSize: 13,
      color: it.id === activeId ? 'var(--text-primary)' : 'var(--text-secondary)',
      background: it.id === activeId ? 'var(--surface-card-raised)' : 'transparent',
      cursor: 'pointer',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center'
    }
  }, React.createElement('span', null, it.label), it.meta && React.createElement('span', {
    style: {
      fontSize: 11,
      color: 'var(--text-tertiary)',
      fontFamily: 'var(--font-mono)'
    }
  }, it.meta)))), footer && React.createElement('div', {
    style: {
      borderTop: '1px solid var(--border-subtle)',
      padding: 10
    }
  }, footer));
}
Object.assign(__ds_scope, { Sidebar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/Sidebar.jsx", error: String((e && e.message) || e) }); }

// components/navigation/Tabs.jsx
try { (() => {
function Tabs({
  items = [],
  active,
  onChange
}) {
  return React.createElement('div', {
    style: {
      display: 'flex',
      gap: 4,
      borderBottom: '1px solid var(--border-subtle)',
      fontFamily: 'var(--font-body)'
    }
  }, items.map(it => React.createElement('button', {
    key: it,
    onClick: () => onChange && onChange(it),
    style: {
      background: 'none',
      border: 'none',
      borderBottom: it === active ? '2px solid var(--sage-600)' : '2px solid transparent',
      color: it === active ? 'var(--text-primary)' : 'var(--text-tertiary)',
      fontWeight: it === active ? 600 : 400,
      fontSize: 13,
      padding: '8px 4px',
      marginBottom: -1,
      cursor: 'pointer'
    }
  }, it)));
}
Object.assign(__ds_scope, { Tabs });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/Tabs.jsx", error: String((e && e.message) || e) }); }

// components/navigation/TitleBar.jsx
try { (() => {
function TitleBar({
  product,
  doc,
  actions
}) {
  return React.createElement('div', {
    style: {
      height: 44,
      display: 'flex',
      alignItems: 'center',
      padding: '0 12px',
      background: 'var(--surface-card)',
      borderBottom: '1px solid var(--border-subtle)',
      fontFamily: 'var(--font-body)',
      gap: 10
    }
  }, React.createElement('span', {
    style: {
      font: '600 14px var(--font-display)',
      color: 'var(--text-primary)'
    }
  }, product), doc && React.createElement('span', {
    style: {
      color: 'var(--text-tertiary)',
      fontSize: 13
    }
  }, '/'), doc && React.createElement('span', {
    style: {
      color: 'var(--text-secondary)',
      fontSize: 13,
      fontFamily: 'var(--font-mono)'
    }
  }, doc), React.createElement('div', {
    style: {
      flex: 1
    }
  }), actions);
}
Object.assign(__ds_scope, { TitleBar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/TitleBar.jsx", error: String((e && e.message) || e) }); }

// components/surfaces/Card.jsx
try { (() => {
function Card({
  title,
  meta,
  children
}) {
  const [hover, setHover] = React.useState(false);
  return React.createElement('div', {
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      background: 'var(--surface-card)',
      border: `1px solid ${hover ? 'var(--rule-dark)' : 'var(--border-subtle)'}`,
      borderRadius: 'var(--radius-lg)',
      padding: 14,
      fontFamily: 'var(--font-body)',
      boxShadow: hover ? 'var(--shadow-lifted)' : 'var(--shadow-paper)',
      transform: hover ? 'translateY(-4px)' : 'none',
      transition: 'transform var(--duration-normal) var(--ease-primary),box-shadow var(--duration-normal) ease,border-color var(--duration-normal) ease'
    }
  }, (title || meta) && React.createElement('div', {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      marginBottom: 8
    }
  }, title && React.createElement('span', {
    style: {
      font: 'var(--text-title)',
      color: 'var(--text-primary)'
    }
  }, title), meta && React.createElement('span', {
    style: {
      fontSize: 12,
      color: 'var(--text-tertiary)'
    }
  }, meta)), children);
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/surfaces/Card.jsx", error: String((e && e.message) || e) }); }

// components/surfaces/Panel.jsx
try { (() => {
function Panel({
  title,
  actions,
  children
}) {
  return React.createElement('div', {
    style: {
      background: 'var(--surface-card-raised)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-xl)',
      fontFamily: 'var(--font-body)',
      overflow: 'hidden',
      boxShadow: 'var(--shadow-paper)'
    }
  }, (title || actions) && React.createElement('div', {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '10px 14px',
      borderBottom: '1px solid var(--border-subtle)'
    }
  }, React.createElement('span', {
    style: {
      font: 'var(--text-title)',
      color: 'var(--text-primary)'
    }
  }, title), actions), React.createElement('div', {
    style: {
      padding: 14
    }
  }, children));
}
Object.assign(__ds_scope, { Panel });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/surfaces/Panel.jsx", error: String((e && e.message) || e) }); }

// ui_kits/draft/DraftApp.jsx
try { (() => {
const {
  Button,
  IconButton,
  Badge,
  Tag,
  Input,
  Select,
  Sidebar,
  TitleBar,
  Tabs,
  Card,
  Panel,
  Toast
} = window.ArtificeDesignSystem_1fd848;
const DOCS = [{
  id: '1',
  label: 'chapter-three.md',
  meta: '2.1k w'
}, {
  id: '2',
  label: 'letter-to-editor.md',
  meta: '420 w'
}, {
  id: '3',
  label: 'grant-narrative.md',
  meta: '1.8k w'
}];
const SUGGESTIONS = [{
  id: 1,
  type: 'clarity',
  before: 'in order to',
  after: 'to',
  note: 'Cut the wind-up.'
}, {
  id: 2,
  type: 'redundancy',
  before: 'past history',
  after: 'history',
  note: '"History" is already past.'
}, {
  id: 3,
  type: 'passive',
  before: 'was reviewed by the committee',
  after: 'the committee reviewed',
  note: 'Prefer active voice.'
}];
function DraftApp() {
  const [activeDoc, setActiveDoc] = React.useState('1');
  const [tab, setTab] = React.useState('Suggestions');
  const [resolved, setResolved] = React.useState({});
  const [toast, setToast] = React.useState(null);
  const act = (id, verb) => {
    setResolved(r => ({
      ...r,
      [id]: verb
    }));
    setToast(`${verb === 'accept' ? 'Accepted' : 'Rejected'} suggestion ${id}.`);
    setTimeout(() => setToast(null), 2200);
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      background: 'var(--surface-page)',
      fontFamily: 'var(--font-body)'
    }
  }, /*#__PURE__*/React.createElement(TitleBar, {
    product: "Draft",
    doc: DOCS.find(d => d.id === activeDoc)?.label,
    actions: /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        gap: 8,
        alignItems: 'center'
      }
    }, /*#__PURE__*/React.createElement(Select, {
      options: ["local: llama-3.1-8b", "gpt-4o-mini", "claude-3-haiku"]
    }), /*#__PURE__*/React.createElement(Button, {
      size: "sm"
    }, "Save"))
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flex: 1,
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(Sidebar, {
    items: DOCS,
    activeId: activeDoc,
    onSelect: setActiveDoc,
    footer: /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      variant: "ghost"
    }, "+ New document")
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      padding: 24,
      overflowY: 'auto',
      maxWidth: 640
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      font: 'var(--text-display-md)',
      color: 'var(--text-primary)',
      marginBottom: 16
    }
  }, "Chapter Three"), /*#__PURE__*/React.createElement("div", {
    style: {
      font: 'var(--text-body-lg)',
      color: 'var(--text-primary)',
      lineHeight: 1.8
    }
  }, "The committee's decision, ", /*#__PURE__*/React.createElement("span", {
    style: {
      background: 'var(--sage-100)',
      borderBottom: '2px solid var(--sage-500)',
      padding: '0 2px'
    }
  }, "was reviewed by the committee"), " in order to determine whether the grant merited renewal. Given its past history of underfunding, the outcome was hardly a surprise.")), /*#__PURE__*/React.createElement("div", {
    style: {
      width: 340,
      borderLeft: '1px solid var(--border-subtle)',
      background: 'var(--surface-card)',
      padding: 16,
      overflowY: 'auto'
    }
  }, /*#__PURE__*/React.createElement(Tabs, {
    items: ["Suggestions", "Style notes"],
    active: tab,
    onChange: setTab
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 14,
      display: 'flex',
      flexDirection: 'column',
      gap: 10
    }
  }, tab === 'Suggestions' ? SUGGESTIONS.map(s => {
    const r = resolved[s.id];
    return /*#__PURE__*/React.createElement(Card, {
      key: s.id,
      meta: s.type
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        textDecoration: 'line-through',
        color: 'var(--text-tertiary)'
      }
    }, s.before), ' → ', /*#__PURE__*/React.createElement("span", {
      style: {
        color: 'var(--sage-700)',
        fontWeight: 600
      }
    }, s.after)), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        color: 'var(--text-secondary)',
        marginBottom: 10,
        fontStyle: 'italic'
      }
    }, s.note), r ? /*#__PURE__*/React.createElement(Badge, {
      tone: r === 'accept' ? 'success' : 'neutral'
    }, r === 'accept' ? 'Accepted' : 'Rejected') : /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        gap: 6
      }
    }, /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      onClick: () => act(s.id, 'accept')
    }, "Accept"), /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      variant: "ghost",
      onClick: () => act(s.id, 'reject')
    }, "Reject")));
  }) : /*#__PURE__*/React.createElement(Panel, {
    title: "Style notes"
  }, "This document favors active voice and concision \u2014 consistent with prior chapters.")))), toast && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      bottom: 20,
      right: 20
    }
  }, /*#__PURE__*/React.createElement(Toast, {
    tone: "success"
  }, toast)));
}
window.DraftApp = DraftApp;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/draft/DraftApp.jsx", error: String((e && e.message) || e) }); }

// ui_kits/graph/GraphApp.jsx
try { (() => {
const {
  Button,
  IconButton,
  Badge,
  Tag,
  Select,
  Sidebar,
  TitleBar,
  Panel,
  Input
} = window.ArtificeDesignSystem_1fd848;
const DOCS = [{
  id: '1',
  label: 'field-notes-1962.txt',
  meta: '112 nodes'
}, {
  id: '2',
  label: 'correspondence.txt',
  meta: '64 nodes'
}, {
  id: '3',
  label: 'census-extract.csv',
  meta: '340 nodes'
}];
const NODES = [{
  id: 'p1',
  x: 140,
  y: 90,
  label: 'Nyah Tran',
  type: 'person'
}, {
  id: 'p2',
  x: 300,
  y: 60,
  label: 'Owusu Baidoo',
  type: 'person'
}, {
  id: 'l1',
  x: 230,
  y: 180,
  label: 'border crossing',
  type: 'event'
}, {
  id: 'g1',
  x: 400,
  y: 170,
  label: '1962',
  type: 'date'
}, {
  id: 'g2',
  x: 120,
  y: 220,
  label: 'refugee camp',
  type: 'place'
}];
const EDGES = [['p1', 'l1'], ['p2', 'l1'], ['l1', 'g1'], ['l1', 'g2']];
const COLORS = {
  person: 'var(--sage-600)',
  event: 'var(--ink-700)',
  date: 'var(--gold)',
  place: 'var(--sage-400)'
};
function GraphApp() {
  const [active, setActive] = React.useState('1');
  const [selected, setSelected] = React.useState('l1');
  const node = NODES.find(n => n.id === selected);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      background: 'var(--surface-page)',
      fontFamily: 'var(--font-body)'
    }
  }, /*#__PURE__*/React.createElement(TitleBar, {
    product: "Graph",
    doc: DOCS.find(d => d.id === active)?.label,
    actions: /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        gap: 8,
        alignItems: 'center'
      }
    }, /*#__PURE__*/React.createElement(Select, {
      options: ["local: llama-3.1-8b", "gpt-4o-mini"]
    }), /*#__PURE__*/React.createElement(Button, {
      size: "sm"
    }, "Extract entities"))
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flex: 1,
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(Sidebar, {
    items: DOCS,
    activeId: active,
    onSelect: setActive
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      position: 'relative',
      background: 'var(--parchment-200)'
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "100%",
    height: "100%",
    viewBox: "0 0 480 280"
  }, EDGES.map(([a, b], i) => {
    const na = NODES.find(n => n.id === a),
      nb = NODES.find(n => n.id === b);
    return /*#__PURE__*/React.createElement("line", {
      key: i,
      x1: na.x,
      y1: na.y,
      x2: nb.x,
      y2: nb.y,
      stroke: "var(--ink-300)",
      strokeWidth: "1.5"
    });
  }), NODES.map(n => /*#__PURE__*/React.createElement("g", {
    key: n.id,
    onClick: () => setSelected(n.id),
    style: {
      cursor: 'pointer'
    }
  }, /*#__PURE__*/React.createElement("circle", {
    cx: n.x,
    cy: n.y,
    r: selected === n.id ? 12 : 9,
    fill: COLORS[n.type],
    stroke: selected === n.id ? 'var(--ink-900)' : 'none',
    strokeWidth: "2"
  }), /*#__PURE__*/React.createElement("text", {
    x: n.x,
    y: n.y + 24,
    textAnchor: "middle",
    fontSize: "11",
    fontFamily: "Inter,sans-serif",
    fill: "var(--ink-700)"
  }, n.label))))), /*#__PURE__*/React.createElement("div", {
    style: {
      width: 300,
      borderLeft: '1px solid var(--border-subtle)',
      background: 'var(--surface-card)',
      padding: 16
    }
  }, /*#__PURE__*/React.createElement(Panel, {
    title: node?.label,
    actions: /*#__PURE__*/React.createElement(Badge, {
      tone: "neutral"
    }, node?.type)
  }, /*#__PURE__*/React.createElement(Input, {
    label: "Label",
    value: node?.label
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 12,
      fontSize: 12,
      color: 'var(--text-secondary)'
    }
  }, "Connected to ", EDGES.filter(([a, b]) => a === selected || b === selected).length, " nodes"), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 10,
      display: 'flex',
      gap: 6,
      flexWrap: 'wrap'
    }
  }, NODES.filter(n => n.id !== selected).slice(0, 3).map(n => /*#__PURE__*/React.createElement(Tag, {
    key: n.id
  }, n.label)))))));
}
window.GraphApp = GraphApp;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/graph/GraphApp.jsx", error: String((e && e.message) || e) }); }

// ui_kits/ocr/OcrApp.jsx
try { (() => {
const {
  Button,
  IconButton,
  Badge,
  Select,
  Sidebar,
  TitleBar,
  Card,
  Textarea,
  ProgressBar,
  EmptyState
} = window.ArtificeDesignSystem_1fd848;
const PAGES = [{
  id: '12',
  label: 'page-012.tif',
  meta: 'done'
}, {
  id: '13',
  label: 'page-013.tif',
  meta: 'done'
}, {
  id: '14',
  label: 'page-014.tif',
  meta: 'review'
}, {
  id: '15',
  label: 'page-015.tif',
  meta: 'queued'
}, {
  id: '16',
  label: 'page-016.tif',
  meta: 'queued'
}];
function OcrApp() {
  const [active, setActive] = React.useState('14');
  const [running, setRunning] = React.useState(false);
  const [progress, setProgress] = React.useState(38);
  const page = PAGES.find(p => p.id === active);
  React.useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setProgress(p => Math.min(100, p + 7)), 260);
    return () => clearInterval(t);
  }, [running]);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      background: 'var(--surface-page)',
      fontFamily: 'var(--font-body)'
    }
  }, /*#__PURE__*/React.createElement(TitleBar, {
    product: "OCR",
    doc: page?.label,
    actions: /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        gap: 8,
        alignItems: 'center'
      }
    }, /*#__PURE__*/React.createElement(Select, {
      options: ["local: tesseract-best", "local: paddleocr", "gpt-4o-mini (vision)"]
    }), /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      onClick: () => {
        setRunning(true);
        setProgress(0);
      }
    }, "Run batch"))
  }), running && /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '8px 16px',
      borderBottom: '1px solid var(--border-subtle)',
      background: 'var(--surface-card)'
    }
  }, /*#__PURE__*/React.createElement(ProgressBar, {
    value: progress,
    label: `Recognizing text — ${progress}%`
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flex: 1,
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(Sidebar, {
    items: PAGES.map(p => ({
      id: p.id,
      label: p.label,
      meta: p.meta
    })),
    activeId: active,
    onSelect: setActive
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: 'flex',
      gap: 1,
      background: 'var(--border-subtle)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      background: 'var(--ink-100)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: 'var(--ink-500)',
      fontFamily: 'var(--font-mono)',
      fontSize: 12
    }
  }, "scanned page image \u2014 ", page?.label), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      background: 'var(--surface-card)',
      padding: 16,
      display: 'flex',
      flexDirection: 'column',
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: 'var(--text-title)'
    }
  }, "Extracted text"), /*#__PURE__*/React.createElement(Badge, {
    tone: page?.meta === 'done' ? 'success' : page?.meta === 'review' ? 'warning' : 'neutral'
  }, page?.meta)), page?.meta === 'queued' ? /*#__PURE__*/React.createElement(EmptyState, {
    title: "Not yet processed.",
    description: "This page is waiting in the batch queue."
  }) : /*#__PURE__*/React.createElement(Textarea, {
    rows: 12,
    value: "...the survey party reached the ridge on the fourth\nday, having lost two mules to the crossing. what timber\nremained had been marked for the railway..."
  })))));
}
window.OcrApp = OcrApp;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/ocr/OcrApp.jsx", error: String((e && e.message) || e) }); }

// ui_kits/transcribe/TranscribeApp.jsx
try { (() => {
const {
  Button,
  IconButton,
  Badge,
  Tag,
  Select,
  Sidebar,
  TitleBar,
  Textarea,
  Dialog
} = window.ArtificeDesignSystem_1fd848;
const FILES = [{
  id: 'a',
  label: '1994-nyah-tran.wav',
  meta: '42m'
}, {
  id: 'b',
  label: '1994-owusu-baidoo.wav',
  meta: '58m'
}, {
  id: 'c',
  label: '1995-vasquez-mireles.wav',
  meta: '31m'
}];
const SEGMENTS = [{
  t: '00:00:04',
  speaker: 'Interviewer',
  text: 'Can you tell me about the crossing itself?'
}, {
  t: '00:00:11',
  speaker: 'Nyah Tran',
  text: 'The first winter we spent near the border, waiting for papers that never came.'
}, {
  t: '00:00:29',
  speaker: 'Nyah Tran',
  text: 'My brother kept a small radio. That was how we knew the war had not really ended.'
}];
function TranscribeApp() {
  const [active, setActive] = React.useState('a');
  const [showExport, setShowExport] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      background: 'var(--surface-page)',
      fontFamily: 'var(--font-body)',
      position: 'relative'
    }
  }, /*#__PURE__*/React.createElement(TitleBar, {
    product: "Transcribe",
    doc: FILES.find(f => f.id === active)?.label,
    actions: /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        gap: 8,
        alignItems: 'center'
      }
    }, /*#__PURE__*/React.createElement(Select, {
      options: ["local: whisper-large-v3", "local: whisper-medium", "gpt-4o-transcribe"]
    }), /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      onClick: () => setShowExport(true)
    }, "Export"))
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flex: 1,
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(Sidebar, {
    items: FILES,
    activeId: active,
    onSelect: setActive
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      height: 72,
      borderBottom: '1px solid var(--border-subtle)',
      background: 'var(--surface-card)',
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '0 16px'
    }
  }, /*#__PURE__*/React.createElement(IconButton, {
    label: "Play",
    icon: /*#__PURE__*/React.createElement("span", null, "\u25B6")
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      height: 28,
      background: 'repeating-linear-gradient(90deg,var(--sage-400) 0 2px,transparent 2px 5px)',
      borderRadius: 4,
      opacity: 0.6
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-secondary)'
    }
  }, "00:00:29 / 00:42:10")), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflowY: 'auto',
      padding: 20,
      display: 'flex',
      flexDirection: 'column',
      gap: 16
    }
  }, SEGMENTS.map((s, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: 'flex',
      gap: 14
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-tertiary)',
      width: 64,
      flexShrink: 0,
      paddingTop: 4
    }
  }, s.t), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement(Tag, null, s.speaker), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 6,
      font: 'var(--text-body-lg)',
      color: 'var(--text-primary)'
    }
  }, s.text))))))), showExport && /*#__PURE__*/React.createElement(Dialog, {
    title: "Export transcript",
    actions: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Button, {
      variant: "secondary",
      size: "sm",
      onClick: () => setShowExport(false)
    }, "Cancel"), /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      onClick: () => setShowExport(false)
    }, "Export as .docx"))
  }, "Includes speaker labels and timestamps. Names are not redacted."));
}
window.TranscribeApp = TranscribeApp;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/transcribe/TranscribeApp.jsx", error: String((e && e.message) || e) }); }

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.IconButton = __ds_scope.IconButton;

__ds_ns.Tag = __ds_scope.Tag;

__ds_ns.Dialog = __ds_scope.Dialog;

__ds_ns.EmptyState = __ds_scope.EmptyState;

__ds_ns.ProgressBar = __ds_scope.ProgressBar;

__ds_ns.Toast = __ds_scope.Toast;

__ds_ns.Checkbox = __ds_scope.Checkbox;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.Select = __ds_scope.Select;

__ds_ns.Switch = __ds_scope.Switch;

__ds_ns.Textarea = __ds_scope.Textarea;

__ds_ns.Sidebar = __ds_scope.Sidebar;

__ds_ns.Tabs = __ds_scope.Tabs;

__ds_ns.TitleBar = __ds_scope.TitleBar;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.Panel = __ds_scope.Panel;

})();
