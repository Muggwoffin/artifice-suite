import type { ReactNode } from 'react';
/** @startingPoint section="Core" subtitle="Compact icon-only control" viewport="700x100" */
export interface IconButtonProps {
  icon: ReactNode;
  label: string;
  active?: boolean;
  onClick?: () => void;
}
