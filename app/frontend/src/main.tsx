import React from 'react';
import ReactDOM from 'react-dom/client';

import App from './App';
import { NodeProvider } from './contexts/node-context';
import { ThemeProvider } from './providers/theme-provider';

// Coding-branch shell: only the bug_fix domain is registered, so the
// runtime acts as a single-domain app. The DomainProvider is still
// present to keep contexts wired; the switcher UI has been removed.
import './domains/bug-fix';
import './domains/agent-platform';

import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <NodeProvider>
        <App />
      </NodeProvider>
    </ThemeProvider>
  </React.StrictMode>
);
