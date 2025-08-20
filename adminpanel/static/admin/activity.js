/**
 * Instagram Activity System JavaScript
 * Handles frontend interactions for the activity management system
 */

class ActivityManager {
    constructor() {
        this.init();
    }

    init() {
        this.bindEvents();
        this.setupAutoRefresh();
    }

    bindEvents() {
        // Global utility functions
        window.showAlert = this.showAlert.bind(this);
        window.hideAlert = this.hideAlert.bind(this);
    }

    setupAutoRefresh() {
        // Auto-refresh stats every 30 seconds on dashboard
        if (window.location.pathname.includes('/activity/')) {
            setInterval(() => {
                this.refreshStats();
            }, 30000);
        }
    }

    async refreshStats() {
        try {
            const response = await fetch('/srdr-proadmin/activity/api/stats');
            const data = await response.json();
            
            if (data.success) {
                this.updateStatsDisplay(data.stats);
            }
        } catch (error) {
            console.error('Failed to refresh stats:', error);
        }
    }

    updateStatsDisplay(stats) {
        // Update dashboard stats if elements exist
        const likesToday = document.querySelector('[data-stat="likes_today"]');
        const followsToday = document.querySelector('[data-stat="follows_today"]');
        const successRate = document.querySelector('[data-stat="success_rate"]');

        if (likesToday) likesToday.textContent = stats.likes_today;
        if (followsToday) followsToday.textContent = stats.follows_today;
        if (successRate) successRate.textContent = stats.success_rate + '%';
    }

    showAlert(message, type = 'info', duration = 5000) {
        // Remove existing alerts
        this.hideAlert();

        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show alert-floating`;
        alertDiv.id = 'floating-alert';
        alertDiv.innerHTML = `
            <div class="d-flex align-items-center">
                <i class="bi bi-${this.getIconForType(type)} me-2"></i>
                <span>${message}</span>
                <button type="button" class="btn-close ms-auto" onclick="hideAlert()"></button>
            </div>
        `;

        document.body.appendChild(alertDiv);

        // Auto-hide after duration
        setTimeout(() => {
            this.hideAlert();
        }, duration);
    }

    hideAlert() {
        const existingAlert = document.getElementById('floating-alert');
        if (existingAlert) {
            existingAlert.remove();
        }
    }

    getIconForType(type) {
        const icons = {
            'success': 'check-circle',
            'danger': 'exclamation-circle',
            'warning': 'exclamation-triangle',
            'info': 'info-circle'
        };
        return icons[type] || 'info-circle';
    }

    // Utility function for making API calls
    async apiCall(url, method = 'GET', data = null) {
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            }
        };

        if (data) {
            options.body = JSON.stringify(data);
        }

        try {
            const response = await fetch(url, options);
            return await response.json();
        } catch (error) {
            console.error('API call failed:', error);
            throw error;
        }
    }

    // Form validation helpers
    validateHashtag(hashtag) {
        const clean = hashtag.trim().replace('#', '');
        return /^[a-zA-Z0-9_]+$/.test(clean) && clean.length > 0 && clean.length <= 100;
    }

    validateUsername(username) {
        const clean = username.trim().replace('@', '');
        return /^[a-zA-Z0-9_.]+$/.test(clean) && clean.length > 0 && clean.length <= 30;
    }

    // Loading state management
    setLoading(element, loading = true) {
        if (loading) {
            element.disabled = true;
            element.dataset.originalText = element.textContent;
            element.innerHTML = '<i class="bi bi-hourglass-split"></i> İşlem yapılıyor...';
        } else {
            element.disabled = false;
            element.textContent = element.dataset.originalText || 'İşlem Yap';
        }
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.activityManager = new ActivityManager();
});

// Common utility functions
function confirmAction(message) {
    return confirm(message);
}

function formatDateTime(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString('tr-TR');
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}