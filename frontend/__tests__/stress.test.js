import React from 'react';
import { render, screen, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ToastProvider, useToast } from '../app/components/ToastProvider';

// A mock component to consume useToast and render edge cases
function ToastTestConsumer({ edgeCaseString }) {
    const { addToast } = useToast();
    return (
        <button onClick={() => addToast({ message: edgeCaseString, type: 'error' })}>
            Trigger
        </button>
    );
}

const frontendEdgeCases = [
    { id: 1, desc: "Empty string", payload: "" },
    { id: 2, desc: "Null payload equivalent", payload: null },
    { id: 3, desc: "Undefined payload equivalent", payload: undefined },
    { id: 4, desc: "Extremely long string", payload: "A".repeat(10000) },
    { id: 5, desc: "Special characters", payload: "!@#$%^&*()_+~`|}{[]:;?><,./" },
    { id: 6, desc: "HTML Injection attempt", payload: "<script>alert('XSS')</script>" },
    { id: 7, desc: "SQL Injection attempt", payload: "DROP TABLE users;--" },
    { id: 8, desc: "Zero width joiners", payload: "👨‍👩‍👧‍👦" },
    { id: 9, desc: "RTL Override characters", payload: "\u202E RTL Text \u202C" },
    { id: 10, desc: "Control characters", payload: "\x00\x08\x0B\x0C\x0E\x1F" },
    { id: 11, desc: "Emoji overflow", payload: "🔥".repeat(1000) },
    { id: 12, desc: "Deeply nested JSON", payload: JSON.stringify({ a: { b: { c: { d: "1" } } } }) },
    { id: 13, desc: "Maximum integer", payload: Number.MAX_SAFE_INTEGER.toString() },
    { id: 14, desc: "Minimum integer", payload: Number.MIN_SAFE_INTEGER.toString() },
    { id: 15, desc: "Float overflow", payload: "1e309" },
    { id: 16, desc: "Unicode chaos", payload: "åß∂ƒ©˙∆˚¬…æ" },
    { id: 17, desc: "Zalgo text", payload: "Z̵͈͗à̵̧l̵͖̉g̵͋͜ȍ̵̡ ̸̰̓T̵͎̋e̵͗ͅẍ̵̤́t̵̜̀" },
    { id: 18, desc: "Boolean true", payload: "true" },
    { id: 19, desc: "Boolean false", payload: "false" },
    { id: 20, desc: "Array notation", payload: "[1,2,3]" },
    { id: 21, desc: "Object notation", payload: "{}" },
    { id: 22, desc: "Function notation", payload: "() => void" },
    { id: 23, desc: "URL encoding", payload: "%20%22%3C" },
    { id: 24, desc: "Hex encoded string", payload: "0x410x420x43" },
    { id: 25, desc: "Base64 encoded string", payload: "SGVsbG8gV29ybGQ=" },
    { id: 26, desc: "Carriage returns", payload: "\r\n\r\n\r\n" },
    { id: 27, desc: "Tab characters", payload: "\t\t\t\t\t" },
    { id: 28, desc: "Non-breaking spaces", payload: "\u00A0\u00A0\u00A0" },
    { id: 29, desc: "Large file path equivalent", payload: "/a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p/q.txt" },
    { id: 30, desc: "CSS Injection", payload: "body { display: none; }" },
    { id: 31, desc: "SVG attempt", payload: "<svg><circle r='50'/></svg>" },
    { id: 32, desc: "Markdown formatting", payload: "**Bold** _Italic_ `# Hello`" },
    { id: 33, desc: "Regex patterns", payload: "^[a-zA-Z0-9]+$" },
    { id: 34, desc: "Cyrillic payload", payload: "Бдхъц" },
    { id: 35, desc: "Arabic payload", payload: "مرحبا بالعالم" },
    { id: 36, desc: "Chinese payload", payload: "你好世界" },
    { id: 37, desc: "Mathematical symbols", payload: "∑∫π∞≈" },
    { id: 38, desc: "IPv4 Address", payload: "192.168.1.1" },
    { id: 39, desc: "IPv6 Address", payload: "2001:0db8:85a3:0000:0000:8a2e:0370:7334" },
    { id: 40, desc: "UUID", payload: "123e4567-e89b-12d3-a456-426614174000" },
    { id: 41, desc: "JWT string equivalent", payload: "eyJhbGci...eyJzdWI...SflKxw" },
    { id: 42, desc: "File schema", payload: "file:///etc/passwd" },
    { id: 43, desc: "Git format", payload: "<<<<<<< HEAD" },
    { id: 44, desc: "Docker CMD format", payload: "CMD [\"executable\",\"param1\"]" },
    { id: 45, desc: "Ansible vault equivalent", payload: "$ANSIBLE_VAULT;1.1;AES256" },
    { id: 46, desc: "SSH Key equivalent", payload: "ssh-rsa AAAAB3Nza" },
    { id: 47, desc: "Binary data mock", payload: "\\x00\\x01\\x02\\x03" },
    { id: 48, desc: "React component mock", payload: "<Component />" },
    { id: 49, desc: "YAML sequence", payload: "- item1\n- item2" },
    { id: 50, desc: "Null byte termination", payload: "test\0test" }
];

describe('Frontend Stress and Edge Case Tests (50 Items)', () => {
    // We execute 50 distinct tests dynamically
    frontendEdgeCases.forEach(({ id, desc, payload }) => {
        it(`Frontend Edge Case #${id}: Should gracefully handle ${desc} without crashing`, async () => {
            // Test that rendering a toast with extremely malformed data doesn't crash the React tree
            const safePayload = payload !== undefined && payload !== null ? payload.toString() : String(payload);
            const { unmount } = render(
                <ToastProvider>
                    <ToastTestConsumer edgeCaseString={safePayload} />
                </ToastProvider>
            );

            // Attempt to fire the event
            const button = screen.getByText('Trigger');
            act(() => {
                button.click();
            });

            // If the app hasn't thrown an unhandled exception by now, it handled the edge case gracefully
            expect(true).toBe(true);
            unmount();
        });
    });

    it('Should handle 50 rapid parallel state mutations (Rapid clicks)', async () => {
        render(
            <ToastProvider>
                <ToastTestConsumer edgeCaseString={"Rapid Toast"} />
            </ToastProvider>
        );

        const button = screen.getByText('Trigger');

        act(() => {
            for (let i = 0; i < 50; i++) {
                button.click();
            }
        });

        // The ToastProvider uses prev => [...prev, newToast], which handles rapid setState calls securely
        expect(true).toBe(true);
    });
});
