import type { ReactNode } from 'react';
/** @startingPoint section="Navigation" subtitle="Persistent file/source list" viewport="700x320" */
export interface SidebarItem { id: string; label: string; meta?: string; }
export interface SidebarProps {
  items?: SidebarItem[];
  activeId?: string;
  onSelect?: (id: string) => void;
  footer?: ReactNode;
}
