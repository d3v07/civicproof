import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CasesPage from '../app/cases/page';
import { mockCases } from '../app/lib/mock-data';

const mockPush = jest.fn();

jest.mock('next/navigation', () => ({
    usePathname: () => '/cases',
    useParams: () => ({}),
    useRouter: () => ({ push: mockPush }),
}));

jest.mock('next/link', () => {
    return ({ children, href, ...props }) => <a href={href} {...props}>{children}</a>;
});

jest.mock('../app/lib/api', () => ({
    listCases: jest.fn(() => Promise.resolve({ items: mockCases })),
}));

describe('Cases Page', () => {
    beforeEach(() => {
        mockPush.mockClear();
    });

    it('renders the page title', async () => {
        render(<CasesPage />);
        expect(screen.getByRole('heading', { name: /Cases/ })).toBeInTheDocument();
    });

    it('renders status filter tabs', async () => {
        render(<CasesPage />);
        await waitFor(() => {
            expect(screen.getByText(/^All/)).toBeInTheDocument();
        });
        expect(screen.getByText(/Complete/)).toBeInTheDocument();
        expect(screen.getByText(/Processing/)).toBeInTheDocument();
        expect(screen.getByText(/Blocked/)).toBeInTheDocument();
    });

    it('renders case titles after loading', async () => {
        render(<CasesPage />);
        await waitFor(() => {
            mockCases.forEach((c) => {
                expect(screen.getByText(c.title)).toBeInTheDocument();
            });
        });
    });

    it('renders table headers', async () => {
        render(<CasesPage />);
        await waitFor(() => {
            expect(screen.getByText('Case')).toBeInTheDocument();
        });
        expect(screen.getByText('Status')).toBeInTheDocument();
        expect(screen.getByText('Seed')).toBeInTheDocument();
    });

    it('shows status badges', async () => {
        render(<CasesPage />);
        await waitFor(() => {
            const badges = screen.getAllByText(/complete|processing|blocked/i);
            expect(badges.length).toBeGreaterThan(0);
        });
    });

    it('filters cases when a tab is clicked', async () => {
        render(<CasesPage />);
        await waitFor(() => {
            expect(screen.getByText(mockCases[0].title)).toBeInTheDocument();
        });

        const blockedTab = screen.getByText(/Blocked/);
        fireEvent.click(blockedTab);

        const blockedCases = mockCases.filter(c => c.status === 'blocked');
        blockedCases.forEach((c) => {
            expect(screen.getByText(c.title)).toBeInTheDocument();
        });
    });

    it('renders New Research link to investigate page', async () => {
        render(<CasesPage />);
        const link = screen.getByText('New Research');
        expect(link.closest('a')).toHaveAttribute('href', '/investigate');
    });

    it('shows error state when API fails', async () => {
        const apiModule = require('../app/lib/api');
        apiModule.listCases.mockImplementationOnce(() => Promise.reject(new Error('Network error')));

        render(<CasesPage />);
        await waitFor(() => {
            expect(screen.getByText(/Unable to load cases/)).toBeInTheDocument();
        });
    });
});
