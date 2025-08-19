// /adminpanel/static/admin/ads.js
(function(){
  // Aktif/pasif toggle
  document.addEventListener('click', function(e){
    const btn = e.target.closest('.js-toggle');
    if(!btn) return;
    const slot = btn.dataset.slot;
    const active = btn.dataset.active === 'true'; // server'a gidecek yeni durum
    fetch(`/srdr-proadmin/ads/toggle/${encodeURIComponent(slot)}`, {
      method: 'POST',
      headers: {'Content-Type':'application/x-www-form-urlencoded'},
      body: `active=${active}`
    }).then(r => r.ok ? r.json() : Promise.reject())
      .then(_ => location.reload())
      .catch(_ => alert('Toggle başarısız oldu.'));
  });

  // Slot kodu kopyalama
  document.querySelectorAll('.copyable').forEach(el => {
    el.addEventListener('click', () => {
      const t = el.textContent.trim();
      navigator.clipboard && navigator.clipboard.writeText(t);
      el.classList.add('text-success');
      setTimeout(() => el.classList.remove('text-success'), 1000);
    });
  });
})();
