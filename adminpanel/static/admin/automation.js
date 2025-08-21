/**
 * Instagram Automation JavaScript
 * Admin panel için otomasyon kontrol fonksiyonları
 */

// Global değişkenler
let automationData = {
    status: null,
    sessions: [],
    activities: []
};

let refreshInterval = null;

// Sayfa yüklendiğinde çalışacak fonksiyonlar
document.addEventListener('DOMContentLoaded', function() {
    initializeAutomation();
    
    // Event listeners
    setupEventListeners();
    
    // Auto refresh başlat
    startAutoRefresh();
});

function initializeAutomation() {
    loadAutomationStatus();
    loadSessions();
    loadRecentActivities();
}

function setupEventListeners() {
    // Automation control buttons
    const startBtn = document.getElementById('start-automation');
    const stopBtn = document.getElementById('stop-automation');
    const keepAliveBtn = document.getElementById('schedule-keepalive');
    const randomBtn = document.getElementById('schedule-random');
    
    if (startBtn) {
        startBtn.addEventListener('click', startAutomation);
    }
    if (stopBtn) {
        stopBtn.addEventListener('click', stopAutomation);
    }
    if (keepAliveBtn) {
        keepAliveBtn.addEventListener('click', scheduleKeepAliveAll);
    }
    if (randomBtn) {
        randomBtn.addEventListener('click', scheduleRandomActivity);
    }
}

// ============================================================================
// API İletişim Fonksiyonları
// ============================================================================

function loadAutomationStatus() {
    fetch('/srdr-proadmin/api/automation/status')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                automationData.status = data;
                updateStatusDisplay();
                updateStatsCards();
            } else {
                console.error('Error loading automation status:', data.error);
                showNotification('Otomasyon durumu yüklenemedi', 'error');
            }
        })
        .catch(error => {
            console.error('Error loading automation status:', error);
            showNotification('Bağlantı hatası', 'error');
        });
}

function loadSessions() {
    fetch('/srdr-proadmin/api/automation/sessions')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                automationData.sessions = data.sessions;
                updateSessionSelects();
            } else {
                console.error('Error loading sessions:', data.error);
            }
        })
        .catch(error => {
            console.error('Error loading sessions:', error);
        });
}

function loadRecentActivities() {
    fetch('/srdr-proadmin/api/automation/activities?limit=10')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                automationData.activities = data.activities;
                updateRecentActivitiesTable();
            } else {
                console.error('Error loading activities:', data.error);
            }
        })
        .catch(error => {
            console.error('Error loading activities:', error);
        });
}

function loadConfig() {
    return fetch('/srdr-proadmin/api/automation/config')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                return data.config;
            } else {
                throw new Error(data.error);
            }
        });
}

// ============================================================================
// Display Update Fonksiyonları
// ============================================================================

function updateStatusDisplay() {
    const statusElement = document.getElementById('automation-status');
    const lastUpdateElement = document.getElementById('last-update');
    
    if (statusElement && automationData.status) {
        const isActive = automationData.status.automation_active;
        statusElement.textContent = `Durum: ${isActive ? 'Aktif' : 'Pasif'}`;
        statusElement.className = `badge ${isActive ? 'bg-success' : 'bg-secondary'}`;
    }
    
    if (lastUpdateElement) {
        lastUpdateElement.textContent = `Son Güncelleme: ${new Date().toLocaleTimeString('tr-TR')}`;
    }
}

function updateStatsCards() {
    if (!automationData.status) return;
    
    const sessionStats = automationData.status.session_stats;
    const activityStats = automationData.status.activity_stats;
    
    // Session stats
    updateElementText('active-sessions', sessionStats.active || 0);
    updateElementText('pending-activities', activityStats.pending || 0);
    updateElementText('completed-today', activityStats.completed || 0);
    updateElementText('success-rate', `${activityStats.success_rate || 0}%`);
}

function updateElementText(elementId, text) {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = text;
    }
}

function updateSessionSelects() {
    const selects = document.querySelectorAll('select[name="session_user"]');
    
    selects.forEach(select => {
        select.innerHTML = '<option value="">Kullanıcı seçiniz...</option>';
        
        automationData.sessions.forEach(session => {
            if (session.status === 'active') {
                const option = document.createElement('option');
                option.value = session.user;
                option.textContent = `${session.user} (${session.success_rate}% başarı)`;
                select.appendChild(option);
            }
        });
    });
}

function updateRecentActivitiesTable() {
    const tbody = document.querySelector('#recent-activities-table tbody');
    if (!tbody) return;
    
    if (!automationData.activities.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">Henüz aktivite yok</td></tr>';
        return;
    }
    
    tbody.innerHTML = automationData.activities.slice(0, 10).map(activity => {
        const date = new Date(activity.created_at * 1000).toLocaleString('tr-TR');
        const statusBadge = getStatusBadge(activity.status);
        
        return `
            <tr>
                <td>${date}</td>
                <td><strong>${activity.session_user}</strong></td>
                <td>
                    <span class="badge bg-secondary">${getActivityTypeLabel(activity.activity_type)}</span>
                </td>
                <td>${activity.target || '-'}</td>
                <td>${statusBadge}</td>
                <td>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-info btn-sm" onclick="showActivityDetails('${activity.id}')" title="Detaylar">
                            <i class="fas fa-info"></i>
                        </button>
                        ${activity.status === 'failed' ? 
                            `<button class="btn btn-outline-warning btn-sm" onclick="retryActivity('${activity.id}')" title="Yeniden Dene">
                                <i class="fas fa-redo"></i>
                            </button>` : ''
                        }
                        ${activity.status === 'pending' ? 
                            `<button class="btn btn-outline-danger btn-sm" onclick="cancelActivity('${activity.id}')" title="İptal Et">
                                <i class="fas fa-times"></i>
                            </button>` : ''
                        }
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

// ============================================================================
// Otomasyon Kontrol Fonksiyonları
// ============================================================================

function startAutomation() {
    fetch('/srdr-proadmin/api/automation/start-scheduler', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Otomasyon başlatıldı', 'success');
            loadAutomationStatus();
        } else {
            showNotification('Otomasyon başlatılamadı: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showNotification('Hata: ' + error.message, 'error');
    });
}

function stopAutomation() {
    if (!confirm('Otomasyonu durdurmak istediğinizden emin misiniz?')) {
        return;
    }
    
    fetch('/srdr-proadmin/api/automation/stop-scheduler', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Otomasyon durduruldu', 'warning');
            loadAutomationStatus();
        } else {
            showNotification('Otomasyon durdurulamadı: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showNotification('Hata: ' + error.message, 'error');
    });
}

function scheduleKeepAliveAll() {
    fetch('/srdr-proadmin/api/automation/schedule-keepalive', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({})
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification(data.message, 'success');
            loadRecentActivities();
        } else {
            showNotification('Keep-alive zamanlanamadı: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showNotification('Hata: ' + error.message, 'error');
    });
}

function scheduleRandomActivity() {
    const availableUsers = automationData.sessions.filter(s => s.status === 'active');
    if (!availableUsers.length) {
        showNotification('Aktif session bulunamadı', 'warning');
        return;
    }
    
    const randomUser = availableUsers[Math.floor(Math.random() * availableUsers.length)];
    
    fetch('/srdr-proadmin/api/automation/schedule-random', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            session_user: randomUser.user
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification(data.message, 'success');
            loadRecentActivities();
        } else {
            showNotification('Rastgele aktivite zamanlanamadı: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showNotification('Hata: ' + error.message, 'error');
    });
}

// ============================================================================
// Modal Fonksiyonları
// ============================================================================

function scheduleActivity(activityType) {
    const modal = new bootstrap.Modal(document.getElementById('activityModal'));
    
    // Form'u temizle ve activity type'ı set et
    const form = document.getElementById('activity-form');
    form.reset();
    
    const typeSelect = form.querySelector('[name="activity_type"]');
    if (typeSelect) {
        typeSelect.value = activityType;
    }
    
    modal.show();
}

function submitActivity() {
    const form = document.getElementById('activity-form');
    const formData = new FormData(form);
    
    const activityData = {
        activity_type: formData.get('activity_type'),
        session_user: formData.get('session_user'),
        target: formData.get('target') || null,
        delay_seconds: parseInt(formData.get('delay_seconds')) || 0,
        metadata: {
            count: parseInt(formData.get('count')) || 1
        }
    };
    
    if (!activityData.activity_type || !activityData.session_user) {
        showNotification('Aktivite türü ve kullanıcı seçmelisiniz', 'warning');
        return;
    }
    
    fetch('/srdr-proadmin/api/automation/schedule-activity', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(activityData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification(data.message, 'success');
            bootstrap.Modal.getInstance(document.getElementById('activityModal')).hide();
            loadRecentActivities();
        } else {
            showNotification('Aktivite zamanlanamadı: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showNotification('Hata: ' + error.message, 'error');
    });
}

function showConfigModal() {
    const modal = new bootstrap.Modal(document.getElementById('configModal'));
    
    // Mevcut config değerlerini yükle
    loadConfig().then(config => {
        const form = document.getElementById('config-form');
        
        // Form alanlarını doldur
        Object.keys(config).forEach(key => {
            const input = form.querySelector(`[name="${key}"]`);
            if (input) {
                let value = config[key];
                if (key.includes('probability')) {
                    value = value * 100; // Yüzde olarak göster
                }
                input.value = value;
            }
        });
        
        modal.show();
    }).catch(error => {
        showNotification('Config yüklenemedi: ' + error.message, 'error');
    });
}

function saveConfig() {
    const form = document.getElementById('config-form');
    const formData = new FormData(form);
    
    const configData = {};
    for (let [key, value] of formData.entries()) {
        if (key.includes('probability')) {
            configData[key] = parseFloat(value) / 100; // Yüzdeden decimal'e çevir
        } else {
            configData[key] = isNaN(value) ? value : Number(value);
        }
    }
    
    fetch('/srdr-proadmin/api/automation/config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(configData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification(data.message, 'success');
            bootstrap.Modal.getInstance(document.getElementById('configModal')).hide();
        } else {
            showNotification('Config kaydedilemedi: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showNotification('Hata: ' + error.message, 'error');
    });
}

// ============================================================================
// Aktivite İşlemleri
// ============================================================================

function retryActivity(activityId) {
    fetch('/srdr-proadmin/api/automation/retry-activity', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            activity_id: activityId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Aktivite yeniden deneme için zamanlandı', 'success');
            loadRecentActivities();
        } else {
            showNotification('Aktivite yeniden denemeye alınamadı: ' + data.message, 'error');
        }
    })
    .catch(error => {
        showNotification('Hata: ' + error.message, 'error');
    });
}

function cancelActivity(activityId) {
    if (!confirm('Bu aktiviteyi iptal etmek istediğinizden emin misiniz?')) {
        return;
    }
    
    fetch('/srdr-proadmin/api/automation/cancel-activity', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            activity_id: activityId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Aktivite iptal edildi', 'success');
            loadRecentActivities();
        } else {
            showNotification('Aktivite iptal edilemedi: ' + data.message, 'error');
        }
    })
    .catch(error => {
        showNotification('Hata: ' + error.message, 'error');
    });
}

// ============================================================================
// Yardımcı Fonksiyonlar
// ============================================================================

function getStatusBadge(status) {
    const badges = {
        'pending': '<span class="badge bg-warning">Bekleyen</span>',
        'running': '<span class="badge bg-info">Çalışan</span>',
        'completed': '<span class="badge bg-success">Tamamlanan</span>',
        'failed': '<span class="badge bg-danger">Başarısız</span>',
        'cancelled': '<span class="badge bg-secondary">İptal</span>'
    };
    return badges[status] || '<span class="badge bg-light">Bilinmiyor</span>';
}

function getActivityTypeLabel(type) {
    const labels = {
        'like': 'Beğeni',
        'follow': 'Takip',
        'comment': 'Yorum',
        'story_view': 'Story İzle',
        'profile_visit': 'Profil Ziyaret',
        'explore_browse': 'Keşfet Gezin',
        'session_keepalive': 'Keep-Alive'
    };
    return labels[type] || type;
}

function startAutoRefresh() {
    stopAutoRefresh();
    refreshInterval = setInterval(() => {
        loadAutomationStatus();
        loadRecentActivities();
    }, 30000); // 30 saniye
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

function showNotification(message, type = 'info') {
    // Bootstrap toast kullanarak bildirim göster
    const toastHtml = `
        <div class="toast align-items-center text-white bg-${type === 'error' ? 'danger' : type} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;
    
    // Toast container oluştur (yoksa)
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
        toastContainer.style.zIndex = '9999';
        document.body.appendChild(toastContainer);
    }
    
    // Toast'ı ekle
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    
    // Toast'ı göster
    const toastElement = toastContainer.lastElementChild;
    const toast = new bootstrap.Toast(toastElement, {
        autohide: true,
        delay: type === 'error' ? 5000 : 3000
    });
    
    toast.show();
    
    // Toast kapandıktan sonra DOM'dan kaldır
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

// ============================================================================
// Temizlik İşlemleri
// ============================================================================

window.addEventListener('beforeunload', function() {
    stopAutoRefresh();
});

// Export fonksiyonları global scope'a
window.scheduleActivity = scheduleActivity;
window.submitActivity = submitActivity;
window.showConfigModal = showConfigModal;
window.saveConfig = saveConfig;
window.retryActivity = retryActivity;
window.cancelActivity = cancelActivity;