from flask import Flask, jsonify, request
from flask_cors import CORS
import anthropic
import requests
import base64
import json
import os

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
CORS(app)

MTA_API_KEY = 'Dd58ed0f-82c5-48a2-b01f-4d2d6a65e608'

# Initialize Claude client
client = None
if os.environ.get('ANTHROPIC_API_KEY'):
    client = anthropic.Anthropic()

ANALYSIS_PROMPT = """Analyze this NYC traffic camera image for snow conditions that could block bus stop access.

Look carefully for:
1. Snow mounds or banks along the curb that would prevent passengers from boarding a bus
2. Accumulated snow blocking the sidewalk near where a bus stop might be
3. Clear vs obstructed pathway from sidewalk to street

Also check if the camera view is obscured (lens covered, too dark to see, heavy glare).

IMPORTANT: Only mark as "blocked" if you can clearly see snow accumulation that would physically prevent someone from accessing a bus. Wet pavement or light snow dusting is NOT blocked.

Respond with ONLY valid JSON (no other text):
{
  "status": "clear" | "blocked" | "obscured",
  "confidence": 0.0 to 1.0,
  "reason": "One sentence explaining what you see",
  "snow_visible": true/false,
  "blockage_location": "curb" | "sidewalk" | "none" | "unknown"
}"""


@app.route('/api/health', methods=['GET'])
def health():
    has_key = bool(os.environ.get('ANTHROPIC_API_KEY'))
    return jsonify({
        "status": "ok",
        "ai_enabled": has_key
    })


@app.route('/api/cameras', methods=['GET'])
def get_cameras():
    """Proxy for NYCTMC cameras API"""
    try:
        res = requests.get('https://webcams.nyctmc.org/api/cameras', timeout=30)
        return jsonify(res.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/bus-stops', methods=['GET'])
def get_bus_stops():
    """Proxy for MTA bus stops API"""
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    radius = request.args.get('radius', '100')

    if not lat or not lon:
        return jsonify({"error": "lat and lon required"}), 400

    try:
        url = f'http://bustime.mta.info/api/where/stops-for-location.json?key={MTA_API_KEY}&lat={lat}&lon={lon}&radius={radius}'
        res = requests.get(url, timeout=10)
        data = res.json()
        return jsonify(data.get('data', {}).get('stops', []))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/snowplow', methods=['GET'])
def get_snowplow():
    """Proxy for NYC SnowPlow API"""
    limit = request.args.get('limit', '100')
    try:
        url = f'https://data.cityofnewyork.us/resource/rmhc-afj9.json?$limit={limit}&$order=last_visited%20DESC'
        res = requests.get(url, timeout=10)
        return jsonify(res.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/analyze', methods=['POST'])
def analyze_image():
    """Analyze camera image using Claude Vision"""
    data = request.json
    image_url = data.get('imageUrl', '')
    camera_name = data.get('name', 'Unknown')

    # Check if AI is enabled
    if not client:
        return jsonify({
            "status": "clear",
            "confidence": 0.0,
            "reason": "AI not configured - add ANTHROPIC_API_KEY to .env file",
            "snow_visible": False,
            "ai_enabled": False
        })

    try:
        # Fetch image and convert to base64
        img_response = requests.get(image_url, timeout=10)
        img_response.raise_for_status()
        image_base64 = base64.standard_b64encode(img_response.content).decode("utf-8")

        # Call Claude Vision API
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_base64
                        }
                    },
                    {
                        "type": "text",
                        "text": ANALYSIS_PROMPT
                    }
                ]
            }]
        )

        # Parse response
        result_text = response.content[0].text.strip()

        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = {
                    "status": "obscured",
                    "confidence": 0.5,
                    "reason": f"Could not parse AI response",
                    "snow_visible": False
                }

        result['ai_enabled'] = True
        print(f"[AI] {camera_name}: {result['status']} ({result.get('confidence', 0):.0%}) - {result.get('reason', 'N/A')}")

        return jsonify(result)

    except anthropic.AuthenticationError as e:
        print(f"[AI ERROR] Authentication failed: {e}")
        return jsonify({
            "status": "clear",
            "confidence": 0.0,
            "reason": "Invalid API key - check your ANTHROPIC_API_KEY",
            "snow_visible": False,
            "ai_enabled": False
        })
    except Exception as e:
        print(f"[AI ERROR] {camera_name}: {e}")
        return jsonify({
            "status": "obscured",
            "confidence": 0.0,
            "reason": f"Analysis error: {str(e)[:50]}",
            "snow_visible": False,
            "ai_enabled": True
        })


if __name__ == '__main__':
    print("=" * 50)
    print("  SNOWED-IN BUS STOP - Backend Server")
    print("=" * 50)

    if os.environ.get('ANTHROPIC_API_KEY'):
        print("  AI Status: ENABLED (Claude Vision)")
    else:
        print("  AI Status: DISABLED")
        print("  Add ANTHROPIC_API_KEY to .env file to enable")

    print()
    print("  Endpoints:")
    print("    GET  /api/cameras     - NYC traffic cameras")
    print("    GET  /api/bus-stops   - MTA bus stops")
    print("    GET  /api/snowplow    - NYC plow history")
    print("    POST /api/analyze     - AI image analysis")
    print("=" * 50)
    print("  Running on http://localhost:5001")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5001, debug=True)
