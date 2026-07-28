import type { ReactNode } from 'react';
/** @startingPoint section="Feedback" subtitle="Transient status message" viewport="700x100" */
export interface ToastProps {
  tone?: 'neutral' | 'success' | 'danger';
  children?: ReactNode;
  onClose?: () => void;
}
