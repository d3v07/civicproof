import '@testing-library/jest-dom';
import { render, screen, fireEvent } from '@testing-library/react';
import InvestigatePage from '../app/investigate/page';
import { mockEntities } from '../app/lib/mock-data';

jest.mock('next/navigation', () => ({
    usePathname: () => '/investigate',
    useParams: () => ({}),
}));

describe('Investigate Page', () => {
    it('renders the page title', () => {
        render(<InvestigatePage />);
        expect(screen.getByRole('heading', { name: /Investigate/ })).toBeInTheDocument();
    });

    it('renders the search input with label', () => {
        render(<InvestigatePage />);
        expect(screen.getByRole('textbox', { name: /search/i })).toBeInTheDocument();
    });

    it('renders entity tab with count', () => {
        render(<InvestigatePage />);
        expect(screen.getByRole('tab', { name: /Entities/i })).toBeInTheDocument();
    });

    it('renders all entities by default', () => {
        render(<InvestigatePage />);
        mockEntities.items.forEach((e) => {
            expect(screen.getByText(e.canonical_name)).toBeInTheDocument();
        });
    });

    it('filters entities on search', () => {
        render(<InvestigatePage />);
        const input = screen.getByRole('textbox', { name: /search/i });
        fireEvent.change(input, { target: { value: 'Acme' } });
        fireEvent.submit(input.closest('form'));
        expect(screen.getByText(/Showing \d+ of/)).toBeInTheDocument();
    });

    it('renders the new investigation button', () => {
        render(<InvestigatePage />);
        expect(screen.getByText('+ New Investigation')).toBeInTheDocument();
    });

    it('opens the modal when button is clicked', () => {
        render(<InvestigatePage />);
        fireEvent.click(screen.getByText('+ New Investigation'));
        expect(screen.getByRole('dialog')).toBeInTheDocument();
        expect(screen.getByText('Initiate New Investigation')).toBeInTheDocument();
    });

    it('closes the modal on cancel', () => {
        render(<InvestigatePage />);
        fireEvent.click(screen.getByText('+ New Investigation'));
        fireEvent.click(screen.getByText('Cancel'));
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('renders recent investigations summary box', () => {
        render(<InvestigatePage />);
        expect(screen.getByText('Recent Investigations')).toBeInTheDocument();
    });
});
