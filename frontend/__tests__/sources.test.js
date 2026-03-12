import '@testing-library/jest-dom';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import SourcesPage from '../app/sources/page';
import { mockSources } from '../app/lib/mock-data';
import { ToastProvider } from '../app/components/ToastProvider';

jest.mock('next/navigation', () => ({
    usePathname: () => '/sources',
    useParams: () => ({}),
}));

jest.mock('../app/lib/api', () => ({
    getMetrics: jest.fn(() => Promise.reject(new Error('no backend'))),
    triggerIngest: jest.fn(() => Promise.reject(new Error('no backend'))),
}));

function renderWithProviders(ui) {
    return render(<ToastProvider>{ui}</ToastProvider>);
}

describe('Sources Page', () => {
    it('renders the page title', () => {
        renderWithProviders(<SourcesPage />);
        expect(screen.getByRole('heading', { name: /Data Sources/ })).toBeInTheDocument();
    });

    it('renders subtitle with connector count', () => {
        renderWithProviders(<SourcesPage />);
        expect(screen.getByText(/federal data connectors/)).toBeInTheDocument();
    });

    it('renders all source cards', () => {
        renderWithProviders(<SourcesPage />);
        mockSources.forEach((s) => {
            expect(screen.getAllByText(s.name).length).toBeGreaterThan(0);
        });
    });

    it('renders rate limits for each source', () => {
        renderWithProviders(<SourcesPage />);
        mockSources.forEach((s) => {
            const rateElements = screen.getAllByText(s.rate_limit);
            expect(rateElements.length).toBeGreaterThan(0);
        });
    });

    it('renders trigger sync buttons', () => {
        renderWithProviders(<SourcesPage />);
        const buttons = screen.getAllByText('Trigger Sync');
        expect(buttons.length).toBe(mockSources.length);
    });

    it('shows syncing state on button click', async () => {
        renderWithProviders(<SourcesPage />);
        const buttons = screen.getAllByText('Trigger Sync');

        await act(async () => {
            fireEvent.click(buttons[0]);
        });

        expect(screen.getByText('Syncing...')).toBeInTheDocument();
    });

    it('renders the rate limit compliance table', () => {
        renderWithProviders(<SourcesPage />);
        expect(screen.getByText('Rate Limit Compliance')).toBeInTheDocument();
    });

    it('renders auth badges (API Key vs Public)', () => {
        renderWithProviders(<SourcesPage />);
        const apiKeyBadges = screen.getAllByText('API Key');
        const publicBadges = screen.getAllByText('Public');
        expect(apiKeyBadges.length).toBeGreaterThan(0);
        expect(publicBadges.length).toBeGreaterThan(0);
    });

    it('renders schedule for each source', () => {
        renderWithProviders(<SourcesPage />);
        mockSources.forEach((s) => {
            expect(screen.getAllByText(s.schedule).length).toBeGreaterThan(0);
        });
    });
});
