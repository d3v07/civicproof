import './globals.css';
import Sidebar from './components/Sidebar';
import { ToastProvider } from './components/ToastProvider';

export const metadata = {
  title: 'CivicProof',
  description: 'Public spending research tool — trace federal contracts, map entity networks, surface risk signals.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />
      </head>
      <body>
        <a href="#main-content" className="skip-nav">Skip to main content</a>
        <div className="disclaimer-bar">
          Independent open-source research tool. Not a government website.
        </div>
        <div className="app-shell">
          <Sidebar />
          <div className="main-area">
            <main id="main-content" className="page-content">
              <ToastProvider>
                {children}
              </ToastProvider>
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
