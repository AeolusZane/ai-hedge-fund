import { Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { BugFixDashboard } from './domains/bug-fix/bug-fix-dashboard';
import { EvolutionDashboard } from './domains/bug-fix/evolution-dashboard';
import { Toaster } from './components/ui/sonner';

export default function App() {
  return (
    <>
      <Routes>
        <Route path="/bug-fix" element={<BugFixDashboard />} />
        <Route path="/evolution" element={<EvolutionDashboard />} />
        <Route path="/" element={<Navigate to="/evolution" replace />} />
        <Route path="*" element={<Layout />} />
      </Routes>
      <Toaster />
    </>
  );
}
