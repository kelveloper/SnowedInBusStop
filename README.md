# Snowed-In Bus Stop

A real-time monitoring system that uses NYC traffic cameras and AI to detect snow-blocked bus stops, helping the MTA prioritize snow removal efforts.

## Features

- **Live Camera Feed**: Displays NYC traffic cameras near MTA bus stops
- **AI Snow Detection**: Color-based image analysis to detect snow accumulation
- **Interactive Map**: Leaflet-powered map showing all monitored locations
- **Snowplow Tracking**: Cross-references NYC snowplow activity data
- **Visual Annotations**: Red box overlays highlighting blocked areas for MTA employees

## APIs Used

| API | Purpose | Key Required |
|-----|---------|--------------|
| [NYCTMC Webcams](https://webcams.nyctmc.org/api/cameras) | Live traffic camera feeds | No |
| [MTA Bus Time](http://bustime.mta.info/) | Bus stop locations | Yes (free) |
| [NYC OpenData - SnowPlow](https://data.cityofnewyork.us/resource/rmhc-afj9.json) | Plow activity history | No |

## Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/kelveloper/SnowedInBusStop.git
cd SnowedInBusStop
```

### 2. Set up environment
```bash
# Copy the environment template
cp .env.example .env

# Edit .env with your API keys (see below)
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the server
```bash
python3 server.py
```

### 5. Open the app
Open `app.html` in your browser or serve it locally:
```bash
# Option 1: Direct file
open app.html

# Option 2: Local server (recommended)
python3 -m http.server 8080
# Then visit http://localhost:8080/app.html
```

## API Keys Setup

### MTA Bus Time API (Required)
1. Go to [MTA Bus Time Developer Portal](http://bustime.mta.info/wiki/Developers/Index)
2. Register for a free API key
3. Add to your `.env` file:
   ```
   MTA_API_KEY=your_key_here
   ```

**Note**: A demo key is currently hardcoded for testing. Replace with your own for production use.

### Hugging Face API (Optional)
For enhanced AI analysis (not currently used):
1. Create account at [huggingface.co](https://huggingface.co)
2. Generate API token in settings
3. Add to your `.env` file:
   ```
   HF_API_KEY=your_token_here
   ```

## Project Structure

```
SnowedInBusStop/
├── app.html          # Main frontend application
├── server.py         # Flask backend server
├── requirements.txt  # Python dependencies
├── .env.example      # Environment template
├── .env              # Your API keys (git-ignored)
└── README.md         # This file
```

## How It Works

1. **Camera Discovery**: Fetches all NYC traffic cameras from NYCTMC API
2. **Bus Stop Matching**: For each camera, queries MTA API for nearby bus stops (100m radius)
3. **Snow Detection**: Analyzes camera images using color-based detection:
   - Looks for high brightness (>200) with low saturation (<25)
   - Focuses on bottom 40% of image (curb/sidewalk area)
   - Adjusts for nighttime conditions
4. **Status Classification**:
   - **Blocked**: >40% curb snow or >50% ground snow
   - **Clear**: <20% snow detected
   - **Obscured**: Camera unavailable or analysis failed

## Demo Mode

For presentations, the app includes demo features:
- **"View Demo: Blocked Bus Stop"** button shows annotated example
- **"Mark as Blocked (Demo)"** button in camera modal
- **Father Capodanno Blvd @ Sands LN** is auto-marked as blocked during analysis

## Tech Stack

- **Frontend**: HTML, CSS, JavaScript, Leaflet.js
- **Backend**: Python, Flask, Flask-CORS
- **Image Analysis**: PIL (Pillow), NumPy
- **APIs**: NYCTMC, MTA Bus Time, NYC OpenData

## Team

Built for NYC Hackathon by:
- Jonel
- Carolina
- Jawad
- Dawn
- Kelvin

## License

MIT License
