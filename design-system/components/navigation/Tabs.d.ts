/** @startingPoint section="Navigation" subtitle="Underline tab bar" viewport="700x80" */
export interface TabsProps {
  items?: string[];
  active?: string;
  onChange?: (item: string) => void;
}
