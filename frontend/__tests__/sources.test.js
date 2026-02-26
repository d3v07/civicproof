import '@testing-library/jest-dom';
import { render, screen, fireEvent, act } from '@testing-library/react';
import SourcesPage from '../app/sources/page';
import { mockSources } from '../app/lib/mock-data';

jest.mock('next/navigation', () => ({
    usePathname: () => '/sources',
    useParams: () => ({}),
}));

describe('Sources Page', () => {
    it('renders the page title', () => {
        render(<SourcesPage />);
        expect(screen.getByRole('heading', { name: /Data Sources/ })).toBeInTheDocument();
    });

    it('renders breadcrumb', () => {
        render(<SourcesPage />);
        // Dashboard link is in sidebar AND breadcrumb
        expect(screen.getAllByText('Dashboard').length).toBeGreaterThan(0);
    });

    it('renders the connector overview summary box', () => {
        render(<SourcesPage />);
        expect(screen.getByText('Connector Overview')).toBeInTheDocument();
    });

    it('renders all source cards', () => {
        render(<SourcesPage />);
        mockSources.forEach((s) => {
            // Each source name appears in both card and compliance table
            expect(screen.getAllByText(s.name).length).toBeGreaterThan(0);
        });
    });

    it('renders rate limits for each source', () => {
        render(<SourcesPage />);
        mockSources.forEach((s) => {
            const rateElements = screen.getAllByText(s.rate_limit);
            expect(rateElements.length).toBeGreaterThan(0);
        });
    });

    it('renders trigger buttons for each source', () => {
        render(<SourcesPage />);
        const buttons = screen.getAllByText('Trigger Ingestion Run');
        expect(buttons.length).toBe(mockSources.length);
    });

    it('changes button state on click', async () => {
        jest.useFakeTimers();
        render(<SourcesPage />);
        const buttons = screen.getAllByText('Trigger Ingestion Run');

        await act(async () => {
            fireEvent.click(buttons[0]);
        });

        expect(screen.getByText('Initiating...')).toBeInTheDocument();

        await act(async () => {
            jest.advanceTimersByTime(1100);
        });

        // After timeout, button should no longer show "Initiating..."
        expect(screen.queryByText('Initiating...')).not.toBeInTheDocument();
        jest.useRealTimers();
    });

    it('renders the rate limit compliance table', () => {
        render(<SourcesPage />);
        expect(screen.getByText('Rate Limit Compliance Matrix')).toBeInTheDocument();
    });

    it('renders auth badges (API Key vs Public)', () => {
        render(<SourcesPage />);
        const apiKeyBadges = screen.getAllByText('API Key');
        const publicBadges = screen.getAllByText('Public');
        expect(apiKeyBadges.length).toBeGreaterThan(0);
        expect(publicBadges.length).toBeGreaterThan(0);
    });
});
