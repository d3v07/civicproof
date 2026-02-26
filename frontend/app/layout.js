import './globals.css';
import Sidebar from './components/Sidebar';
import { ToastProvider } from './components/ToastProvider';

export const metadata = {
  title: 'CivicProof — Public Spending Research Tool',
  description: 'Open-source research tool for analyzing public federal spending data. Not a government website.',
  keywords: 'public data analysis, federal spending research, open source, procurement analytics',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <a href="#main-content" className="skip-nav">Skip to main content</a>
        {/* Non-government disclaimer banner */}
        <div className="disclaimer-banner" role="banner">
          <span>This is NOT a government website. CivicProof is an independent open-source research tool that analyzes publicly available federal data.</span>
        </div>

        <div className="app-layout">
          <Sidebar />
          <main className="main-content" role="main" id="main-content">
            <ToastProvider>
              {children}
            </ToastProvider>
          </main>
        </div>

        {/* Footer */}
        <div className="app-footer" role="contentinfo">
          <span>CivicProof v1.0.0 — Independent open-source research tool. Not affiliated with any government agency.</span>
        </div>
      </body>
    </html>
  );
}
