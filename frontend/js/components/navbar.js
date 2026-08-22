/**
 * Navigation Bar Component
 * Renders consistent navigation across all pages.
 * Styled from design tokens (css/tokens.css); icons are Lucide.
 */

const Navbar = {
    navItems: [
        { id: 'dashboard',  label: 'Dashboard',        icon: 'layout-dashboard', href: 'dashboard.html' },
        { id: 'upload',     label: 'Upload',           icon: 'upload',           href: 'upload.html' },
        { id: 'datasets',   label: 'Datasets',         icon: 'database',         href: 'datasets.html' },
        { id: 'query',      label: 'Query Builder',    icon: 'terminal-square',  href: 'query.html' },
        { id: 'saved',      label: 'Saved Dashboards', icon: 'bookmark',         href: 'saved-dashboards.html' }
    ],

    render(activePage = '') {
        const isAuthenticated = Auth.isAuthenticated();
        const user = Auth.getCurrentUser();
        const initial = user?.full_name?.charAt(0).toUpperCase() || 'U';
        const userName = user?.full_name || 'User';
        const userEmail = user?.email || '';

        // CH-18: admins get an extra nav item (server enforces access regardless)
        const items = user?.is_admin
            ? [...this.navItems, { id: 'admin', label: 'Admin', icon: 'shield', href: 'admin.html' }]
            : this.navItems;

        const links = isAuthenticated ? items.map(item => {
            const active = activePage === item.id;
            return `<a href="${item.href}" class="nav-link${active ? ' nav-link-active' : ''}">
                <i data-lucide="${item.icon}"></i>${item.label}
            </a>`;
        }).join('') : `
            <a href="index.html#features" class="nav-link">Features</a>
            <a href="index.html?login=1" class="nav-btn-outline">Sign In</a>
            <a href="index.html?register=1" class="nav-btn-solid">Get Started</a>
        `;

        const userMenu = isAuthenticated ? `
            <div style="position:relative;display:inline-block;" id="navUserMenuWrapper">
                <button id="navUserMenuBtn" class="nav-user-btn">
                    <span class="nav-avatar">${initial}</span>
                    <span class="nav-user-name">${userName}</span>
                    <i data-lucide="chevron-down" style="width:14px;height:14px;color:var(--ink-500);"></i>
                </button>
                <div id="navUserDropdown" class="nav-dropdown">
                    <div class="nav-dropdown-head">
                        <p style="margin:0;font-size:var(--text-sm);font-weight:700;color:var(--ink-900);">${userName}</p>
                        <p style="margin:4px 0 0;font-size:var(--text-xs);color:var(--ink-500);">${userEmail}</p>
                    </div>
                    <button id="navLogoutBtn" class="nav-logout">
                        <i data-lucide="log-out"></i>Logout
                    </button>
                </div>
            </div>
        ` : '';

        const mobileLinks = isAuthenticated ? items.map(item => {
            const active = activePage === item.id;
            return `<a href="${item.href}" class="nav-mobile-link${active ? ' nav-link-active' : ''}">
                <i data-lucide="${item.icon}"></i>${item.label}
            </a>`;
        }).join('') : '';

        return `
        <style>
            #mainNavbar {
                position:fixed;top:0;left:0;right:0;z-index:1000;
                background:rgba(240,250,250,0.92);
                backdrop-filter:blur(12px);
                border-bottom:1px solid #e2e8f0;
            }
            #navInner { max-width:1280px;margin:0 auto;padding:0 24px;height:64px;display:flex;align-items:center;justify-content:space-between;gap:16px; }
            #navLinks { display:flex;align-items:center;gap:2px; }
            .nav-brand {
                text-decoration:none;display:flex;align-items:center;gap:8px;
                font-family:'Nunito',sans-serif;font-size:1.2rem;font-weight:900;color:#1a2332;
                white-space:nowrap;
            }
            .nav-brand-mark {
                display:flex;align-items:center;justify-content:center;color:#2dd4bf;flex-shrink:0;
            }
            .nav-brand-mark i, .nav-brand-mark svg { width:22px;height:22px; }
            .nav-link {
                display:inline-flex;align-items:center;gap:7px;
                text-decoration:none;padding:8px 13px;border-radius:8px;
                font-size:0.9rem;font-weight:500;color:#64748b;
                font-family:'Plus Jakarta Sans',sans-serif;
                transition:background .2s, color .2s;
                white-space:nowrap;
            }
            .nav-link i, .nav-link svg { width:15px;height:15px;color:#94a3b8;transition:color .2s; }
            .nav-link:hover { background:#e6faf8;color:#1a2332; }
            .nav-link-active { background:#e6faf8;color:#14b8a6;font-weight:600; }
            .nav-link-active i, .nav-link-active svg { color:#14b8a6; }
            .nav-btn-outline {
                text-decoration:none;font-size:0.9rem;font-weight:700;color:#14b8a6;
                font-family:'Plus Jakarta Sans',sans-serif;
                padding:8px 16px;background:none;border:none;border-radius:8px;
                transition:background .2s;white-space:nowrap;
            }
            .nav-btn-outline:hover { background:#e6faf8; }
            .nav-btn-solid {
                text-decoration:none;font-size:0.9rem;font-weight:700;color:#fff;
                font-family:'Plus Jakarta Sans',sans-serif;
                padding:10px 20px;background:#2dd4bf;border-radius:10px;
                transition:all .2s;white-space:nowrap;display:inline-flex;align-items:center;
            }
            .nav-btn-solid:hover { background:#14b8a6;transform:translateY(-1px);box-shadow:0 4px 16px rgba(45,212,191,0.35); }
            .nav-user-btn {
                display:flex;align-items:center;gap:9px;background:none;border:none;cursor:pointer;
                padding:6px 10px;border-radius:8px;transition:background .2s;
            }
            .nav-user-btn:hover { background:#e6faf8; }
            .nav-avatar {
                width:32px;height:32px;background:#2dd4bf;color:#fff;border-radius:50%;
                display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;
                font-family:'Nunito',sans-serif;
            }
            .nav-user-name { font-size:0.9rem;font-weight:600;color:#1a2332;font-family:'Plus Jakarta Sans',sans-serif; }
            .nav-dropdown {
                display:none;position:absolute;right:0;top:calc(100% + 8px);
                background:#fff;border-radius:12px;box-shadow:0 8px 40px rgba(45,212,191,0.15);
                min-width:210px;z-index:9999;overflow:hidden;border:1px solid #e2e8f0;
            }
            .nav-dropdown-head { padding:12px 16px;border-bottom:1px solid #e2e8f0;background:#f0fafa; }
            .nav-logout {
                display:flex;align-items:center;gap:8px;width:100%;text-align:left;padding:11px 16px;
                background:none;border:none;cursor:pointer;font-size:0.9rem;font-family:'Plus Jakarta Sans',sans-serif;
                color:#ef4444;font-weight:600;transition:background .2s;
            }
            .nav-logout:hover { background:#fef2f2; }
            .nav-logout i, .nav-logout svg { width:15px;height:15px; }
            #navHamburger { display:none;background:none;border:none;cursor:pointer;padding:6px;color:#1a2332; }
            #mobileMenuPanel { display:none;background:#fff;border-top:1px solid #e2e8f0;padding:12px 20px 16px; }
            .nav-mobile-link {
                display:flex;align-items:center;gap:10px;text-decoration:none;padding:11px 14px;border-radius:8px;
                font-size:15px;font-weight:500;color:#64748b;font-family:'Plus Jakarta Sans',sans-serif;
            }
            .nav-mobile-link i, .nav-mobile-link svg { width:16px;height:16px;color:#94a3b8; }
            .nav-mobile-link.nav-link-active { background:#e6faf8;color:#14b8a6; }
            @media(max-width:900px){
                #navLinks { display:none; }
                #navHamburger { display:block; }
                #mobileMenuPanel.open { display:block; }
                .nav-user-name { display:none; }
            }
            #navSpacer { height:64px; }
        </style>
        <nav id="mainNavbar">
            <div id="navInner">
                <a href="${isAuthenticated ? 'dashboard.html' : 'index.html'}" class="nav-brand">
                    <span class="nav-brand-mark">
                        <svg width="22" height="22" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M3 3v18h18M7 15l4-5 3 3 5-7"/>
                        </svg>
                    </span>
                    BI&nbsp;Dashboard
                </a>
                <div id="navLinks">
                    ${links}
                </div>
                <div style="display:flex;align-items:center;gap:8px;">
                    ${userMenu}
                    <button id="navHamburger" onclick="document.getElementById('mobileMenuPanel').classList.toggle('open')">
                        <i data-lucide="menu" style="width:22px;height:22px;"></i>
                    </button>
                </div>
            </div>
            <div id="mobileMenuPanel">
                ${mobileLinks}
                ${isAuthenticated ? `<button onclick="Navbar.handleLogout(event)" class="nav-logout" style="margin-top:8px;"><i data-lucide="log-out"></i>Logout</button>` : ''}
            </div>
        </nav>
        <div id="navSpacer"></div>
        `;
    },

    init(activePage = '') {
        const container = document.getElementById('navbar-container');
        if (container) {
            container.innerHTML = this.render(activePage);
        }

        // Render Lucide icons inside the freshly injected markup.
        // The library loads from a CDN — retry until it's available so the
        // navbar never renders label-only on a slow connection or cold cache.
        const renderNavIcons = (attempt = 0) => {
            if (window.lucide) { try { lucide.createIcons(); } catch (_) {} return; }
            if (attempt < 20) setTimeout(() => renderNavIcons(attempt + 1), 150);
        };
        renderNavIcons();
        window.addEventListener('load', () => renderNavIcons());

        // User menu dropdown toggle
        const menuBtn = document.getElementById('navUserMenuBtn');
        const dropdown = document.getElementById('navUserDropdown');
        if (menuBtn && dropdown) {
            menuBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                dropdown.style.display = dropdown.style.display === 'block' ? 'none' : 'block';
            });
            document.addEventListener('click', () => {
                dropdown.style.display = 'none';
            });
        }

        // Logout
        const logoutBtn = document.getElementById('navLogoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', this.handleLogout);
        }
    },

    handleLogout(e) {
        e.preventDefault();
        Auth.logout();
        Notifications.success('Logged out successfully');
        setTimeout(() => { window.location.href = 'index.html'; }, 1000);
    }
};
