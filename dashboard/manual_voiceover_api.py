"""Manual voiceover API endpoint for multi-character script input"""

import asyncio
import threading
import aiohttp
import re
import time
from flask import request, jsonify
from flask_login import login_required, current_user
from core.logger import logger
from core.database import db

def create_manual_voiceover_api():
    """Create voiceover from manual script with multi-character support"""
    try:
        data = request.get_json()
        script = data.get('script')
        voice_selections = data.get('voiceSelections', {})
        voice_method = data.get('voiceMethod', 'elevenlabs')  # 'elevenlabs' or 'kokoro'
        
        if not all([script, voice_selections]):
            return jsonify({'success': False, 'error': 'Missing required parameters: script and voiceSelections'})
        
        # Get current user's Discord ID for voice generation
        user_id = getattr(current_user, 'discord_id', None)
        if not user_id:
            return jsonify({'success': False, 'error': 'User Discord ID not found'})
        
        # Generate the folder URL synchronously first
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            folder_url = loop.run_until_complete(
                generate_manual_voice_over_via_service(script, voice_selections, str(user_id))
            )
            loop.close()
            
            if folder_url:
                return jsonify({
                    'success': True,
                    'message': f'Multi-character voiceover generation started. Audio files will be available in Google Drive.',
                    'folder_url': folder_url
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Failed to create Google Drive folder'
                })
                
        except Exception as e:
            loop.close()
            logger.error(f"Error creating folder: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'Failed to start voiceover generation: {str(e)}'
            })
    
    except Exception as e:
        logger.error(f"Error in create_manual_voiceover_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

async def generate_manual_voice_over_via_service(script: str, voice_selections: dict, user_id: str):
    """Generate voice over using your external voice service (same as Trend Discovery)"""
    try:
        logger.info(f"Starting manual voice over generation for user {user_id}")
        
        # Create Google Drive folder (reusing existing logic)
        folder_name = f"Manual_Script_{int(time.time())}"
        
        # Get Drive service and create folder
        drive_service = db.get_drive_service_sync()
        if not drive_service:
            logger.error("Failed to get Google Drive service")
            return None
            
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
        folder_id = folder.get('id')
        folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
        logger.info(f"Created Google Drive folder: {folder_url}")
        
        # Split script into segments using the same logic as voice service
        segments = split_script_into_segments(script)
        logger.info(f"Found {len(segments)} segment(s) in the script.")
        
        # Send to your external voice service (same as Trend Discovery)
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "folder_id": folder_id,
                    "segments": segments,
                    "voice_selections": voice_selections,
                    "user_id": user_id,
                    "voice_service": voice_method  # Use the selected voice service
                }
                
                # Use your server's IP address (same as in ai_utils.py)
                url = "http://157.180.0.71:8081/api/process-audio"
                
                async with session.post(url, json=data, timeout=60) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Successfully sent to voice service: {result}")
                    else:
                        error_text = await response.text()
                        logger.error(f"Error from voice service: {error_text}")
        except Exception as server_error:
            logger.error(f"Error communicating with voice server: {str(server_error)}")
        
        # Return the folder URL immediately while audio generation continues in background
        return folder_url
        
    except Exception as e:
        logger.error(f"Error in generate_manual_voice_over_via_service: {str(e)}", exc_info=True)
        return None

def split_script_into_segments(script):
    """Split script into segments using same logic as voice service"""
    # Clean the script to remove segment breaks
    script = script.replace("=== SEGMENT BREAK ===", "").strip()
    
    # Try the segment header pattern
    segment_pattern = r'#\s*(?:Segment|SEGMENT|Section|SECTION)\s*(?:\d+)?(?::|-)?\s*([^\n]+)(?:\n+)([\s\S]*?)(?=\n+#\s*(?:Segment|SEGMENT|Section|SECTION)|$)'
    segments = []
    
    for match in re.finditer(segment_pattern, script):
        title = match.group(1).strip()
        content = match.group(2).strip()
        segments.append({"title": title, "content": content})
    
    # If no segments found with the original pattern, try the timestamp pattern
    if not segments:
        segment_pattern = r"(?m)^(?P<header>.+\(\d+(?::\d{2}){1,2}\s*-\s*\d+(?::\d{2}){1,2},\s*Duration:\s*\d+(?::\d{2}){1,2}\))\s*\n"
        matches = list(re.finditer(segment_pattern, script))
        
        if matches:
            for i, match in enumerate(matches):
                header = match.group("header").strip()
                start_index = match.end()
                end_index = matches[i + 1].start() if i + 1 < len(matches) else len(script)
                content = script[start_index:end_index].strip()
                segments.append({"title": header, "content": content})
    
    # If still no segments found, treat the entire script as one segment
    if not segments:
        segments.append({"title": "Manual Script", "content": script})
    
    return segments
