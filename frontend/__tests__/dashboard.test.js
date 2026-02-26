import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import HomePage from '../app/page';

jest.mock('next/navigation', () => ({
    usePathname: () => '/',
    useParams: () => ({}),
    useRouter: () => ({ push: jest.fn() }),
}));

jest.mock('next/link', () => {
    return ({ children, href, ...props }) => <a href={href} {...props}>{children}</a>;
});

describe('Home Page', () => {
    it('renders the search input', () => {
        render(<HomePage />);
        expect(screen.getByRole('textbox', { name: /search/i })).toBeInTheDocument();
    });

    it('renders the page heading', () => {
        render(<HomePage />);
        expect(screen.getByRole('heading', { name: /Investigate federal spending/ })).toBeInTheDocument();
    });

    it('renders case titles in the feed', () => {
        render(<HomePage />);
        expect(screen.getByText('Acme Defense Solutions — Sole-Source Pattern')).toBeInTheDocument();
    });

    it('groups cases by status', () => {
        render(<HomePage />);
        expect(screen.getByText('In Progress')).toBeInTheDocument();
        expect(screen.getByText('Completed')).toBeInTheDocument();
    });

    it('does NOT render any KPI cards', () => {
        const { container } = render(<HomePage />);
        expect(container.querySelector('.kpi-card')).toBeNull();
        expect(container.querySelector('.kpi-grid')).toBeNull();
    });
});
