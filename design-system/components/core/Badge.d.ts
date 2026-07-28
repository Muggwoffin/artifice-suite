import type { ReactNode } from 'react';
/** @startingPoint section="Core" subtitle="Status pill" viewport="700x100" */
export interface BadgeProps {
  tone?: 'neutral' | 'success' | 'warning' | 'danger';
  children?: ReactNode;
}
