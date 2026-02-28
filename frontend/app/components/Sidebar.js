'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Search, FolderOpen, Database, FileText, BookOpen } from 'lucide-react';

const NAV = [
  { label: 'Investigate', href: '/', icon: Search },
  { label: 'Cases', href: '/cases', icon: FolderOpen },
  { label: 'Sources', href: '/sources', icon: Database },
  { label: 'User Guide', href: '/guide', icon: BookOpen },
  { label: 'About', href: '/about', icon: FileText },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-mark">CP</div>
        <div>
          <div className="logo-text">CivicProof</div>
          <div className="logo-sub">v1.0</div>
        </div>
      </div>

      <nav className="nav-section">
        <div className="nav-label">Navigation</div>
        {NAV.map((item) => {
          const Icon = item.icon;
          const isActive = item.href === '/'
            ? pathname === '/'
            : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`nav-item ${isActive ? 'active' : ''}`}
              aria-current={isActive ? 'page' : undefined}
            >
              <Icon size={16} strokeWidth={1.8} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <div style={{ fontSize: 12, color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center' }}>
          <span className="status-dot online" />
          All systems operational
        </div>
      </div>
    </aside>
  );
}
