import React from 'react';
import ReactDOM from 'react-dom/client';

import App from './App';
import { NodeProvider } from './contexts/node-context';
import { ThemeProvider } from './providers/theme-provider';

// Importing a domain pack triggers its registerDomain(...) side effect.
// Add new domains here to make them selectable in the switcher.
import './domains/finance';

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
