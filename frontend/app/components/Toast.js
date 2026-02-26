'use client';

function Toast({ message, type, onClose }) {
    const icon = type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ';
    return (
        <div className={`toast toast-${type}`} role="alert">
            <div className="toast-icon">{icon}</div>
            <div className="toast-message">{message}</div>
            <button className="toast-close" onClick={onClose} aria-label="Close notification">×</button>
        </div>
    );
}

export default Toast;
