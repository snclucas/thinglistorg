/**
 * Toast Notification System
 * Provides client-side toast notifications with different types (success, error, info, warning)
 */

class Toast {
    constructor(message, type = 'info', duration = 5000) {
        this.message = message;
        this.type = type;
        this.duration = duration;
        this.element = null;
    }

    show() {
        const container = document.getElementById('toastContainer');

        this.element = document.createElement('div');
        this.element.className = `toast toast-${this.type}`;
        this.element.textContent = this.message;

        container.appendChild(this.element);

        // Auto-hide after duration
        if (this.duration > 0) {
            setTimeout(() => this.hide(), this.duration);
        }

        return this;
    }

    hide() {
        if (this.element) {
            this.element.classList.add('hide');
            setTimeout(() => {
                if (this.element && this.element.parentNode) {
                    this.element.parentNode.removeChild(this.element);
                }
            }, 300);
        }
    }

    static success(message, duration = 5000) {
        return new Toast(message, 'success', duration).show();
    }

    static error(message, duration = 5000) {
        return new Toast(message, 'error', duration).show();
    }

    static warning(message, duration = 5000) {
        return new Toast(message, 'warning', duration).show();
    }

    static info(message, duration = 5000) {
        return new Toast(message, 'info', duration).show();
    }
}

// Show server-side flash messages as toasts
document.addEventListener('DOMContentLoaded', function () {
    const flashMessages = document.getElementById('flashMessages');
    if (flashMessages) {
        flashMessages.querySelectorAll('[data-message]').forEach(item => {
            const type = item.getAttribute('data-type');
            const message = item.getAttribute('data-message');
            Toast[type](message);
        });
    }
});

// Global function for client-side toasts
window.showToast = function (message, type = 'info', duration = 5000) {
    return Toast[type](message, duration);
};
