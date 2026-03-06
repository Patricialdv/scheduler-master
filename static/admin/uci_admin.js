(function() {
    function injectNavbar() {
        if (document.getElementById('uci-navbar')) return;

        var navbar = document.createElement('nav');
        navbar.id = 'uci-navbar';
        navbar.style.cssText = [
            'position:fixed', 'top:0', 'left:0', 'right:0', 'z-index:99999',
            'display:flex', 'align-items:center', 'justify-content:space-between',
            'background:#1a1a2e', 'padding:0 24px', 'height:56px',
            'box-shadow:0 2px 8px rgba(0,0,0,0.25)',
            'font-family:Arial,sans-serif'
        ].join(';');

        var isLoggedIn = document.querySelector('#user-tools') !== null;

        navbar.innerHTML = `
            <a href="/" style="color:white;text-decoration:none;font-size:1.05rem;font-weight:700;display:flex;align-items:center;gap:8px;">
                🎓 UCI Scheduler
            </a>
            <div style="display:flex;align-items:center;gap:4px;">
                <a href="/" style="color:rgba(255,255,255,0.72);text-decoration:none;padding:6px 13px;border-radius:6px;font-size:0.88rem;font-weight:500;"
                onmouseover="this.style.background='rgba(255,255,255,0.1)';this.style.color='white'"
                onmouseout="this.style.background='transparent';this.style.color='rgba(255,255,255,0.72)'">
                🏠 Inicio
                </a>
                <a href="/schedule/" style="color:rgba(255,255,255,0.72);text-decoration:none;padding:6px 13px;border-radius:6px;font-size:0.88rem;font-weight:500;"
                onmouseover="this.style.background='rgba(255,255,255,0.1)';this.style.color='white'"
                onmouseout="this.style.background='transparent';this.style.color='rgba(255,255,255,0.72)'">
                📅 Horarios
                </a>
                <span style="color:white;padding:6px 13px;border-radius:6px;font-size:0.88rem;font-weight:500;background:rgba(255,255,255,0.14);">
                    ⚙️ Admin
                </span>
                ${isLoggedIn ? `<a href="/accounts/logout/" style="color:rgba(255,110,110,0.85);text-decoration:none;padding:6px 13px;border-radius:6px;font-size:0.88rem;font-weight:500;"
                onmouseover="this.style.background='rgba(255,80,80,0.13)';this.style.color='#ff6b6b'"
                onmouseout="this.style.background='transparent';this.style.color='rgba(255,110,110,0.85)'">
                Cerrar sesión
                </a>` : ''}
            </div>
        `;

        document.body.insertBefore(navbar, document.body.firstChild);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', injectNavbar);
    } else {
        injectNavbar();
    }
})();