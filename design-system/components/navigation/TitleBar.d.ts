import type { ReactNode } from 'react';
/** @startingPoint section="Navigation" subtitle="App window title bar" viewport="700x100" */
export interface TitleBarProps {
  product: string;
  doc?: string;
  actions?: ReactNode;
}
