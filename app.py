import os
import binascii
import logging
from datetime import datetime
from flask import Flask, request, jsonify
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import uid_generator_pb2
from GetPlayerPersonalShow_pb2 import GetPlayerPersonalShow

app = Flask(__name__)

# Configuration
API_TIMEOUT = 15  # seconds
MAX_RETRIES = 2
VERSION = "1.2.0"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load secrets from environment (recommended) or secret.py
try:
    KEY = os.getenv('AES_KEY', 'default_secret_key_here')[:16].encode()
    IV = os.getenv('AES_IV', 'default_iv_here')[:16].encode()
except Exception as e:
    logger.critical(f"Failed to load encryption keys: {str(e)}")
    raise

class APIError(Exception):
    """Custom exception for API errors"""
    pass

def create_protobuf(uid, request_type=1):
    """Create protobuf message"""
    message = uid_generator_pb2.uid_generator()
    message.akiru_ = uid
    message.aditya = request_type
    return message.SerializeToString()

def encrypt_data(data):
    """Encrypt data using AES-CBC"""
    try:
        cipher = AES.new(KEY, AES.MODE_CBC, IV)
        padded_data = pad(data, AES.block_size)
        return cipher.encrypt(padded_data)
    except Exception as e:
        logger.error(f"Encryption failed: {str(e)}")
        raise APIError("Encryption failed")

def get_api_endpoint(region):
    """Get the appropriate API endpoint based on region"""
    region = region.upper()
    endpoints = {
        "NA": "https://prod-na.hellokitty.com",
        "EU": "https://prod-eu.hellokitty.com",
        "AS": "https://prod-as.hellokitty.com",
        "IND": "https://prod-in.hellokitty.com",
        "BR": "https://prod-br.hellokitty.com",
        "US": "https://prod-us.hellokitty.com",
        "SAC": "https://prod-sac.hellokitty.com"
    }
    return endpoints.get(region, "https://prod.hellokitty.com")

def get_jwt_token(region):
    """Retrieve JWT token for authentication"""
    credentials = {
        "IND": ("3942040791", "EDD92B8948F4453F544C9432DFB4996D02B4054379A0EE083D8459737C50800B"),
        "NA": ("3949487129", "67D4C358CCE73BFF8B295B99111D6BDF7D67E149E2C6FD90F28BE45B7C00CAA6"),
        "BR": ("3949487129", "67D4C358CCE73BFF8B295B99111D6BDF7D67E149E2C6FD90F28BE45B7C00CAA6"),
        "SAC": ("3949487129", "67D4C358CCE73BFF8B295B99111D6BDF7D67E149E2C6FD90F28BE45B7C00CAA6"),
        "US": ("3949487129", "67D4C358CCE73BFF8B295B99111D6BDF7D67E149E2C6FD90F28BE45B7C00CAA6"),
    }
    
    uid, password = credentials.get(region.upper(), credentials["NA"])
    url = f"https://genjwt.vercel.app/api/get_jwt?type=4&guest_uid={uid}&guest_password={password}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data.get('success', False):
            raise APIError("JWT service returned unsuccessful response")
            
        token = data.get('BearerAuth')
        if not token or len(token.split('.')) != 3:
            raise APIError("Invalid JWT token format")
            
        return {
            'token': token,
            'serverUrl': data.get('serverUrl', '')
        }
    except Exception as e:
        logger.error(f"JWT token request failed: {str(e)}")
        raise APIError("Failed to obtain authentication token")

def make_game_api_request(api, token, encrypted_data):
    """Make request to game server with retry logic"""
    headers = {
        'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)',
        'Authorization': f'Bearer {token}',
        'X-Unity-Version': '2018.4.11f1',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.post(
                f"{api}/GetPlayerPersonalShow",
                headers=headers,
                data=encrypted_data,
                timeout=API_TIMEOUT
            )
            response.raise_for_status()
            
            if not response.content:
                raise APIError("Empty response from game server")
                
            return response.content
            
        except requests.Timeout:
            if attempt == MAX_RETRIES:
                raise APIError("Game server timeout after multiple attempts")
            logger.warning(f"Timeout occurred, retrying ({attempt + 1}/{MAX_RETRIES})")
            
        except requests.RequestException as e:
            raise APIError(f"Game server request failed: {str(e)}")

def parse_game_response(response_data):
    """Parse the binary game server response"""
    try:
        users = GetPlayerPersonalShow()
        users.ParseFromString(response_data)
        return users
    except Exception as e:
        logger.error(f"Failed to parse game response: {str(e)}")
        raise APIError("Failed to decode game server response")

def build_player_info(player):
    """Build player info dictionary from protobuf"""
    info = {
        'user_id': player.user_id,
        'username': player.username,
        'level': player.level,
        'rank': player.rank,
        'clan_id': player.clan_id,
        'clan_tag': player.clan_tag,
        'matches_played': player.matches_played,
        'kills': player.kills,
        'skill_rating': player.skill_rating,
        'headshot_percentage': player.headshot_percentage,
        'last_login': player.last_login,
    }
    
    if player.HasField("subscription"):
        info['subscription'] = {
            'tier': player.subscription.tier,
            'renewal_period': player.subscription.renewal_period
        }
        
    if player.achievements:
        info['achievements'] = [{
            'id': a.achievement_id,
            'progress': a.progress
        } for a in player.achievements]
        
    return info

@app.route('/player-info', methods=['GET'])
def player_info():
    """Main endpoint for player information"""
    start_time = datetime.now()
    uid = request.args.get('uid')
    region = request.args.get('region', 'NA')
    
    if not uid:
        return jsonify({"error": "UID parameter is required"}), 400
        
    try:
        uid_int = int(uid)
    except ValueError:
        return jsonify({"error": "UID must be a number"}), 400
    
    try:
        # Step 1: Get authentication token
        jwt_data = get_jwt_token(region)
        api = jwt_data.get('serverUrl') or get_api_endpoint(region)
        token = jwt_data['token']
        
        # Step 2: Prepare request data
        protobuf_data = create_protobuf(uid_int)
        encrypted_data = encrypt_data(protobuf_data)
        
        # Step 3: Make API request
        response_data = make_game_api_request(api, token, encrypted_data)
        
        # Step 4: Parse response
        game_data = parse_game_response(response_data)
        
        # Step 5: Build result
        result = {
            'success': True,
            'version': VERSION,
            'processing_time': str(datetime.now() - start_time),
            'player': None,
            'clan': None
        }
        
        if game_data.players:
            result['player'] = build_player_info(game_data.players[0])
            
        if game_data.clans:
            result['clan'] = {
                'id': game_data.clans[0].clan_id,
                'member_count': game_data.clans[0].member_count
            }
            
        return jsonify(result)
        
    except APIError as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'version': VERSION
        }), 502
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({
            'success': False,
            'error': "Internal server error",
            'version': VERSION
        }), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
