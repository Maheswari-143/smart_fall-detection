<<<<<<< HEAD
# SmartFall - AI-Powered Fall Detection System

A cutting-edge, real-time fall detection system powered by YOLOv8 technology designed for elderly care and personal safety monitoring.

## Features

**Real-Time Monitoring** - Continuously monitors activity with advanced AI to detect falls as they happen  
**High Accuracy & Reliability** - Powered by YOLOv8, minimizes false alarms with precise detection  
**Instant Alert System** - Automatically dispatches notifications to caregivers upon fall detection  
**Video Upload & Analysis** - Upload videos to analyze human activity and detect falls  
**Live Monitoring** - Real-time analytics dashboard for activity monitoring  
**Analytics Dashboard** - Comprehensive statistics and fall detection history  
**Contact Management** - Manage emergency contacts for instant notifications  
**User Authentication** - Secure login/signup system for protected access  

## Tech Stack

- **Backend:** Flask (Python)
- **Frontend:** HTML5, CSS3, JavaScript
- **AI/ML:** YOLOv8 (Object Detection)
- **Database:** MongoDB
- **Package Management:** pip

## Requirements

- Python 3.9+
- pip (Python Package Manager)
- Virtual Environment (recommended)

## Installation

### 1. Navigate to Project Directory

Open Command Prompt or PowerShell and navigate to your project folder:

```bash
cd fall detection
```

Or if you have the folder open in File Explorer, you can:
1. Hold `Shift` and right-click in the folder
2. Select "Open PowerShell window here" or "Open Command Prompt window here"

### 2. Create Virtual Environment

```bash
python -m venv myvenv
```

### 3. Activate Virtual Environment

**On Windows (PowerShell):**
```bash
.\myvenv\Scripts\Activate.ps1
```

**On Windows (CMD):**
```bash
myvenv\Scripts\activate.bat
```

**On macOS/Linux:**
```bash
source myvenv/bin/activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

## Running the Project

### Start the Flask Server

```bash
python app.py
```

The application will be available at:
```
http://localhost:5000
```

## Project Structure

```
smartfall/
├── app.py                      # Main Flask application
├── requirements.txt            # Project dependencies
├── yolov8s.pt                 # YOLOv8 pre-trained model
├── classes.txt                # YOLO class labels
├── README.md                  # Project documentation
│
├── templates/                 # HTML templates
│   ├── home.html             # Landing page
│   ├── about.html            # About page
│   ├── login.html            # Login page
│   ├── signup.html           # Sign up page
│   ├── upload.html           # Video upload page
│   ├── analytics.html        # Analytics dashboard
│   ├── dashboard.html        # User dashboard
│   ├── live.html             # Live monitoring page
│   ├── contact.html          # Contact management
│   └── footer.html           # Reusable footer component
│
├── static/                    # Static files
│   ├── footer.css            # Footer styles
│   ├── fall_logo.png         # Application logo
│   ├── alert.png             # Alert icon
│   ├── pose_icon.png         # Pose detection icon
│   └── live_icon.png         # Live monitoring icon
│
├── uploads/                   # User uploaded video directory
│
└── myvenv/                    # Virtual environment (auto-created)
    ├── Lib/
    ├── Scripts/
    └── Include/
```

## Key Pages & Features

### Public Pages
- **Home** (`/`) - Landing page with Learn More feature
- **About** (`/about`) - Information about SmartFall
- **Upload** (`/upload_page`) - Upload videos for analysis

### Authenticated Pages (Login Required)
- **Analytics** (`/analytics`) - Fall detection statistics
- **Dashboard** (`/dashboard`) - User dashboard with live detection analytics
- **Live Monitor** (`/live`) - Real-time monitoring feed
- **Contacts** (`/contact_page`) - Emergency contact management

### Authentication
- **Login** (`/login`) - User login
- **Signup** (`/signup`) - New user registration
- **Logout** (`/logout`) - Logout functionality

## Configuration

### Port Configuration
By default, the app runs on port 5000. To change:

Edit in `app.py`:
```python
if __name__ == '__main__':
    app.run(debug=True, port=5000)  # Change 5000 to your desired port
```

### Database Setup
Make sure MongoDB is installed and running. The app will automatically connect to the local MongoDB instance.

## Dependencies

Key Python packages (see `requirements.txt`):
- Flask - Web framework
- OpenCV (cv2) - Computer vision
- YOLOv8 - Object detection
- NumPy - Numerical computing
- Pillow - Image processing
- PyMongo - MongoDB driver
- Python-dotenv - Environment variables

## Usage

### For End Users
1. Navigate to the home page
2. Sign up for an account
3. Upload videos for fall detection analysis
4. Monitor live feeds from the dashboard
5. Manage emergency contacts

### For Developers
1. Ensure all dependencies are installed
2. Run `python app.py` to start the development server
3. Check Flask debug mode for development features
4. Modify templates in `templates/` folder
5. Update styles in `static/footer.css`

## Features Walkthrough

### Learn More Section
Click "Learn More" on the home page to expand the "Why Choose Our System?" section featuring three key features with smooth animation.

### Video Upload & Analysis
- Upload MP4 videos
- System analyzes with YOLOv8
- Real-time fall detection
- Instant notifications

### Live Monitoring
- Real-time camera feed analysis
- Detection status indicator
- Video evidence captured
- Automatic alert dispatch

### Analytics Dashboard
- Fall detection statistics
- Weekly/monthly trends
- Detection accuracy metrics
- Historical data

## Troubleshooting

### Virtual Environment Not Activating
Ensure you're running PowerShell as Administrator on Windows, or use CMD instead.

### Port Already in Use
Change the port number in `app.py` or kill the process using the port:
```bash
# Windows
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# macOS/Linux
lsof -i :5000
kill -9 <PID>
```

### Missing Dependencies
Reinstall all dependencies:
```bash
pip install --upgrade -r requirements.txt
```

### Database Connection Error
Ensure MongoDB is running:
```bash
# Windows
mongod

# macOS (with Homebrew)
brew services start mongodb-community
```

## Browser Compatibility

- Chrome (Recommended)
- Firefox
- Safari
- Edge
- Mobile browsers (iOS Safari, Chrome Mobile)

## Security Notes

- Use environment variables for sensitive data
- Change secret keys in production
- Enable HTTPS for production deployment
- Validate all user inputs
- Keep dependencies updated

## Future Enhancements

- [ ] Cloud deployment (AWS, Heroku)
- [ ] Mobile app (iOS/Android)
- [ ] Multi-camera support
- [ ] Advanced analytics reports
- [ ] SMS notifications
- [ ] Email integration
- [ ] Machine learning model improvements

## Support & Contacts

- **Email:** 25workproject123@gmail.com
- **Instagram:** [@detection_960](https://www.instagram.com/detection_960)
- **YouTube:** [@pro-267z](https://www.youtube.com/@pro-267z)

## License

This project is for educational and personal safety purposes.

## Version

**Current Version:** 1.0.0  
**Last Updated:** January 2026

---

**SmartFall** - Advanced AI-powered fall detection system for elderly care and safety monitoring.