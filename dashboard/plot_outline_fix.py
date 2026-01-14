# EXACT Discord bot plot outline logic for web app

def create_plot_outline_background_task(group_id, series_name, theme_name, title, video_length):
    """EXACT copy of Discord bot create_plot_outline logic"""
    import asyncio
    import json
    from datetime import datetime
    from bson import ObjectId
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Import main database (not core wrapper)
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from database import db as main_db
        from utils.ai_utils import generate_plot_outline
        from services.google_docs_service import create_google_doc
        
        # Convert group_id to ObjectId if needed
        if isinstance(group_id, str):
            object_id = ObjectId(group_id)
        else:
            object_id = group_id
        
        # EXACT Discord bot logic - Step 1: Get script breakdown
        script_breakdown_data = loop.run_until_complete(
            main_db.get_script_breakdown(object_id, series_name, theme_name)
        )

        if not script_breakdown_data or 'guidelines' not in script_breakdown_data:
            return {'error': 'Script breakdown or guidelines not found. Please generate a script breakdown first.'}

        # EXACT Discord bot logic - Step 2: Parse guidelines to get script breakdown
        guidelines_raw = script_breakdown_data['guidelines']
        
        try:
            if guidelines_raw.startswith('{"is_clip_reactive"'):
                parsed = json.loads(guidelines_raw)
                script_breakdown = parsed.get('script_breakdown', guidelines_raw)
            else:
                script_breakdown = guidelines_raw
        except:
            script_breakdown = guidelines_raw
        
        # EXACT Discord bot logic - Step 3: Create series/theme objects
        series = {'name': series_name}
        theme = {'name': theme_name}
        
        # EXACT Discord bot logic - Step 4: Generate plot outline
        plot_outline = loop.run_until_complete(
            generate_plot_outline(title, script_breakdown, series, theme, video_length)
        )
        
        # EXACT Discord bot logic - Step 5: Create Google Doc
        doc_url = loop.run_until_complete(
            create_google_doc(
                f"Plot Outline: {series_name} - {theme_name} - {title}",
                plot_outline,
                str(object_id)
            )
        )
        
        if doc_url:
            # EXACT Discord bot logic - Step 6: Save plot outline and doc URL
            loop.run_until_complete(
                main_db.save_plot_outline(object_id, series_name, theme_name, plot_outline, doc_url)
            )
            
            # EXACT Discord bot logic - Step 7: Update content URLs for calendar
            loop.run_until_complete(
                main_db.update_content_urls(
                    object_id,
                    datetime.now().date().isoformat(),
                    {"plot_outline_url": doc_url}
                )
            )
            
            return {'success': True, 'plot_outline': plot_outline, 'doc_url': doc_url}
        else:
            return {'error': 'Error creating Google Doc for plot outline'}
            
    except Exception as e:
        print(f"❌ Plot outline error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}
    finally:
        loop.close()

