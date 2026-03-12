import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import HomePage from '../app/page';
import { mockCases } from '../app/lib/mock-data';

jest.mock('next/navigation', () => ({
    usePathname: () => '/',
    useParams: () => ({}),
    useRouter: () => ({ push: jest.fn() }),
}));

jest.mock('next/link', () => {
    return ({ children, href, ...props }) => <a href={href} {...props}>{children}</a>;
});

jest.mock('../app/lib/api', () => ({
    listCases: jest.fn(() => Promise.reject(new Error('no backend'))),
}));

describe('Home Page', () => {
    it('renders the search input by placeholder', () => {
        render(<HomePage />);
        expect(screen.getByPlaceholderText(/company name/i)).toBeInTheDocument();
    });

    it('renders the hero heading', () => {
        render(<HomePage />);
        expect(screen.getByText(/Trace federal spending/)).toBeInTheDocument();
    });

    it('renders how-it-works steps', () => {
        render(<HomePage />);
        expect(screen.getByText('Search')).toBeInTheDocument();
        expect(screen.getByText('Analyze')).toBeInTheDocument();
        expect(screen.getByText('Audit')).toBeInTheDocument();
    });

    it('renders suggestion pills', () => {
        render(<HomePage />);
        expect(screen.getByText('Acme Defense Solutions')).toBeInTheDocument();
        expect(screen.getByText('Meridian Logistics')).toBeInTheDocument();
    });

    it('falls back to mock cases when API is down', async () => {
        render(<HomePage />);
        await waitFor(() => {
            expect(screen.getByText(mockCases[0].title)).toBeInTheDocument();
        });
    });

    it('renders recent cases section with link to all cases', async () => {
        render(<HomePage />);
        await waitFor(() => {
            expect(screen.getByText('All cases')).toBeInTheDocument();
        });
    });

    it('does NOT render any KPI cards', () => {
        const { container } = render(<HomePage />);
        expect(container.querySelector('.kpi-card')).toBeNull();
        expect(container.querySelector('.kpi-grid')).toBeNull();
    });

    it('navigates to investigate page on search submit', () => {
        const mockPush = jest.fn();
        jest.spyOn(require('next/navigation'), 'useRouter').mockReturnValue({ push: mockPush });

        render(<HomePage />);
        const input = screen.getByPlaceholderText(/company name/i);
        fireEvent.change(input, { target: { value: 'Palantir' } });
        fireEvent.submit(input.closest('form'));

        expect(mockPush).toHaveBeenCalledWith('/investigate?q=Palantir');
    });
});
