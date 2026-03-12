import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import InvestigatePage from '../app/investigate/page';
import { mockEntities } from '../app/lib/mock-data';
import { ToastProvider } from '../app/components/ToastProvider';

jest.mock('next/navigation', () => ({
    usePathname: () => '/investigate',
    useParams: () => ({}),
    useRouter: () => ({ push: jest.fn() }),
    useSearchParams: () => new URLSearchParams(),
}));

jest.mock('next/link', () => {
    return ({ children, href, ...props }) => <a href={href} {...props}>{children}</a>;
});

jest.mock('../app/lib/api', () => ({
    searchEntities: jest.fn(() => Promise.reject(new Error('no backend'))),
    createCase: jest.fn(() => Promise.reject(new Error('no backend'))),
}));

jest.mock('../app/components/LiveInvestigation', () => {
    return function MockLiveInvestigation({ title }) {
        return <div data-testid="live-investigation">Investigating: {title}</div>;
    };
});

function renderWithProviders(ui) {
    return render(<ToastProvider>{ui}</ToastProvider>);
}

describe('Investigate Page', () => {
    it('renders the page title', async () => {
        renderWithProviders(<InvestigatePage />);
        await waitFor(() => {
            expect(screen.getByRole('heading', { name: /Investigate/ })).toBeInTheDocument();
        });
    });

    it('renders the search input', async () => {
        renderWithProviders(<InvestigatePage />);
        await waitFor(() => {
            expect(screen.getByPlaceholderText(/vendor name/i)).toBeInTheDocument();
        });
    });

    it('renders the new research button', async () => {
        renderWithProviders(<InvestigatePage />);
        await waitFor(() => {
            expect(screen.getByText('New Research')).toBeInTheDocument();
        });
    });

    it('opens the modal when button is clicked', async () => {
        renderWithProviders(<InvestigatePage />);
        await waitFor(() => {
            expect(screen.getByText('New Research')).toBeInTheDocument();
        });

        fireEvent.click(screen.getByText('New Research'));

        expect(screen.getByText('Start Research')).toBeInTheDocument();
        expect(screen.getByText('Cancel')).toBeInTheDocument();
    });

    it('closes the modal on cancel', async () => {
        renderWithProviders(<InvestigatePage />);
        await waitFor(() => {
            expect(screen.getByText('New Research')).toBeInTheDocument();
        });

        fireEvent.click(screen.getByText('New Research'));
        expect(screen.getByText('Start Research')).toBeInTheDocument();

        fireEvent.click(screen.getByText('Cancel'));
        expect(screen.queryByText('Start Research')).not.toBeInTheDocument();
    });

    it('shows entity results on search with mock fallback', async () => {
        renderWithProviders(<InvestigatePage />);
        await waitFor(() => {
            expect(screen.getByPlaceholderText(/vendor name/i)).toBeInTheDocument();
        });

        const input = screen.getByPlaceholderText(/vendor name/i);
        fireEvent.change(input, { target: { value: 'Acme' } });
        fireEvent.submit(input.closest('form'));

        await waitFor(() => {
            expect(screen.getByText('Acme Defense Solutions')).toBeInTheDocument();
        });
    });

    it('renders subtitle text', async () => {
        renderWithProviders(<InvestigatePage />);
        await waitFor(() => {
            expect(screen.getByText(/Search entity records/)).toBeInTheDocument();
        });
    });

    it('modal has seed type selector', async () => {
        renderWithProviders(<InvestigatePage />);
        await waitFor(() => {
            expect(screen.getByText('New Research')).toBeInTheDocument();
        });

        fireEvent.click(screen.getByText('New Research'));

        expect(screen.getByText('Identifier Type')).toBeInTheDocument();
        expect(screen.getByText('Seed Value')).toBeInTheDocument();
        expect(screen.getByText('Reference Title')).toBeInTheDocument();
    });

    it('shows no results message for empty search', async () => {
        renderWithProviders(<InvestigatePage />);
        await waitFor(() => {
            expect(screen.getByPlaceholderText(/vendor name/i)).toBeInTheDocument();
        });

        const input = screen.getByPlaceholderText(/vendor name/i);
        fireEvent.change(input, { target: { value: 'zzz_no_match_zzz' } });
        fireEvent.submit(input.closest('form'));

        await waitFor(() => {
            expect(screen.getByText(/No results for/)).toBeInTheDocument();
        });
    });
});
