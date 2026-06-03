import { Routes, Route } from 'react-router-dom';
import { Layout } from './components/layout';
import { BugFixDashboard } from './domains/bug-fix/bug-fix-dashboard';
import { Toaster } from './components/ui/sonner';

export default function App() {
  return (
    <>
      <Routes>
        <Route path="/bug-fix" element={<BugFixDashboard />} />
        <Route path="*" element={<Layout />} />
      </Routes>
      <Toaster />
    </>
  );
}
