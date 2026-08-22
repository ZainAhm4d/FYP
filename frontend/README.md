# Frontend - BI Dashboard Generator

## Overview
Modern, responsive frontend for the BI Dashboard Generator application. Built with vanilla JavaScript, Tailwind CSS, and production-quality design.

## Tech Stack
- **HTML5** - Semantic markup
- **Tailwind CSS 3.x** - Utility-first CSS framework (CDN)
- **Vanilla JavaScript** - No framework dependencies
- **Google Fonts (Inter)** - Professional typography

## Project Structure
```
frontend/
├── index.html              # Landing page
├── login.html             # Login page
├── register.html          # Registration page
├── dashboard.html         # Main dashboard (placeholder)
├── css/
│   ├── main.css          # Global styles & utilities
│   └── components.css    # Component-specific styles
└── js/
    ├── config.js         # API configuration
    ├── storage.js        # LocalStorage utilities
    ├── api.js            # HTTP client wrapper
    ├── auth.js           # Authentication logic
    ├── components/
    │   └── notifications.js  # Toast notification system
    └── pages/
        ├── login.js      # Login page logic
        └── register.js   # Register page logic
```

## Features Implemented

### Authentication
- ✅ User registration with password validation
- ✅ User login with JWT token storage
- ✅ Automatic redirect if already logged in
- ✅ Protected routes (dashboard requires authentication)
- ✅ Logout functionality
- ✅ Real-time password strength indicator

### UI/UX
- ✅ Responsive design (desktop-first 1920x1080)
- ✅ Modern gradient backgrounds
- ✅ Smooth animations and transitions
- ✅ Professional color scheme (Blue/Indigo/Purple)
- ✅ Toast notification system
- ✅ Form validation with error messages
- ✅ Loading states during API calls

### Pages
1. **Landing Page (index.html)**
   - Hero section with CTA
   - Features showcase
   - How it works section
   - Call-to-action section
   - Responsive navigation

2. **Login Page (login.html)**
   - Email/password form
   - Remember me checkbox
   - Forgot password link
   - Redirect to dashboard on success

3. **Register Page (register.html)**
   - Full name, email, password, confirm password
   - Real-time password strength validation
   - Password requirements display
   - Terms & conditions checkbox

4. **Dashboard Page (dashboard.html)**
   - Welcome message with user name
   - Quick stats cards (placeholder)
   - Action cards for features (coming soon)
   - Recent activity section
   - Logout button

## Configuration

### API Endpoint
Update `js/config.js` to change the backend URL:
```javascript
const CONFIG = {
    API_BASE_URL: 'http://localhost:8000',  // Change this for production
    API_V1: '/api/v1'
};
```

### CORS Setup
Backend must allow frontend origin. Already configured in FastAPI for:
- http://localhost:3000
- http://localhost:5500
- http://127.0.0.1:3000
- http://127.0.0.1:5500

## Running the Frontend

### Option 1: Live Server (VS Code Extension)
1. Install "Live Server" extension in VS Code
2. Right-click `index.html` → "Open with Live Server"
3. Default: http://localhost:5500

### Option 2: Python HTTP Server
```bash
# Navigate to frontend directory
cd "d:\VSCode\FYP 2\frontend"

# Start server
python -m http.server 5500

# Open browser: http://localhost:5500
```

### Option 3: Simple HTTP Server (Node.js)
```bash
# Install http-server globally
npm install -g http-server

# Start server
http-server -p 5500

# Open browser: http://localhost:5500
```

## Testing Authentication Flow

### 1. Register New User
1. Go to http://localhost:5500/register.html
2. Fill in:
   - Full Name: Test User
   - Email: newuser@example.com
   - Password: Test123!@# (meets requirements)
   - Confirm Password: Test123!@#
3. Check terms & conditions
4. Click "Create Account"
5. Should redirect to login page

### 2. Login
1. Go to http://localhost:5500/login.html
2. Enter credentials:
   - Email: test@example.com (or your new user)
   - Password: Test123!@#
3. Click "Sign In"
4. Should redirect to dashboard with user name displayed

### 3. Logout
1. On dashboard, click "Logout" button
2. Should clear token and redirect to login

## Password Requirements
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one number
- At least one special character (!@#$%^&*)

## Browser Support
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Known Limitations (Day 1)
- Dashboard features are placeholders (datasets, queries, visualizations coming in later days)
- No "Forgot Password" functionality yet
- No social login (OAuth) yet
- Mobile responsiveness needs improvement (desktop-first approach)

## Next Steps (Day 2-4)
- Dataset upload functionality
- Natural language query interface
- SQL generation and execution
- Chart visualizations with Chart.js
- Dashboard creation and management

## Color Palette
```css
Primary Blue:    #3B82F6
Secondary Indigo: #6366F1
Success Green:   #10B981
Error Red:       #EF4444
Warning Yellow:  #F59E0B
Background:      #F9FAFB
```

## File Sizes (Approximate)
- Total frontend: ~50 KB (excluding external CDN resources)
- HTML pages: ~25 KB combined
- JavaScript: ~20 KB
- Custom CSS: ~5 KB

## Performance
- First Contentful Paint: < 1s
- Time to Interactive: < 2s
- No build step required (vanilla JS)
- CDN resources cached by browser

## Security Notes
- JWT tokens stored in LocalStorage (XSS consideration)
- HTTPS recommended for production
- CORS properly configured on backend
- No sensitive data in localStorage except token

## Debugging
Open browser console (F12) to see:
- API request/response logs
- Authentication state
- Error messages
- Network calls

## Contributing
This is part of FYP 2 (Final Year Project). Follow the 40% Milestone Plan for feature additions.
