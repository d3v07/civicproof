import '@testing-library/jest-dom';
import { render, screen, fireEvent } from '@testing-library/react';
import CasesPage from '../app/cases/page';
import { mockCases } from '../app/lib/mock-data';

jest.mock('next/navigation', () => ({
    usePathname: () => '/cases',
    useParams: () => ({}),
}));

describe('Cases Page', () => {
    it('renders the page title', () => {
        render(<CasesPage />);
        expect(screen.getByText('Case Registry')).toBeInTheDocument();
    });

    it('renders breadcrumb navigation', () => {
        render(<CasesPage />);
        expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });

    it('renders the correct number of status tabs', () => {
        render(<CasesPage />);
        expect(screen.getByRole('tab', { name: /All Cases/i })).toBeInTheDocument();
        expect(screen.getByRole('tab', { name: /Complete/i })).toBeInTheDocument();
        expect(screen.getByRole('tab', { name: /Processing/i })).toBeInTheDocument();
        expect(screen.getByRole('tab', { name: /Blocked/i })).toBeInTheDocument();
    });

    it('filters cases when a tab is clicked', () => {
        render(<CasesPage />);
        const completeTab = screen.getByRole('tab', { name: /Complete/i });
        fireEvent.click(completeTab);
        expect(completeTab).toHaveAttribute('aria-selected', 'true');
    });

    it('renders case titles in the table', () => {
        render(<CasesPage />);
        mockCases.forEach((c) => {
            expect(screen.getByText(c.title)).toBeInTheDocument();
        });
    });

    it('renders proper table headers with scope', () => {
        const { container } = render(<CasesPage />);
        const ths = container.querySelectorAll('th[scope="col"]');
        expect(ths.length).toBe(5);
    });

    it('shows status badges', () => {
        render(<CasesPage />);
        const badges = screen.getAllByText(/complete|processing|blocked/i);
        expect(badges.length).toBeGreaterThan(0);
    });

    it('includes the result count text', () => {
        render(<CasesPage />);
        expect(screen.getByText(/Showing .* of .* cases/)).toBeInTheDocument();
    });
});
