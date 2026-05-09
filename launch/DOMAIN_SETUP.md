# SunCredit — Domain & HTTPS Setup

## Step 1: Buy Domain
- **Cloudflare Registrar** (~$10/yr, free WHOIS privacy)
- **Namecheap** (~$13/yr)
- Recommended: **suncredit.com** (or suncredit.io / suncredit.app as backup)

## Step 2: DNS Configuration
Point A record to your server's public IP (or use Cloudflare proxy):
- Record: `@` → A → [SERVER_IP]
- Record: `www` → CNAME → suncredit.com

## Step 3: HTTPS Setup

### Option A: Nginx + Let's Encrypt (Cheapest)
```bash
sudo apt install nginx certbot python3-certbot-nginx -y
sudo certbot --nginx -d suncredit.com -d www.suncredit.com
```

Nginx config (`/etc/nginx/sites-available/suncredit`):
```
server {
    listen 80;
    server_name suncredit.com www.suncredit.com;
    return 301 https://$server_name$request_uri;
}
server {
    listen 443 ssl;
    server_name suncredit.com www.suncredit.com;
    ssl_certificate /etc/letsencrypt/live/suncredit.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/suncredit.com/privkey.pem;
    
    location / {
        proxy_pass http://127.0.0.1:8086;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

### Option B: Cloudflare Tunnel (Easiest)
```bash
# Install cloudflared
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb

# Authenticate
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create suncredit
cloudflared tunnel route dns suncredit suncredit.com

# Run as service
sudo cloudflared service install
```

## Step 4: Update Stripe Webhook
- In Stripe Dashboard → Developers → Webhooks
- Endpoint URL: `https://suncredit.com/stripe/webhook`
- Get the new signing secret and update `.env`

## Step 5: Verify
- Visit `https://suncredit.com` — should serve your platform
- Check SSL grade at https://www.ssllabs.com/ssltest/ — aim for A+
