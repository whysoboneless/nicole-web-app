from flask import Blueprint, request, jsonify, current_app
from core.auth import login_required, get_current_user
import logging
import asyncio
import threading
import json
import sys
import os

# Import core database which has proper sync wrappers for Flask
from core.database import Database

# Initialize database
db = Database()

# Set up clean logging
from core.logger import success, error, warning, progress, api_call, db_operation
logger = logging.getLogger(__name__)

# Create Blueprint
content_studio_bp = Blueprint('content_studio', __name__)

# Content Studio API Endpoints

@content_studio_bp.route('/api/get-example-titles', methods=['POST'])
@login_required
def get_example_titles_api():
    """Get example titles for a specific series and theme"""
    try:
        data = request.get_json()
        group_id = data.get('groupId')
        series_name = data.get('seriesName')
        theme_name = data.get('themeName')
        
        if not all([group_id, series_name, theme_name]):
            return jsonify({'success': False, 'error': 'Missing required parameters'})
        
        # Use sync version from core database
        example_titles = db.get_example_titles_sync(group_id, series_name, theme_name)
        
        if example_titles:
            return jsonify({
                'success': True,
                'exampleTitles': example_titles
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No example titles found for this series and theme'
            })
    
    except Exception as e:
        logger.error(f"Error in get_example_titles_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@content_studio_bp.route('/api/generate-titles', methods=['POST'])
@login_required
def generate_titles_api():
    """Generate new titles based on series, theme, and examples"""
    try:
        data = request.get_json()
        series_data = data.get('seriesData')
        theme_data = data.get('themeData')
        example_titles = data.get('exampleTitles')
        
        if not all([series_data, theme_data, example_titles]):
            return jsonify({'success': False, 'error': 'Missing required parameters'})
        
        # Import the function from ai_utils
        from utils_dir.ai_utils import generate_video_titles
        
        # Run async function in a separate thread with proper event loop handling
        import asyncio
        import threading
        import queue
        
        result_queue = queue.Queue()
        
        def run_async_in_thread():
            try:
                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(generate_video_titles(series_data, theme_data, example_titles))
                    result_queue.put(('success', result))
                except Exception as e:
                    logger.error(f"Error in generate_video_titles: {e}")
                    result_queue.put(('error', str(e)))
                finally:
                    # Clean up the loop
                    try:
                        loop.close()
                    except:
                        pass
            except Exception as e:
                logger.error(f"Error creating event loop: {e}")
                result_queue.put(('error', str(e)))
        
        # Start the thread
        thread = threading.Thread(target=run_async_in_thread)
        thread.start()
        thread.join(timeout=120)  # 2 minute timeout
        
        if thread.is_alive():
            logger.error("generate_video_titles timed out")
            generated_titles = None
        else:
            try:
                status, result = result_queue.get_nowait()
                if status == 'success':
                    generated_titles = result
                else:
                    logger.error(f"generate_video_titles failed: {result}")
                    generated_titles = None
            except queue.Empty:
                logger.error("No result from generate_video_titles")
                generated_titles = None
        
        if generated_titles:
            return jsonify({
                'success': True,
                'titles': generated_titles
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to generate titles'
            })
    
    except Exception as e:
        logger.error(f"Error in generate_titles_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@content_studio_bp.route('/api/create-script-breakdown', methods=['POST'])
@login_required
def create_script_breakdown_api():
    """Create script breakdown for a video (following Discord bot workflow)"""
    try:
        data = request.get_json()
        group_id = data.get('groupId')
        series_name = data.get('seriesName')
        theme_name = data.get('themeName')
        title = data.get('title')
        
        if not all([group_id, series_name, theme_name, title]):
            return jsonify({'success': False, 'error': 'Missing required parameters'})
        
        current_user = get_current_user()
        
        def run_background_task():
            """EXACT copy of Discord bot breakdown_script function"""
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                from utils.ai_utils import breakdown_script
                from bson import ObjectId
                
                # Convert group_id to ObjectId if needed
                if isinstance(group_id, str):
                    object_id = ObjectId(group_id)
                else:
                    object_id = group_id
                
                progress(f"Script breakdown: {series_name} - {theme_name}")
                
                # STEP 1: Check for optimized guidelines first (EXACT Discord bot logic)
                try:
                    optimized_guidelines = db.get_optimized_guidelines_sync(object_id, series_name, theme_name)
                    if optimized_guidelines:
                        success(f"Using optimized guidelines: {series_name} - {theme_name}")
                        script_breakdown = optimized_guidelines
                        loop.close()
                        return {'success': True, 'script_breakdown': script_breakdown}
                except:
                    pass  # Method might not exist, continue to next check
                
                # STEP 2: Check for existing breakdown (now using correct core database method)
                existing_breakdown = db.get_script_breakdown_sync(object_id, series_name, theme_name)

                # Handle different database structures - check for actual script_breakdown field
                if existing_breakdown and existing_breakdown.get('script_breakdown'):
                    script_breakdown = existing_breakdown['script_breakdown']
                    success(f"Using cached breakdown: {series_name} - {theme_name}")
                    
                    # Also get the doc URL if it exists
                    doc_url = None
                    if 'script_breakdown_doc_url' in existing_breakdown:
                        doc_url = existing_breakdown['script_breakdown_doc_url']
                    
                    loop.close()
                    return {
                        'success': True, 
                        'script_breakdown': script_breakdown,
                        'doc_url': doc_url
                    }
                elif existing_breakdown and existing_breakdown.get('plot_outline'):
                    warning("Found plot outline, not script breakdown - generating new")
                    existing_breakdown = None  # Force new generation
                
                if not existing_breakdown or not existing_breakdown.get('script_breakdown'):
                    progress("Generating new script breakdown")
                    # Generate new script breakdown here (using sync methods)
                    video_ids = db.get_top_video_urls_sync(object_id, series_name, theme_name, limit=3)
                    db_operation(f"Found {len(video_ids)} videos", "success")
                    
                    if not video_ids:
                        error("No videos found for series/theme")
                        return {'error': 'No videos found for this series and theme.'}

                    transcripts = []
                    video_durations = []
                    video_titles = []
                    video_descriptions = []
                    # Keep searching beyond initial list until we collect enough transcripts (EXACT Discord bot logic)
                    required_count = 3
                    collected = 0
                    checked = set()
                    queue = list(video_ids)
                    
                    from core.youtube_service import YouTubeService
                    youtube_service = YouTubeService()
                    
                    while queue and collected < required_count:
                        video_id = queue.pop(0)
                        if not video_id or video_id in checked:
                            continue
                        checked.add(video_id)
                        transcript = youtube_service.get_video_transcript_sync(video_id)
                        if transcript:
                            transcripts.append(transcript)
                            video_duration = youtube_service.get_video_duration_sync(video_id)
                            video_durations.append(video_duration)
                            video_info = youtube_service.get_video_info_sync(video_id)
                            video_titles.append(video_info.get('title', ''))
                            video_descriptions.append(video_info.get('description', ''))
                            collected += 1
                        else:
                            # Discover more candidates from DB if available (using sync methods)
                            try:
                                more = db.get_top_video_urls_sync(object_id, series_name, theme_name, limit=20)
                                for vid in more:
                                    if vid not in checked:
                                        queue.append(vid)
                            except Exception:
                                pass

                    progress(f"Processing {len(transcripts)} transcripts")

                    if not transcripts:
                        error("No transcripts available")
                        return {'error': 'Failed to retrieve transcripts for the videos.'}

                    api_call("Claude AI script analysis")
                    response = loop.run_until_complete(
                        breakdown_script(series_name, theme_name, transcripts, video_durations, video_titles, video_descriptions)
                    )
                    try:
                        response_json = json.loads(response)
                        script_breakdown = response_json.get('script_breakdown')
                        is_clip_reactive = response_json.get('is_clip_reactive') == "true"
                        api_call("Claude AI script analysis", "success")
                    except json.JSONDecodeError:
                        error("AI response decode failed")
                        script_breakdown = response
                        is_clip_reactive = False
                    
                    success("Script breakdown generated")
                    
                    safe_series_name = series_name.replace(" ", "_")
                    safe_theme_name = theme_name.replace(" ", "_")
                    
                    db.save_script_breakdown_sync(
                        object_id, 
                        safe_series_name, 
                        safe_theme_name, 
                        script_breakdown,
                        script_breakdown  # Use the same content for guidelines
                    )
                    db_operation("Script breakdown saved", "success")

                # Create or update Google Doc with the script breakdown (EXACT Discord bot logic)
                doc_url = None
                if script_breakdown:
                    from services.google_docs_service import create_google_doc
                    doc_url = loop.run_until_complete(
                        create_google_doc(
                            f"Script Breakdown: {series_name} - {theme_name}", 
                            script_breakdown,
                            str(object_id)
                        )
                    )
                    
                    if doc_url:
                        # Save the doc URL to the database
                        loop.run_until_complete(
                            db.update_script_breakdown_doc_url(
                                object_id,
                                series_name,
                                theme_name,
                                doc_url
                            )
                        )
                        success("Google Doc created")
                    else:
                        warning("Google Doc creation failed")
                
                loop.close()
                return {
                    'success': True, 
                    'script_breakdown': script_breakdown,
                    'doc_url': doc_url
                }
                
            except Exception as e:
                logger.error(f"Error in breakdown_script: {str(e)}", exc_info=True)
                import traceback
                traceback.print_exc()
                return {'error': str(e)}
        
        # Run in background thread
        thread = threading.Thread(target=run_background_task)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Script breakdown started. This may take a few minutes.'
        })
    
    except Exception as e:
        logger.error(f"Error in create_script_breakdown_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@content_studio_bp.route('/api/create-plot-outline', methods=['POST'])
@login_required
def create_plot_outline_api():
    """Create plot outline based on script breakdown"""
    try:
        data = request.get_json()
        group_id = data.get('groupId')
        series_name = data.get('seriesName')
        theme_name = data.get('themeName')
        title = data.get('title')
        video_length = data.get('videoLength', 30)  # Default 30 minutes
        
        if not all([group_id, series_name, theme_name, title]):
            return jsonify({'success': False, 'error': 'Missing required parameters'})
        
        def run_background_task():
            """Generate plot outline matching Discord bot workflow"""
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                from utils_dir.ai_utils import generate_plot_outline
                from bson import ObjectId
                
                # Convert group_id to ObjectId if needed
                if isinstance(group_id, str):
                    object_id = ObjectId(group_id)
                else:
                    object_id = group_id
                
                # Get script breakdown from database
                script_breakdown_data = db.get_script_breakdown_sync(object_id, series_name, theme_name)
                
                if not script_breakdown_data:
                    return {'error': 'Script breakdown not found. Please generate script breakdown first.'}
                
                # Handle the JSON wrapper format
                script_breakdown_raw = script_breakdown_data.get('script_breakdown') or script_breakdown_data.get('guidelines')
                
                if not script_breakdown_raw:
                    return {'error': 'Script breakdown content not found.'}
                
                # Parse JSON if it's wrapped
                try:
                    if script_breakdown_raw.startswith('{"is_clip_reactive"'):
                        import json
                        parsed = json.loads(script_breakdown_raw)
                        script_breakdown = parsed.get('script_breakdown', script_breakdown_raw)
                    else:
                        script_breakdown = script_breakdown_raw
                except:
                    script_breakdown = script_breakdown_raw
                
                # Create series and theme objects matching Discord bot format
                series = {'name': series_name}
                theme = {'name': theme_name}
                
                # Generate plot outline
                plot_outline = loop.run_until_complete(
                    generate_plot_outline(title, script_breakdown, series, theme, video_length)
                )
                
                if plot_outline:
                    # Save to database - create Google Doc
                    from services.google_docs_service import create_google_doc
                    
                    doc_url = loop.run_until_complete(
                        create_google_doc(
                            f"Plot Outline: {series_name} - {theme_name} - {title}",
                            plot_outline,
                            str(object_id)
                        )
                    )
                    
                    if doc_url:
                        # Save plot outline and doc URL to database
                        safe_series_name = series_name.replace(" ", "_")
                        safe_theme_name = theme_name.replace(" ", "_")
                        
                        db.save_plot_outline_sync(object_id, safe_series_name, safe_theme_name, plot_outline, doc_url)
                        
                        result = {'success': True, 'plotOutline': doc_url, 'content': plot_outline}
                    else:
                        result = {'success': True, 'plotOutline': plot_outline, 'content': plot_outline}
                else:
                    result = {'error': 'Failed to generate plot outline'}
                
                loop.close()
                return result
                
            except Exception as e:
                logger.error(f"Background task error: {str(e)}")
                import traceback
                traceback.print_exc()
                return {'error': str(e)}
        
        # Run in background thread (plot outline takes too long for synchronous response)
        thread = threading.Thread(target=run_background_task)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Plot outline generation started. Use polling to check status.'
        })
    
    except Exception as e:
        logger.error(f"Error in create_plot_outline_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@content_studio_bp.route('/api/create-full-script', methods=['POST'])
@login_required
def create_full_script_api():
    """Create full script for fully scripted content"""
    try:
        data = request.get_json()
        group_id = data.get('groupId')
        series_name = data.get('seriesName')
        theme_name = data.get('themeName')
        title = data.get('title')
        video_length = data.get('videoLength', 30)
        
        if not all([group_id, series_name, theme_name, title]):
            return jsonify({'success': False, 'error': 'Missing required parameters'})
        
        def run_background_task():
            """Generate full script matching Discord bot workflow"""
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                from utils_dir.ai_utils import generate_full_script
                from bson import ObjectId
                
                # Convert group_id to ObjectId if needed
                if isinstance(group_id, str):
                    object_id = ObjectId(group_id)
                else:
                    object_id = group_id
                
                # Get script breakdown and plot outline from database
                script_breakdown_data = db.get_script_breakdown_sync(object_id, series_name, theme_name)
                plot_outline_data = db.get_plot_outline_sync(object_id, series_name, theme_name)
                
                if not script_breakdown_data or 'script_breakdown' not in script_breakdown_data:
                    return {'error': 'Script breakdown not found. Please generate script breakdown first.'}
                
                if not plot_outline_data or 'plot_outline' not in plot_outline_data:
                    return {'error': 'Plot outline not found. Please generate plot outline first.'}
                
                script_breakdown = script_breakdown_data['script_breakdown']
                plot_outline = plot_outline_data['plot_outline']
                
                # Create series and theme objects matching Discord bot format
                series = {'name': series_name}
                theme = {'name': theme_name}
                
                # Generate full script with all required parameters from Discord bot
                full_script, cost_data = loop.run_until_complete(
                    generate_full_script(
                        title=title,
                        plot_outline=plot_outline,
                        script_breakdown=script_breakdown,
                        series=series,
                        theme=theme,
                        video_length=video_length,
                        characters=set(),  # Empty set for now
                        research_articles=[],  # Empty list for now
                        host_name="Narrator",  # Default host name
                        sponsored_info=None  # No sponsorship info
                    )
                )
                
                if full_script:
                    # Save to database - create Google Doc
                    from services.google_docs_service import create_google_doc
                    
                    doc_url = loop.run_until_complete(
                        create_google_doc(
                            f"Full Script: {series_name} - {theme_name} - {title}",
                            full_script,
                            str(object_id)
                        )
                    )
                    
                    if doc_url:
                        # Save full script and doc URL to database
                        safe_series_name = series_name.replace(" ", "_")
                        safe_theme_name = theme_name.replace(" ", "_")
                        
                        db.save_full_script_sync(object_id, safe_series_name, safe_theme_name, full_script, doc_url)
                        
                        result = {'success': True, 'fullScript': doc_url, 'content': full_script}
                    else:
                        result = {'success': True, 'fullScript': full_script, 'content': full_script}
                else:
                    result = {'error': 'Failed to generate full script'}
                
                loop.close()
                return result
                
            except Exception as e:
                logger.error(f"Background task error: {str(e)}")
                import traceback
                traceback.print_exc()
                return {'error': str(e)}
        
        # Run in background thread
        thread = threading.Thread(target=run_background_task)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Full script generation started. This may take several minutes.'
        })
    
    except Exception as e:
        logger.error(f"Error in create_full_script_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@content_studio_bp.route('/api/create-voiceover', methods=['POST'])
@login_required
def create_voiceover_api():
    """Create voiceover from script"""
    try:
        data = request.get_json()
        script = data.get('script')
        voice_method = data.get('voiceMethod')  # 'elevenlabs' or 'kokoro'
        voice_id = data.get('voiceId', 'af_nicole')  # Default voice
        
        if not all([script, voice_method]):
            return jsonify({'success': False, 'error': 'Missing required parameters'})
        
        def run_background_voiceover():
            """Run voiceover generation in background"""
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                if voice_method == 'elevenlabs':
                    from utils_dir.ai_utils import generate_voice_over
                    result = loop.run_until_complete(
                        generate_voice_over(script, voice_id)
                    )
                else:  # kokoro
                    from utils_dir.ai_utils import generate_kokoro_voice_over
                    result = loop.run_until_complete(
                        generate_kokoro_voice_over(script)
                    )
                
                loop.close()
                return result
            except Exception as e:
                logger.error(f"Voiceover background task error: {str(e)}")
                return None
        
        # Run in background thread
        thread = threading.Thread(target=run_background_voiceover)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': f'Voiceover generation started using {voice_method}. This may take several minutes.'
        })
    
    except Exception as e:
        logger.error(f"Error in create_voiceover_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@content_studio_bp.route('/api/create-thumbnail', methods=['POST'])
@login_required
def create_thumbnail_api():
    """Generate thumbnail for the video (matching Discord bot workflow)"""
    try:
        data = request.get_json()
        group_id = data.get('groupId')
        series_name = data.get('seriesName')
        theme_name = data.get('themeName')
        title = data.get('title')
        
        if not all([group_id, series_name, theme_name, title]):
            return jsonify({'success': False, 'error': 'Missing required parameters'})
        
        def run_background_thumbnail():
            """Run thumbnail generation matching Discord bot complex workflow"""
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                from utils_dir.ai_utils import (
                    analyze_thumbnails_with_ai, generate_thumbnail_concepts,
                    download_and_prepare_images, train_model_with_replicate,
                    generate_thumbnail_with_trained_model, create_training_captions
                )
                from bson import ObjectId
                import shutil
                
                # Convert group_id to ObjectId if needed
                if isinstance(group_id, str):
                    object_id = ObjectId(group_id)
                else:
                    object_id = group_id
                
                # Step 1: Check for existing trained model
                model_exists = db.check_trained_model_exists_sync(object_id, series_name, theme_name)
                
                # Step 2: Get thumbnail data
                thumbnail_data = db.get_thumbnail_urls_sync(object_id, series_name, theme_name)
                
                # Process thumbnail data like Discord bot
                valid_thumbnails = []
                for t in thumbnail_data:
                    if t.get('url'):
                        # Extract video_id from URL if not present
                        if not t.get('video_id'):
                            url_parts = t['url'].split('/')
                            if len(url_parts) >= 5 and 'vi' in url_parts:
                                vi_index = url_parts.index('vi')
                                if vi_index + 1 < len(url_parts):
                                    t['video_id'] = url_parts[vi_index + 1]
                        
                        if t.get('video_id') or 'youtube' in t.get('url', '').lower():
                            valid_thumbnails.append(t)
                
                thumbnail_urls = [t['url'] for t in valid_thumbnails]
                titles = [t.get('title', '') for t in valid_thumbnails]
                
                if not thumbnail_urls:
                    return {'error': 'No thumbnail URLs found for analysis'}
                
                # Step 3: Handle insufficient thumbnails (< 12)
                if not model_exists and len(thumbnail_urls) < 12:
                    # Get all series thumbnails
                    all_series_thumbnails = db.get_all_series_thumbnails_sync(object_id, series_name)
                    
                    # Add series thumbnails and deduplicate
                    thumbnail_data.extend(all_series_thumbnails)
                    seen_keys = set()
                    unique_thumbnails = []
                    for thumb in thumbnail_data:
                        if not thumb.get('video_id') and 'url' in thumb:
                            url_parts = thumb['url'].split('/')
                            if len(url_parts) >= 5 and 'vi' in url_parts:
                                vi_index = url_parts.index('vi')
                                if vi_index + 1 < len(url_parts):
                                    thumb['video_id'] = url_parts[vi_index + 1]
                        
                        dedup_key = thumb.get('url', '')
                        if thumb.get('video_id'):
                            dedup_key += f"_{thumb.get('video_id')}"
                        
                        if dedup_key and dedup_key not in seen_keys:
                            seen_keys.add(dedup_key)
                            unique_thumbnails.append(thumb)
                    
                    thumbnail_data = unique_thumbnails
                    thumbnail_urls = [t['url'] for t in thumbnail_data]
                    titles = [t.get('title', '') for t in thumbnail_data]
                
                # Step 4: Get or create thumbnail guidelines
                guidelines = db.get_thumbnail_guidelines_sync(object_id, series_name, theme_name)
                if not guidelines:
                    guidelines = loop.run_until_complete(
                        analyze_thumbnails_with_ai(thumbnail_urls, series_name, theme_name)
                    )
                    db.save_thumbnail_guidelines_sync(object_id, series_name, theme_name, guidelines)
                
                # Step 5: Train model if it doesn't exist
                if not model_exists:
                    # Create captions
                    captions = loop.run_until_complete(
                        create_training_captions(guidelines, thumbnail_urls, titles)
                    )
                    
                    # Download and prepare images
                    training_data_path = loop.run_until_complete(
                        download_and_prepare_images(thumbnail_data, captions)
                    )
                    
                    # Train model
                    model_version = loop.run_until_complete(
                        train_model_with_replicate(training_data_path, series_name, theme_name)
                    )
                    
                    if not model_version:
                        return {'error': 'Model training failed'}
                    
                    # Save trained model info
                    db.save_trained_model_info_sync(object_id, series_name, theme_name, model_version)
                    shutil.rmtree(training_data_path)
                
                # Step 6: Generate thumbnail concepts
                plot_outline_data = db.get_plot_outline_sync(object_id, series_name, theme_name)
                plot_outline = plot_outline_data.get('plot_outline', '') if plot_outline_data else ''
                
                concepts = loop.run_until_complete(
                    generate_thumbnail_concepts(guidelines, title, thumbnail_urls, num_concepts=4)
                )
                
                # Save concepts
                db.save_thumbnail_concepts_sync(object_id, series_name, theme_name, title, concepts)
                
                # Step 7: Generate thumbnails using trained model
                thumbnail_images = []
                for i, concept in enumerate(concepts, 1):
                    urls = loop.run_until_complete(
                        generate_thumbnail_with_trained_model(
                            db, object_id, series_name, theme_name, concept, thumbnail_urls
                        )
                    )
                    if urls:
                        thumbnail_images.extend(urls)
                
                if thumbnail_images:
                    # Convert FileOutput objects to strings
                    thumbnail_urls_result = []
                    for img in thumbnail_images:
                        if hasattr(img, 'url'):
                            thumbnail_urls_result.append(str(img.url))
                        else:
                            thumbnail_urls_result.append(str(img))
                    
                    # Save generated thumbnails
                    for i, (url, concept) in enumerate(zip(thumbnail_urls_result, concepts)):
                        db.save_thumbnail_url_sync(
                            object_id, series_name, theme_name, title, url, {"concept": concept, "index": i}
                        )
                    
                    result = {'success': True, 'thumbnails': thumbnail_urls_result}
                else:
                    result = {'error': 'Failed to generate thumbnails'}
                
                loop.close()
                return result
                
            except Exception as e:
                logger.error(f"Thumbnail background task error: {str(e)}")
                import traceback
                traceback.print_exc()
                return {'error': str(e)}
        
        # Run in background thread
        thread = threading.Thread(target=run_background_thumbnail)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Thumbnail generation started. This may take several minutes.'
        })
    
    except Exception as e:
        logger.error(f"Error in create_thumbnail_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@content_studio_bp.route('/api/check-asset-status', methods=['POST'])
@login_required
def check_asset_status_api():
    """Check the status of generated assets for specific title"""
    try:
        data = request.get_json()
        group_id = data.get('groupId')
        series_name = data.get('seriesName')
        theme_name = data.get('themeName')
        title = data.get('title')  # Get the specific title
        
        if not all([group_id, series_name, theme_name]):
            return jsonify({'success': False, 'error': 'Missing required parameters'})
        
        # Check database for asset status
        safe_series_name = series_name.replace(' ', '_').replace('/', '_')
        safe_theme_name = theme_name.replace(' ', '_').replace('/', '_')
        
        # Use sync method from core database
        content_data = db.get_script_breakdown_sync(group_id, series_name, theme_name)
        
        print(f"🔍 ASSET CHECK: {content_data.keys() if content_data else 'None'}")
        if content_data:
            print(f"🔍 PLOT OUTLINE URL: {content_data.get('plot_outline_doc_url')}")
        
        if content_data:
            return jsonify({
                'success': True,
                'assets': {
                    'scriptBreakdown': content_data.get('script_breakdown_doc_url'),  # Return the Google Doc URL
                    'plotOutline': content_data.get('plot_outline_doc_url'),
                    'fullScript': content_data.get('full_script_doc_url'),
                    'voiceover': content_data.get('voiceover_url'),
                    'thumbnail': content_data.get('thumbnail_url')
                }
            })
        else:
            return jsonify({
                'success': True,
                'assets': {
                    'scriptBreakdown': None,
                    'plotOutline': None,
                    'fullScript': None,
                    'voiceover': None,
                    'thumbnail': None
                }
            })
    
    except Exception as e:
        logger.error(f"Error in check_asset_status_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@content_studio_bp.route('/api/export-to-trello', methods=['POST'])
@login_required
def export_to_trello_api():
    """Export assets to Trello (placeholder for now)"""
    try:
        data = request.get_json()
        assets = data.get('assets')
        
        # TODO: Implement Trello integration
        # For now, just return success
        
        return jsonify({
            'success': True,
            'message': 'Assets exported to Trello successfully'
        })
    
    except Exception as e:
        logger.error(f"Error in export_to_trello_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@content_studio_bp.route('/api/download-assets', methods=['POST'])
@login_required
def download_assets_api():
    """Prepare assets for download (placeholder for now)"""
    try:
        data = request.get_json()
        assets = data.get('assets')
        
        # TODO: Implement asset packaging and download
        # For now, just return success
        
        return jsonify({
            'success': True,
            'message': 'Assets prepared for download',
            'downloadUrl': '/downloads/assets.zip'  # Placeholder
        })
    
    except Exception as e:
        logger.error(f"Error in download_assets_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

# Manual voiceover endpoint for multi-character scripts
@content_studio_bp.route('/api/create-manual-voiceover', methods=['POST'])
@login_required
def create_manual_voiceover_api_endpoint():
    """Create voiceover from manual script with multi-character support"""
    from .manual_voiceover_api import create_manual_voiceover_api
    return create_manual_voiceover_api()


# ==========================================
# THUMBNAIL STUDIO API ENDPOINTS
# ==========================================

@content_studio_bp.route('/api/get-user-projects', methods=['GET'])
@login_required
def get_user_projects_api():
    """Get all projects/groups for the current user - for Thumbnail Studio dropdown"""
    try:
        current_user = get_current_user()
        
        # Try to get discord_id first, fall back to user id
        if hasattr(current_user, 'discord_id') and current_user.discord_id:
            discord_id = str(current_user.discord_id)
            user_groups = db.get_user_groups_sync(discord_id)
        else:
            # For web users without discord_id
            user_id = str(current_user.id)
            user_groups = db.get_web_user_groups_sync(user_id)
        
        # Format groups for dropdown
        projects = []
        for group in user_groups:
            projects.append({
                'id': str(group.get('_id')),
                'name': group.get('name', 'Unnamed Project'),
                'created_at': group.get('created_at', '').isoformat() if group.get('created_at') else None
            })
        
        return jsonify({
            'success': True,
            'projects': projects
        })
    except Exception as e:
        logger.error(f"Error in get_user_projects_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@content_studio_bp.route('/api/get-series/<project_id>', methods=['GET'])
@login_required
def get_series_api(project_id):
    """Get all series for a project - for Thumbnail Studio dropdown"""
    try:
        # Get series and themes data from the group
        series_themes = db.get_group_series_and_themes_sync(project_id)
        
        # Format for dropdown
        series_list = []
        for series_name in series_themes.keys():
            series_list.append({
                'name': series_name,
                'theme_count': len(series_themes.get(series_name, []))
            })
        
        return jsonify({
            'success': True,
            'series': series_list
        })
    except Exception as e:
        logger.error(f"Error in get_series_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@content_studio_bp.route('/api/get-themes/<project_id>/<series_name>', methods=['GET'])
@login_required
def get_themes_api(project_id, series_name):
    """Get all themes for a series - for Thumbnail Studio dropdown"""
    try:
        # Get series and themes data from the group
        series_themes = db.get_group_series_and_themes_sync(project_id)
        
        # Get themes for the specified series
        themes = series_themes.get(series_name, [])
        
        # Format for dropdown with model status
        themes_list = []
        for theme_name in themes:
            model_exists = db.check_trained_model_exists_sync(project_id, series_name, theme_name)
            themes_list.append({
                'name': theme_name,
                'has_model': model_exists
            })
        
        return jsonify({
            'success': True,
            'themes': themes_list
        })
    except Exception as e:
        logger.error(f"Error in get_themes_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@content_studio_bp.route('/api/model-status', methods=['POST'])
@login_required
def get_model_status_api():
    """Check if a trained model exists for series/theme"""
    try:
        data = request.get_json()
        project_id = data.get('projectId')
        series_name = data.get('seriesName')
        theme_name = data.get('themeName')
        
        if not all([project_id, series_name, theme_name]):
            return jsonify({'success': False, 'error': 'Missing required parameters'})
        
        model_exists = db.check_trained_model_exists_sync(project_id, series_name, theme_name)
        model_info = db.get_trained_model_info_sync(project_id, series_name, theme_name) if model_exists else None
        guidelines = db.get_thumbnail_guidelines_sync(project_id, series_name, theme_name)
        
        # Get thumbnail count for training data
        thumbnail_urls = db.get_thumbnail_urls_sync(project_id, series_name, theme_name)
        
        return jsonify({
            'success': True,
            'modelExists': model_exists,
            'modelInfo': model_info,
            'hasGuidelines': bool(guidelines),
            'thumbnailCount': len(thumbnail_urls),
            'minThumbnailsRequired': 12
        })
    except Exception as e:
        logger.error(f"Error in get_model_status_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@content_studio_bp.route('/api/thumbnail-status/<task_id>', methods=['GET'])
@login_required
def get_thumbnail_status_api(task_id):
    """Poll for thumbnail generation status - checks for generated thumbnails"""
    try:
        # Parse task_id which contains project_id|series|theme|title
        parts = task_id.split('|')
        if len(parts) != 4:
            return jsonify({'success': False, 'error': 'Invalid task ID format'})
        
        project_id, series_name, theme_name, title = parts
        
        # Check for generated thumbnails
        thumbnails = db.get_generated_thumbnails_sync(project_id, series_name, theme_name, title)
        
        if thumbnails:
            return jsonify({
                'success': True,
                'status': 'completed',
                'thumbnails': thumbnails
            })
        else:
            return jsonify({
                'success': True,
                'status': 'processing',
                'thumbnails': []
            })
    except Exception as e:
        logger.error(f"Error in get_thumbnail_status_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@content_studio_bp.route('/api/get-generated-thumbnails', methods=['POST'])
@login_required
def get_generated_thumbnails_api():
    """Get all generated thumbnails for a series/theme"""
    try:
        data = request.get_json()
        project_id = data.get('projectId')
        series_name = data.get('seriesName')
        theme_name = data.get('themeName')
        title = data.get('title')  # Optional - if provided, get thumbnails for specific title
        
        if not all([project_id, series_name, theme_name]):
            return jsonify({'success': False, 'error': 'Missing required parameters'})
        
        thumbnails = db.get_generated_thumbnails_sync(project_id, series_name, theme_name, title)
        
        return jsonify({
            'success': True,
            'thumbnails': thumbnails
        })
    except Exception as e:
        logger.error(f"Error in get_generated_thumbnails_api: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
