import type { ReactNode } from 'react';
/**
 * @startingPoint section="Core" subtitle="Primary action control" viewport="700x160"
 */
export interface ButtonProps {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md';
  icon?: ReactNode;
  disabled?: boolean;
  children?: ReactNode;
  onClick?: () => void;
}
