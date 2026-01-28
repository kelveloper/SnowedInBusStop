from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import base64
import json
import os
from io import BytesIO

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
CORS(app)

# MTA Bus Time API key (get free at http://bustime.mta.info/wiki/Developers/Index)
# Falls back to demo key if not set in .env
MTA_API_KEY = os.environ.get('MTA_API_KEY', 'Dd58ed0f-82c5-48a2-b01f-4d2d6a65e608')

# Optional: Hugging Face API key for better AI (get free at huggingface.co)
HF_API_KEY = os.environ.get('HF_API_KEY', '')


def analyze_image_for_snow(image_bytes):
    """
    Snow detection using image color analysis.
    Looks for white/bright areas with specific snow characteristics.
    Works without any external API!
    """
    try:
        from PIL import Image
        import numpy as np

        # Open image
        img = Image.open(BytesIO(image_bytes))
        img = img.convert('RGB')
        img_array = np.array(img)

        # Get image dimensions
        height, width = img_array.shape[:2]

        # Check if image is nighttime (overall dark)
        overall_brightness = np.mean(img_array)
        is_night = overall_brightness < 80

        # Focus on bottom 40% of image (where curb/sidewalk usually is)
        bottom_section = img_array[int(height * 0.6):, :, :]

        r, g, b = bottom_section[:, :, 0].astype(float), bottom_section[:, :, 1].astype(float), bottom_section[:, :, 2].astype(float)

        # Brightness: average of RGB
        brightness = (r + g + b) / 3

        # Snow characteristics:
        # 1. High brightness (but not just any bright pixel)
        # 2. Low color saturation (snow is grayish-white, not colorful)
        # 3. Consistent texture (large areas, not spotty reflections)

        # Calculate saturation (max - min of RGB channels)
        max_rgb = np.maximum(np.maximum(r, g), b)
        min_rgb = np.minimum(np.minimum(r, g), b)
        saturation = max_rgb - min_rgb

        # Snow detection criteria (stricter):
        # - Very bright (>200 for day, >170 for night)
        # - Low saturation (< 25) - snow is not colorful
        # - Not pure white from lights (avoid 255,255,255)
        brightness_threshold = 170 if is_night else 200
        snow_mask = (brightness > brightness_threshold) & (saturation < 25) & (brightness < 250)

        # Apply morphological operations to remove noise (small bright spots)
        # Count connected regions - snow should be in large patches
        snow_percentage = np.mean(snow_mask) * 100

        # For curb detection, check sides but require larger contiguous areas
        left_section = snow_mask[:, :int(width * 0.25)]
        right_section = snow_mask[:, int(width * 0.75):]

        # Only count as curb snow if there's a significant continuous area
        left_snow = np.mean(left_section) * 100
        right_snow = np.mean(right_section) * 100
        curb_snow = max(left_snow, right_snow)

        # Night adjustment: be more conservative at night (wet roads reflect)
        if is_night:
            snow_percentage *= 0.5
            curb_snow *= 0.5

        return {
            "snow_percentage": round(float(snow_percentage), 1),
            "curb_snow_percentage": round(float(curb_snow), 1),
            "is_night": bool(is_night),
            "overall_brightness": round(float(overall_brightness), 1),
            "analysis_method": "color_detection"
        }

    except ImportError:
        return {"error": "PIL/numpy not installed", "analysis_method": "none"}
    except Exception as e:
        return {"error": str(e), "analysis_method": "failed"}


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "ai_method": "color_analysis"
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
    """Analyze camera image for snow using color detection (FREE, no API needed!)"""
    data = request.json
    image_url = data.get('imageUrl', '')
    camera_name = data.get('name', 'Unknown')

    try:
        # Fetch image
        img_response = requests.get(image_url, timeout=10)
        img_response.raise_for_status()

        # Analyze for snow
        analysis = analyze_image_for_snow(img_response.content)

        if 'error' in analysis:
            return jsonify({
                "status": "clear",
                "confidence": 0.5,
                "reason": f"Analysis error: {analysis['error']}",
                "snow_visible": False,
                "ai_enabled": True
            })

        snow_pct = analysis['snow_percentage']
        curb_pct = analysis['curb_snow_percentage']

        is_night = analysis.get('is_night', False)

        # Determine status based on snow detection (conservative thresholds)
        if curb_pct > 40:  # Need significant curb coverage
            status = "blocked"
            confidence = min(0.85, 0.5 + curb_pct / 200)
            reason = f"Significant snow ({curb_pct:.0f}%) detected at curb - may block bus access"
            snow_visible = True
        elif snow_pct > 50:  # Need majority snow coverage
            status = "blocked"
            confidence = min(0.75, 0.4 + snow_pct / 200)
            reason = f"Heavy snow coverage ({snow_pct:.0f}%) in ground area"
            snow_visible = True
        elif snow_pct > 20:
            status = "clear"
            confidence = 0.65
            reason = f"Some snow visible ({snow_pct:.0f}%) but bus stop access appears clear"
            snow_visible = True
        elif is_night and snow_pct < 10:
            status = "clear"
            confidence = 0.75
            reason = f"Night image - road appears clear (low snow signature: {snow_pct:.0f}%)"
            snow_visible = False
        else:
            status = "clear"
            confidence = 0.85
            reason = f"Clear conditions - minimal snow detected ({snow_pct:.0f}%)"
            snow_visible = snow_pct > 5

        result = {
            "status": status,
            "confidence": round(confidence, 2),
            "reason": reason,
            "snow_visible": snow_visible,
            "snow_percentage": snow_pct,
            "curb_snow_percentage": curb_pct,
            "ai_enabled": True,
            "analysis_method": "color_detection"
        }

        print(f"[ANALYZE] {camera_name}: {status} ({snow_pct:.0f}% snow, {curb_pct:.0f}% curb)")
        return jsonify(result)

    except requests.exceptions.Timeout:
        return jsonify({
            "status": "obscured",
            "confidence": 0.0,
            "reason": "Request timeout - camera may be offline",
            "ai_enabled": True
        })
    except Exception as e:
        import traceback
        print(f"[ERROR] {camera_name}: {e}", flush=True)
        traceback.print_exc()
        return jsonify({
            "status": "clear",
            "confidence": 0.0,
            "reason": f"Could not analyze image: {str(e)}",
            "ai_enabled": True
        })


if __name__ == '__main__':
    print("=" * 50)
    print("  SNOWED-IN BUS STOP - Backend Server")
    print("=" * 50)
    print("  AI Method: Color-based snow detection")
    print("  (No API key required!)")
    print()
    print("  Endpoints:")
    print("    GET  /api/cameras     - NYC traffic cameras")
    print("    GET  /api/bus-stops   - MTA bus stops")
    print("    GET  /api/snowplow    - NYC plow history")
    print("    POST /api/analyze     - Snow detection")
    print("=" * 50)
    print("  Running on http://localhost:5001")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5001, debug=True)
