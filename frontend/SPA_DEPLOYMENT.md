# Flutter Web SPA Deployment Configuration

## Deployment Target
- **Domain**: app.avenqo.ca
- **Build Output**: `frontend/build/web`
- **Build Command**: `flutter build web --release --dart-define=API_BASE_URL=https://api.avenqo.ca/api/v1`

## SPA Rewrite Rule

For direct navigation and page refresh to work correctly on Flutter Web, configure your web server to serve `index.html` for all unknown routes:

### Vercel Configuration (vercel.json)
```json
{
  "rewrites": [
    {
      "source": "/(?!.*\\.(?:js|css|png|jpg|jpeg|gif|svg|woff|woff2|ttf|eot)$)",
      "destination": "/index.html"
    }
  ]
}
```

### Netlify Configuration (netlify.toml)
```toml
[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

### Nginx Configuration
```nginx
server {
    listen 80;
    server_name app.avenqo.ca;
    root /path/to/frontend/build/web;

    location / {
        try_files $uri /index.html =404;
    }

    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|svg|woff|woff2|ttf|eot)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

### Apache Configuration (.htaccess)
```apache
<IfModule mod_rewrite.c>
  RewriteEngine On
  RewriteBase /
  RewriteCond %{REQUEST_FILENAME} !-f
  RewriteCond %{REQUEST_FILENAME} !-d
  RewriteRule ^ index.html [QSA,L]
</IfModule>
```

## Protected Routes

The following routes require user authentication (redirects to `/login` if not authenticated):

- `/dashboard` - Main dashboard
- `/assistant` - AI Assistant
- `/sales` - Sales analytics
- `/customers` - Customer management
- `/products` - Product management
- `/recommendations` - AI recommendations
- `/alerts` - System alerts
- `/reports` - Reports
- `/connections` - External integrations
- `/team` - Team management
- `/billing` - Billing and subscription
- `/settings` - Application settings
- `/support` - Support page

## Admin Routes

Platform administrators have access to additional routes (non-admins redirect to `/dashboard`):

- `/admin` - Admin dashboard
- `/admin/companies` - Company management
- `/admin/companies/:id` - Company details
- `/admin/audit-log` - Audit log
- `/admin/subscriptions` - Subscription management
- `/admin/billing` - Billing administration
- `/admin/ai-usage` - AI usage tracking
- `/admin/providers` - Provider management
- `/admin/system-health` - System health
- `/admin/support` - Support administration
- `/admin/settings` - Admin settings

## Public Routes

Unauthenticated users can access:

- `/` - Landing page
- `/pricing` - Pricing page
- `/login` - Login form
- `/register` - Registration form
- `/forgot-password` - Password recovery
- `/verify-email` - Email verification
- `/reset-password` - Password reset form

## API Configuration

- **Development**: `http://127.0.0.1:8000/api/v1` (default, no build flag needed)
- **Production**: `https://api.avenqo.ca/api/v1` (passed at build time via `--dart-define`)

## Build Output Structure

```
frontend/build/web/
├── index.html              # SPA entry point
├── main.dart.js            # Compiled Flutter app
├── flutter.js              # Flutter runtime
├── flutter_service_worker.js  # Service worker
└── assets/                 # Static assets
    ├── fonts/
    ├── images/
    └── ...
```

## Deployment Checklist

- [ ] Deploy `frontend/build/web/` to web server at app.avenqo.ca
- [ ] Configure SPA rewrite rule (serve index.html for unknown routes)
- [ ] Set cache headers for static assets (30+ days)
- [ ] Verify direct navigation works: `https://app.avenqo.ca/dashboard`
- [ ] Verify page refresh works on all routes
- [ ] Verify unauthenticated redirect to login works
- [ ] Test theme switcher (light/dark/system)
- [ ] Verify API endpoints use `https://api.avenqo.ca/api/v1`
- [ ] Test cross-origin requests if API is on different domain (CORS configured on backend)
