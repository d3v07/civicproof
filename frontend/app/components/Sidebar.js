'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, useEffect, useCallback } from 'react';

const NAV_ITEMS = [
    {
        label: 'Dashboard', href: '/', shortLabel: 'Home',
        icon: (
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="1" y="1" width="7" height="7" rx="1" />
                <rect x="10" y="1" width="7" height="4" rx="1" />
                <rect x="1" y="10" width="7" height="4" rx="1" />
                <rect x="10" y="7" width="7" height="7" rx="1" />
            </svg>
        ),
    },
    {
        label: 'Investigate', href: '/investigate', shortLabel: 'Investigate',
        icon: (
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="8" cy="8" r="5.5" />
                <line x1="12" y1="12" x2="16" y2="16" />
            </svg>
        ),
    },
    {
        label: 'Cases', href: '/cases', shortLabel: 'Cases',
        icon: (
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="2" y="2" width="14" height="14" rx="2" />
                <line x1="5" y1="6" x2="13" y2="6" />
                <line x1="5" y1="9" x2="13" y2="9" />
                <line x1="5" y1="12" x2="10" y2="12" />
            </svg>
        ),
    },
    {
        label: 'Data Sources', href: '/sources', shortLabel: 'Sources',
        icon: (
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
                <ellipse cx="9" cy="4" rx="7" ry="2.5" />
                <path d="M2 4v5c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5V4" />
                <path d="M2 9v5c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5V9" />
            </svg>
        ),
    },
];

function AppLogo() {
    return (
        <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 16, fontWeight: 700, color: '#fff', fontFamily: 'var(--font-mono)',
        }}>
            CP
        </div>
    );
}

export default function Sidebar() {
    const pathname = usePathname();
    const [mobileOpen, setMobileOpen] = useState(false);

    // Close on route change
    useEffect(() => {
        setMobileOpen(false);
    }, [pathname]);

    // Close on Escape
    const handleKeyDown = useCallback((e) => {
        if (e.key === 'Escape') setMobileOpen(false);
    }, []);

    useEffect(() => {
        if (mobileOpen) {
            document.addEventListener('keydown', handleKeyDown);
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = '';
        }
        return () => {
            document.removeEventListener('keydown', handleKeyDown);
            document.body.style.overflow = '';
        };
    }, [mobileOpen, handleKeyDown]);

    return (
        <>
            {/* Mobile Header Bar */}
            <div className="mobile-header">
                <button className="hamburger-btn" onClick={() => setMobileOpen(true)} aria-label="Open navigation menu">
                    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="currentColor" strokeWidth="1.8">
                        <line x1="3" y1="6" x2="19" y2="6" />
                        <line x1="3" y1="11" x2="19" y2="11" />
                        <line x1="3" y1="16" x2="19" y2="16" />
                    </svg>
                </button>
                <span className="mobile-header-title">CivicProof</span>
            </div>

            {/* Backdrop */}
            {mobileOpen && (
                <div className="sidebar-backdrop" onClick={() => setMobileOpen(false)} aria-hidden="true" />
            )}

            {/* Sidebar */}
            <aside className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`} role="navigation" aria-label="Main navigation">
                <div className="sidebar-brand">
                    <AppLogo />
                    <div className="sidebar-brand-text">
                        <span className="sidebar-brand-name">CivicProof</span>
                        <span className="sidebar-brand-subtitle">Public Data Research Tool</span>
                    </div>
                    {/* Close button (mobile only) */}
                    <button className="sidebar-close-btn" onClick={() => setMobileOpen(false)} aria-label="Close navigation">
                        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.8">
                            <line x1="4" y1="4" x2="14" y2="14" /><line x1="14" y1="4" x2="4" y2="14" />
                        </svg>
                    </button>
                </div>

                <nav className="sidebar-nav">
                    <div className="nav-section-label">Main Menu</div>
                    {NAV_ITEMS.map((item) => {
                        const isActive =
                            item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={`nav-link ${isActive ? 'active' : ''}`}
                                aria-current={isActive ? 'page' : undefined}
                            >
                                <span className="nav-icon">{item.icon}</span>
                                {item.label}
                            </Link>
                        );
                    })}

                    <div className="nav-section-label" style={{ marginTop: 8 }}>Resources</div>
                    <span className="nav-link nav-link-disabled">
                        <span className="nav-icon">
                            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
                                <rect x="2" y="2" width="14" height="14" rx="2" />
                                <path d="M6 6h6M6 9h6M6 12h3" />
                            </svg>
                        </span>
                        API Documentation
                    </span>
                    <span className="nav-link nav-link-disabled">
                        <span className="nav-icon">
                            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
                                <circle cx="9" cy="9" r="7" />
                                <path d="M9 5v4l2.5 2.5" />
                            </svg>
                        </span>
                        Operations Runbook
                    </span>
                </nav>

                <div className="sidebar-footer">
                    <div className="status-indicator">
                        <span className="status-dot online"></span>
                        <span>Systems Operational</span>
                    </div>
                </div>
            </aside>

            {/* Mobile Bottom Tab Bar */}
            <nav className="mobile-tab-bar" aria-label="Mobile navigation">
                {NAV_ITEMS.map((item) => {
                    const isActive = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={`mobile-tab ${isActive ? 'active' : ''}`}
                            aria-current={isActive ? 'page' : undefined}
                        >
                            <span className="mobile-tab-icon">{item.icon}</span>
                            <span className="mobile-tab-label">{item.shortLabel}</span>
                        </Link>
                    );
                })}
            </nav>
        </>
    );
}
