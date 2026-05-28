import type { LucideIcon } from 'lucide-react';

/**
 * One entry inside a component group — typically rendered as a draggable
 * tile in the right-side palette. The `name` is what the canvas uses to
 * resolve the React Flow node type when the tile is dropped.
 */
export interface ComponentItem {
  name: string;
  icon: LucideIcon;
}

/**
 * A collapsible group of draggable components shown in the right sidebar.
 * Domain packs return their own list of groups from
 * `DomainPack.getComponentGroups`.
 */
export interface ComponentGroup {
  name: string;
  icon: LucideIcon;
  iconColor: string;
  items: ComponentItem[];
}
