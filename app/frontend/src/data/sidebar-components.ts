import {
  BadgeDollarSign,
  Bot,
  Brain,
  Calculator,
  ChartLine,
  ChartPie,
  Network,
  Play,
  Zap
} from 'lucide-react';
import { Agent, getAgents } from './agents';

// Types are now owned by the platform core so domain packs can declare them
// without depending on this finance-flavoured module. Re-export here so the
// existing `@/data/sidebar-components` import path keeps working.
import type { ComponentGroup } from '@/core/types/component-group';
export type { ComponentGroup, ComponentItem } from '@/core/types/component-group';

/**
 * Get all component groups, including agents fetched from the backend
 */
export const getComponentGroups = async (): Promise<ComponentGroup[]> => {
  const agents = await getAgents();
  
  return [
    {
      name: "Start Nodes",
      icon: Play,
      iconColor: "text-blue-500",
      items: [
        { name: "Portfolio Input", icon: ChartPie },
        { name: "Stock Input", icon: ChartLine },
      ]
    },
    {
      name: "Analysts",
      icon: Bot,
      iconColor: "text-red-500",
      items: agents.map((agent: Agent) => ({
        name: agent.display_name,
        icon: Bot
      }))
    },
    {
      name: "Swarms",
      icon: Network,
      iconColor: "text-yellow-500",
      items: [
        { name: "Data Wizards", icon: Calculator },
        { name: "Market Mavericks", icon: Zap },
        { name: "Value Investors", icon: BadgeDollarSign },
      ]
    },
    {
      name: "End Nodes",
      icon: Brain,
      iconColor: "text-green-500",
      items: [
        { name: "Portfolio Manager", icon: Brain },
        // { name: "JSON Output", icon: FileJson },
        // { name: "Investment Report", icon: FileText },
      ]
    },
  ];
};