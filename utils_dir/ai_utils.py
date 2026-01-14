# Python standard library
from ast import arg
import asyncio
import base64
import functools
import io
import json
import logging
import math
import os
import random
import re
import shutil
import sys
import tempfile
import time
import traceback
from datetime import datetime
from typing import List, Dict, Optional, Union, Any
import textwrap
import librosa
from services.cloud_service import CloudVideoService
# Third-party packages
import aiohttp
import cv2
import numpy as np
import replicate
from anthropic import Anthropic, AsyncAnthropic, HUMAN_PROMPT, AI_PROMPT
from elevenlabs import Voice, voices
from elevenlabs.client import ElevenLabs
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload, MediaIoBaseDownload
from pydub import AudioSegment
import os
import zipfile
import time
import boto3
import aiohttp
import asyncio
import tenacity
import tempfile
import functools
import hashlib
import google.generativeai as genai
from google.generativeai.types import GenerationConfig, Tool # Import Tool
import os
import json
import logging
import re # For cleaner JSON extraction
from typing import List, Dict, Any # Corrected Type Hinting


# Local imports
from config import (
    ANTHROPIC_API_KEY,
    ELEVENLABS_API_KEY,
    GOOGLE_CREDENTIALS_FILE,
    REPLICATE_API_TOKEN,
    logger
)
from database import db
from services.google_docs_service import get_drive_service, get_credentials

def get_drive_service():
    """Get an authorized Drive service instance with domain delegation"""
    try:
        # Add caching - only create a new service if needed
        if hasattr(get_drive_service, 'cached_service') and get_drive_service.cached_service:
            try:
                # Test if the cached service still works by making a simple API call
                get_drive_service.cached_service.files().list(pageSize=1).execute()
                return get_drive_service.cached_service
            except Exception:
                # If test fails, cached service is invalid, create a new one
                logger.info("Cached Drive service failed, creating new service")
                pass
        
        # Use the same path configuration as google_docs_service
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        SERVICE_ACCOUNT_FILE = os.path.join(project_root, 'googlecred', 'service_account.json')
        
        # Your Workspace user email
        WORKSPACE_USER_EMAIL = 'boneless@nicole-ai.com'
        
        # Use retries for connection errors
        import socket
        import ssl
        import random
        import time
        
        MAX_RETRIES = 5
        
        for retry in range(MAX_RETRIES):
            try:
                # Load credentials from service account file
                credentials = service_account.Credentials.from_service_account_file(
                    SERVICE_ACCOUNT_FILE,
                    scopes=['https://www.googleapis.com/auth/drive.file', 
                           'https://www.googleapis.com/auth/drive']
                )
                
                # Add domain-wide delegation
                delegated_credentials = credentials.with_subject(WORKSPACE_USER_EMAIL)
                
                # Build the service with additional settings
                service = build('drive', 'v3', 
                               credentials=delegated_credentials,
                               cache_discovery=False)
                
                # Cache the service for future use
                get_drive_service.cached_service = service
                
                return service
            except (socket.error, ssl.SSLError, ConnectionError) as e:
                # These are network-related errors that might be transient
                if retry < MAX_RETRIES - 1:
                    wait_time = (2 ** retry) + (random.random() * 0.5)  # Exponential backoff with jitter
                    logger.warning(f"Drive service SSL/network error (attempt {retry+1}/{MAX_RETRIES}): {str(e)}. Retrying in {wait_time:.1f}s")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to initialize Drive service after {MAX_RETRIES} attempts: {str(e)}")
                    return None
    except Exception as e:
        logger.error(f"Error creating Drive service: {str(e)}")
        return None

ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)

print(f"Loading ai_utils.py from: {__file__}")
print(f"Python version: {sys.version}")
print(f"Python path: {sys.path}")

logger = logging.getLogger(__name__)

def cache_claude_analysis(func):
    cache = {}
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        key = str(args) + str(kwargs)
        if key not in cache:
            result = await func(*args, **kwargs)
            cache[key] = result
        return cache[key]
    return wrapper

import asyncio
import json
import logging
import random
import traceback
from typing import List, Dict
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = "your_anthropic_api_key_here"
@cache_claude_analysis
async def get_claude_analysis(video_data: List[Dict], channel_title: str = None, max_retries: int = 5, max_titles: int = 9000):
    video_titles = [video['title'] for video in video_data]
    logger.info(f"Starting Claude analysis for {len(video_titles)} video titles")
    
    if not video_titles:
        logger.error("No video titles provided for analysis")
        raise ValueError("No video titles provided for analysis")

    if len(video_titles) > max_titles:
        logger.warning(f"Number of video titles ({len(video_titles)}) exceeds maximum ({max_titles}). Truncating list.")
        video_titles = video_titles[:max_titles]

    # Add batch processing
    BATCH_SIZE = 80  # Process 50 videos at a time
    all_series_data = []
    
    # Split videos into batches
    video_batches = [video_titles[i:i + BATCH_SIZE] for i in range(0, len(video_titles), BATCH_SIZE)]
    
    # Initialize client and system message BEFORE the batch loop
    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    system_message = """You are a highly skilled YouTube content analyzer. Your task is to analyze video titles to identify top-performing series, themes, and topics. Follow these instructions precisely:

    1. **Hierarchy Understanding:**
       - Understand and maintain the correct hierarchy: Series > Themes > Topics.
       - A Series contains multiple Themes, and each Theme contains multiple Topics.

    2. **Series Identification:**
       - Examine the video titles to identify recurring words, phrases, or structures.
       - A series is a collection of videos with a consistent format, style, or recurring theme that ties them together.
       - Series names should be specific and descriptive, capturing the core concept.
       - Do not use placeholder words like [Person] or [Situation] in series names.
       - Example: If multiple videos start with or end with "Roblox But..." followed by different challenges, they belong to the "Roblox But" series.

    3. **Theme Identification:**
       - Identify the broader, overarching narrative or idea that the series explores.
       - The theme goes beyond the surface-level topic and captures the essence of what the series is about.
       - Themes should be general enough to encompass multiple videos but specific to the series.
       - Derive themes directly from the topics, ensuring they accurately represent the subject matter.
       - Avoid using specific time frames or numerical elements in theme names.
       - Example: For a "Roblox But" series, themes might be "Time-Based Changes" or "Player Limitations."

    4. **Topic Identification:**
       - The topic is the specific subject matter or narrative that each video addresses within the theme.
       - It's what differentiates one episode from another within the series.
       - The topic must be an exact, contiguous phrase taken directly from the title.
       - It should represent the most specific or unique element in the title.
       - Do not paraphrase or interpret the topic; use the exact words from the title.
       - Example: For "Roblox But Acid Rises Every Second", the topic is "Acid Rises".

    5. **Output Format:**
    Present the analysis as a JSON object with the following structure:

    {
      "series": [
        {
          "name": "Series Name",
          "themes": [
            {
              "name": "Theme Name",
              "topics": [
                {
                  "name": "Topic Name",
                  "example": "Full Video Title"
                }
              ]
            }
          ]
        }
      ]
    }

    6. **Constraints:**
       - Include all identified series.
       - For each series, include all identified themes.
       - Each topic MUST include the exact matching video title as its example.
       - Include EVERY video title as a topic somewhere in the structure.
       - Do not add any explanations or notes outside the specified JSON structure.

    7. **Theme Distinctiveness:**
       - Ensure themes within a series are distinct from each other.
       - If two themes are very similar, combine them into a single, more general theme.
       - Never repeat the same or nearly identical themes within a series.

    8. **Series Name Precision:**
       - Series names should be specific and avoid generic placeholders.
       - Capture the recurring pattern or concept that links multiple videos.
       - Ensure the series name is descriptive and unique to the content.
       - Name the series based on the repetitive title structure across multiple videos.
       - ONLY NAME THE SERIES BASED ON THE REPETITIVE TITLE STRUCTURE.
       - Example: If the repetitive title structure across multiple videos is "Roblox But...", the series name should be "Roblox But..."
    
    9. **Theme-Topic Relationship:**
       - Themes should directly relate to and encompass the video topics they contain.
       - Ensure a clear and logical connection between the theme and its video topics.

    10. **Theme-Topic Alignment:**
        - Ensure that the identified theme accurately represents the video topic.
        - The theme should be a broader category that the topic falls under.
        - If the topic is very specific (e.g., "Earth's Evolution"), the theme should be a more general category that encompasses it (e.g., "Planetary Development").
        - Avoid using the exact same wording for both theme and topic unless it's the only logical choice.
    
    11. **Consistency Check:**
        - After identifying themes and topics, review them to ensure consistency across all entries.
        - If you notice a theme that doesn't align well with its topics, reconsider and adjust the theme to better represent the content.
        - Make sure that similar topics across different videos are grouped under the same theme when appropriate.

    12. **Complete Coverage:**
        - Every single video title MUST be assigned to a series, theme, and topic
        - Track which titles have been processed and which haven't
        - Before finalizing output, verify that ALL input titles are included
        - If any titles are missing, create appropriate series/themes to include them
        - CRITICAL: When multiple videos have identical titles, DO NOT consolidate them
        - Each individual video title must appear as a separate topic entry, even if titles are duplicated
        - Example: If "Greek Mythology for Sleep" appears 90 times, create 90 separate topic entries
        
    
    13. **Series and Theme Merging Rules:**
        A. Series Pattern Analysis:
           - BEFORE creating any new series:
             * Check ALL existing series patterns for matches
             * Look for partial matches (e.g., "Upgrading to" vs "Upgrading into")
             * Check if pattern could be a theme of existing series
           
        B. Series Merging Priority:
           1. Exact Pattern Match:
              * If title matches existing series pattern exactly -> Add to that series
              * Example: "Upgrading to X" matches "Upgrading to... in GTA 5"
           
           2. Similar Pattern Match:
              * If title has similar pattern -> Merge into existing series
              * Examples:
                - "Upgrading to" and "Upgrading into" -> Merge as "Upgrading to. in GTA 5"
                - "Character Evolution" and "Character Progression" -> Merge as one series
           
           3. Theme vs Series Decision:
              * If new pattern could be subset of existing series -> Add as theme
              * Example: "Size Transformation" should be theme under "Upgrading" series
        
        C. Theme Merging Priority:
           1. Check Existing Themes:
              * Look for similar theme concepts across ALL series
              * Consolidate themes with similar meanings
              * Example: "Character Power-Ups" and "Basic Transformations" -> Merge as "Character Transformations"
           
           2. Theme Hierarchy:
              * General themes should absorb more specific ones
              * Maintain consistent theme names across series
              * Example: All size-related themes -> "Size Transformations"

        D. New Series Creation Rules:
           - ONLY create new series when:
             1. Title pattern is completely unique
             2. Cannot fit into any existing series
             3. Cannot be converted to theme
             4. Follows clear repetitive structure

    7. **Style Guidelines:**
       - **Do not include any text outside of the JSON object.**
       - **Your response should start immediately with '{' and end with '}'.**
       - **Do not include any introductory text, explanations, or apologies.**

    **Your response must strictly follow the specified JSON format without any deviations. Include every single video title in the analysis, ensuring no titles are missed or omitted. Start your response immediately with the JSON object.**
    """
    
    for batch_num, video_batch in enumerate(video_batches):
        logger.info(f"Processing batch {batch_num + 1}/{len(video_batches)} ({len(video_batch)} videos)")
        
        titles_text = "\n".join([f"- {title}" for title in video_batch])
        
        # Add previous batch series info to the prompt if not first batch
        if batch_num > 0:
            # Include full series structure, not just names
            previous_series_info = []
            for series in all_series_data:
                themes_info = []
                for theme in series.get('themes', []):
                    themes_info.append(f"    - Theme: {theme['name']}")
                    for topic in theme.get('topics', []):
                        themes_info.append(f"      • Topic: {topic['name']} (Example: {topic['example']})")
                
                previous_series_info.extend([
                    f"- Series: {series['name']}",
                    *themes_info
                ])
            
            series_context = "\n".join(previous_series_info)
            
            user_message = f"""Analyze the following video titles with STRICT adherence to the existing series and themes:

Previously identified series structure:
{series_context}

Video titles to analyze:
{titles_text}

Please carefully analyze these titles and:

1. **Add to Existing Series and Themes:**
   - **Mandatory:** Before creating any new series, check if each video title fits into any existing series.
   - Use **exact matching** and **case-insensitive** comparisons for series names to avoid variations.
   - If a title fits multiple series, choose the most specific one.
   - **Critical:** Check EVERY word in the title against existing series patterns, not just the beginning.
   - Example: "When Evil Parents Realize..." should match "When... Get/Try/Realize" series.

2. **Merge Similar Series and Themes:**
   - If a potential new series shares similarities with an existing one, **merge them**.
   - Look for partial matches or variations in naming (e.g., "Upgrading to..." vs. "Upgrading into...").
   - Consolidate themes with overlapping concepts under a more general theme.

3. **Avoid Redundancies:**
   - **Eliminate duplicates** in series, themes, and topics.
   - Ensure that topics are unique and not repeated within the same theme.

4. **Create New Series Only When Necessary:**
   - Only create a new series if the title pattern is **completely unique** and **cannot fit** into any existing series or theme.
   - Ensure the new series follows the established naming conventions.

5. **Maintain Series Name Precision:**
   - Series names must be based on the **exact repetitive title structure**.
   - Enforce uniformity in naming conventions across all batches.

6. **Review and Adjust Hierarchies:**
   - Ensure that themes are correctly placed under the appropriate series.
   - Adjust the hierarchy if a theme aligns better with a different series.

7. **Complete Data Fields:**
   - Populate all data fields for each topic, ensuring no missing information. EVERY SINGLE VIDEO TITLE MUST BE INCLUDED.

8. **Strictly Follow the System Message Guidelines:**
   - Adhere to **all rules** and instructions provided in the system message.

When in doubt, **prefer merging into existing series and themes** over creating new ones. The goal is to have a cohesive, non-redundant structure that accurately categorizes all video titles.

Provide the updated analysis in the specified JSON format without any extra explanations."""
        else:
            user_message = f"""Analyze the following video titles:

{titles_text}

Please analyze these video titles and provide a comprehensive analysis in the specified JSON format without any extra explanations."""

        for attempt in range(max_retries):
            try:
                logger.info(f"Sending request to Claude API (attempt {attempt + 1})")
                response = await client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=8192,
                    temperature=0.2,
                    system=system_message,
                    messages=[{"role": "user", "content": user_message}]
                )
                
                response_text = response.content[0].text
                logger.debug(f"Raw Claude API response for batch {batch_num + 1}: {response_text[:500]}...")
                
                # Clean response - strip markdown code blocks if present
                clean_text = response_text.strip()
                if '```json' in clean_text:
                    clean_text = clean_text.split('```json')[1]
                if '```' in clean_text:
                    clean_text = clean_text.split('```')[0]
                clean_text = clean_text.strip()
                
                try:
                    batch_series_data = json.loads(clean_text)
                    if isinstance(batch_series_data, dict) and 'series' in batch_series_data:
                        all_series_data.extend(batch_series_data['series'])
                        break
                    elif isinstance(batch_series_data, list):
                        all_series_data.extend(batch_series_data)
                        break
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON for batch {batch_num + 1}, retrying...")
                    continue
                    
            except Exception as e:
                logger.error(f"Error in Claude API request for batch {batch_num + 1} (attempt {attempt + 1}): {str(e)}")
                if attempt == max_retries - 1:
                    return None
    # Merge similar series
    merged_series = {}
    for series in all_series_data:
        name = series['name']
        if name not in merged_series:
            merged_series[name] = series
        else:
            for theme in series['themes']:
                existing_themes = merged_series[name]['themes']
                theme_exists = False
                for existing_theme in existing_themes:
                    if existing_theme['name'] == theme['name']:
                        existing_theme['topics'].extend(theme['topics'])
                        theme_exists = True
                        break
                if not theme_exists:
                    existing_themes.append(theme)

    # Add this check right before returning the merged_series data
    if merged_series and len(merged_series) == 1:
        # If we only have one series, check if it contains all videos
        # If not, make sure each video appears at least once in the structure
        series_name = next(iter(merged_series.keys()))
        series = merged_series[series_name]
        
        all_examples = []
        for theme in series.get('themes', []):
            for topic in theme.get('topics', []):
                all_examples.append(topic.get('example', ''))
        
        # Check if any videos are missing from the analysis
        missing_titles = set([video['title'] for video in video_data]) - set(all_examples)
        
        if missing_titles:
            # Create a new theme for missing titles if needed
            if not series.get('themes'):
                series['themes'] = []
                
            # Add missing titles to an appropriate theme or create a new one
            misc_theme = None
            for theme in series['themes']:
                if theme['name'] == 'Miscellaneous':
                    misc_theme = theme
                    break
                    
            if not misc_theme:
                misc_theme = {'name': 'Miscellaneous', 'topics': []}
                series['themes'].append(misc_theme)
                
            for title in missing_titles:
                misc_theme['topics'].append({
                    'name': title.split(' ')[0:3],  # Take first few words as topic name
                    'example': title
                })
    
    return list(merged_series.values()) if merged_series else None

def extract_partial_data(response_string):
    series = []
    current_series = None
    current_theme = None
    
    for line in response_string.split('\n'):
        line = line.strip()
        if '"name":' in line and '"themes":' in line:
            if current_series:
                series.append(current_series)
            current_series = {"name": line.split('"name":')[1].split(',')[0].strip(' "'), "themes": []}
        elif '"name":' in line and '"topics":' in line:
            if current_theme:
                current_series["themes"].append(current_theme)
            current_theme = {"name": line.split('"name":')[1].split(',')[0].strip(' "'), "topics": []}
        elif '"name":' in line and '"example":' in line:
            name = line.split('"name":')[1].split(',')[0].strip(' "')
            example = line.split('"example":')[1].strip(' ",')
            current_theme["topics"].append({"name": name, "example": example})
    
    if current_theme:
        current_series["themes"].append(current_theme)
    if current_series:
        series.append(current_series)
    
    return series


def fix_json_string(json_str):
    # Remove any text before the first '{' and after the last '}'
    json_str = json_str.strip()
    start = json_str.find('{')
    end = json_str.rfind('}') + 1
    json_str = json_str[start:end]

    # Unescape escaped characters
    json_str = json_str.replace('\\"', '"').replace('\\\\', '\\')

    # Fix common JSON formatting issues
    json_str = json_str.replace("'", '"')
    json_str = json_str.replace('True', 'true').replace('False', 'false').replace('None', 'null')

    # Remove any trailing commas before closing brackets
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*]', ']', json_str)

    return json_str

async def check_video_relevance(claude_analysis: Dict, videos: List[Dict]) -> int:
    
    matching_series = 0
    for series in claude_analysis['series']:
        for video in videos:
            if await check_videos_in_series(series['name'], video['title']):
                matching_series += 1
                break
    return matching_series

def check_videos_in_series(series_data: List[Dict], videos: List[str]) -> Dict[str, List[Dict]]:
    result = {}
    
    for series in series_data:
        series_name = series['name']
        result[series_name] = []
        
        for theme in series['themes']:
            theme_name = theme['name']
            
            for topic in theme['topics']:
                topic_name = topic['name']
                topic_keywords = set(re.findall(r'\w+', topic_name.lower()))
                
                for video_title in videos:
                    video_keywords = set(re.findall(r'\w+', video_title.lower()))
                    
                    # Check if there's significant overlap between video title and topic keywords
                    if len(topic_keywords.intersection(video_keywords)) >= 2:
                        result[series_name].append({
                            'title': video_title,
                            'theme': theme_name,
                            'topic': topic_name
                        })
    
    # Remove series with no matching videos
    return {k: v for k, v in result.items() if v}

def parse_claude_response(response: List[Dict]) -> List[Dict]:
    try:
        if not isinstance(response, list):
            logger.error(f"Invalid response structure: {response}")
            return None

        series_data = []
        for series in response:
            if not isinstance(series, dict) or "name" not in series or "themes" not in series:
                logger.error(f"Invalid series structure: {series}")
                continue

            series_info = {
                'name': series['name'],
                'themes': []
            }
            for theme in series['themes']:
                if not isinstance(theme, dict) or "name" not in theme or "topics" not in theme:
                    logger.error(f"Invalid theme structure: {theme}")
                    continue

                theme_info = {
                    'name': theme['name'],
                    'topics': []
                }
                for topic in theme['topics']:
                    if not isinstance(topic, dict) or "name" not in topic or "example" not in topic:
                        logger.error(f"Invalid topic structure: {topic}")
                        continue

                    topic_info = {
                        'name': topic['name'],
                        'example': topic['example']
                    }
                    theme_info['topics'].append(topic_info)
                series_info['themes'].append(theme_info)
            series_data.append(series_info)
        return series_data
    
    except Exception as e:
        logger.error(f"Error parsing Claude response: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return None
def process_series_data(data: dict) -> List[Dict]:
    if not isinstance(data, dict) or 'series' not in data:
        logger.warning("Data is not in the expected format")
        return None

    processed_data = []
    for series in data['series']:
        series_data = {
            "name": series.get('name', 'Unnamed Series'),
            "themes": [{
                "name": theme.get('name', 'Unnamed Theme'),
                "topics": [{
                    "name": topic.get('name', 'Unnamed Topic'),
                    "example": topic.get('example', 'No example')
                } for topic in theme.get('topics', [])]
            } for theme in series.get('themes', [])]
        }
        processed_data.append(series_data)
    return processed_data

def parse_views(view_string: str) -> int:
    if not view_string or view_string.lower() in ['not available', 'n/a']:
        return 0

    view_string = view_string.strip().lower().replace(',', '')
    
    multipliers = {'k': 1000, 'm': 1000000, 'b': 1000000000}
    
    try:
        for suffix, multiplier in multipliers.items():
            if view_string.endswith(suffix):
                return int(float(view_string[:-1]) * multiplier)
        
        return int(float(view_string))
    except ValueError:
        logger.warning(f"Could not parse view count: {view_string}")
        return 0

def parse_niche_and_demographics(response: str) -> Dict:
    lines = response.split('\n')
    result = {}
    current_section = None

    for line in lines:
        line = line.strip()
        if line.startswith("Niche:"):
            result['niche'] = line.split(":", 1)[1].strip()
        elif line == "Target Demographics:":
            current_section = "demographics"
            result['demographics'] = {}
        elif current_section == "demographics":
            if line.startswith("- Age Range:"):
                result['demographics']['age_range'] = line.split(":", 1)[1].strip()
            elif line.startswith("- Gender Split:"):
                result['demographics']['gender_split'] = line.split(":", 1)[1].strip()
            elif line.startswith("- Interests:"):
                result['demographics']['interests'] = [i.strip() for i in line.split(":", 1)[1].strip().split(',')]
            elif line.startswith("- Geographic Regions:"):
                result['demographics']['regions'] = []
            elif line.startswith(tuple("12345")) and 'regions' in result['demographics']:
                result['demographics']['regions'].append(line.split(".", 1)[1].strip())

def calculate_average_views(series_list: List[Dict]) -> float:
    if not series_list:
        return 0.0
    
    total_views = 0
    for series in series_list:
        if "average_views" in series and isinstance(series["average_views"], (int, float)):
            total_views += series["average_views"]
        else:
            # Log a warning or handle the case where average_views is missing or not a number
            print(f"Warning: Invalid average_views for series: {series.get('name', 'Unknown')}")
    
    return total_views / len(series_list)


    return result

async def identify_niche_and_demographics(channel_data: Dict, videos: List[Dict]):
    try:
        system_message = """You are an AI assistant specializing in YouTube channel analysis. Your task is to identify the niche and target demographics for a YouTube channel based on its content and audience."""

        user_message = f"""
        Channel Name: {channel_data.get('title', 'Unknown')}
        Subscriber Count: {channel_data.get('subscriberCount', 'Unknown')}
        Video Count: {channel_data.get('videoCount', 'Unknown')}
        Total Views: {channel_data.get('viewCount', 'Unknown')}

        Channel Description: {channel_data.get('description', 'No description available')}

        Recent Video Titles:
        {chr(10).join([f"- {video.get('title', 'Unknown Title')}" for video in videos[:10]])}

        Please analyze this information and provide:

        1. Niche: Identify the primary niche of this channel. Be specific but concise.
        2. Target Demographics: Estimate the primary target audience in terms of:
           - Age range
           - Gender split (if applicable)
           - Interests
           - Geographic regions (list top 5 countries you think this content would appeal to)

        Format your response as follows:

        Niche: [Identified Niche]

        Target Demographics:
        - Age Range: [Estimated Age Range]
        - Gender Split: [Estimated Gender Distribution or 'Not Specifically Targeted']
        - Interests: [List of 3-5 Primary Interests]
        - Geographic Regions:
          1. [Country 1]
          2. [Country 2]
          3. [Country 3]
          4. [Country 4]
          5. [Country 5]

        Provide only the requested information without any additional explanation.
        """

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "system": system_message,
                    "messages": [
                        {"role": "user", "content": user_message}
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.7
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info("Received response from Claude API")
                    logger.debug(f"Claude response: {data}")
                    if 'content' in data:
                        content_text = data['content'][0]['text']
                        return parse_niche_and_demographics(content_text)
                    else:
                        logger.error(f"Key 'content' not found in response: {data}")
                        raise Exception(f"Key 'content' not found in response: {data}")
                else:
                    error_data = await response.text()
                    logger.error(f"Error in Claude API call: {error_data}")
                    raise Exception(f"Claude API returned an error: {error_data}")

    except Exception as e:
        logger.error(f"Error in identify_niche_and_demographics: {str(e)}", exc_info=True)
        return {
            "niche": "Unknown",
            "demographics": {
                "age_range": "Unknown",
                "gender_split": "Unknown",
                "interests": ["Unknown"],
                "geographic_regions": ["Unknown"]
            }
        }

import aiohttp
from config import ANTHROPIC_API_KEY


async def generate_production_resources(niche):
    prompt = f"Given a YouTube niche of {niche}, what are the typical production resources needed? Include equipment, software, and human resources."
    return await generate_ai_response(prompt)

async def generate_monetization_opportunities(niche):
    prompt = f"For a YouTube channel in the {niche} niche, what are the best monetization opportunities? Include both on-platform and off-platform strategies."
    return await generate_ai_response(prompt)

async def generate_ai_response(prompt, max_tokens_to_sample=1000, model="claude-3-haiku-20240307"):
    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens_to_sample,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"Error in generate_ai_response: {str(e)}")
        raise

async def generate_production_resources(niche, top_video_transcript):
    prompt = f"""Given a YouTube niche of {niche} and the following transcript from a top-performing video in this niche:

Transcript:
{top_video_transcript}

Based on this information, provide detailed production resource requirements. Format your response as a Python dictionary with the following keys:
    'equipment': List common equipment used in this niche.
    'software': Describe software tools typically used in production.
    'human_resources': Outline the team composition and roles needed.
    'estimated_costs': Provide a breakdown of potential production costs.
Ensure the response is a valid Python dictionary.
    """
    response = await generate_ai_response(prompt, max_tokens_to_sample=4000, model="claude-3-haiku-20240307")
    
    try:
        resources = eval(response)
        if not isinstance(resources, dict):
            raise ValueError("Response is not a valid dictionary")
        
        required_keys = ['equipment', 'software', 'human_resources', 'estimated_costs']
        for key in required_keys:
            if key not in resources:
                resources[key] = f"No {key} data available."
        
        return resources
    except Exception as e:
        logger.error(f"Error processing AI response: {str(e)}")
        return {
            'equipment': "Error retrieving equipment data.",
            'software': "Error retrieving software data.",
            'human_resources': "Error retrieving human resources data.",
            'estimated_costs': "Error retrieving cost estimation data."
        }

async def generate_monetization_opportunities(niche, top_video_transcript):
    prompt = f"""Given a YouTube niche of {niche} and the following transcript from a top-performing video in this niche:

Transcript:
{top_video_transcript}

Based on this information, provide detailed monetization opportunities. Format your response as a Python dictionary with the following keys:
    'on_platform': List YouTube-specific monetization methods.
    'off_platform': Describe external revenue streams.
    'sponsorships': Outline potential sponsorship opportunities.
    'merchandise': Suggest product ideas and merchandising strategies.
Ensure the response is a valid Python dictionary.
    """
    response = await generate_ai_response(prompt, max_tokens_to_sample=4000, model="claude-3-haiku-20240307")
    
    try:
        opportunities = eval(response)
        if not isinstance(opportunities, dict):
            raise ValueError("Response is not a valid dictionary")
        
        required_keys = ['on_platform', 'off_platform', 'sponsorships', 'merchandise']
        for key in required_keys:
            if key not in opportunities:
                opportunities[key] = f"No {key} data available."
        
        return opportunities
    except Exception as e:
        logger.error(f"Error processing AI response for monetization opportunities: {str(e)}")
        return {
            'on_platform': "Error retrieving on-platform monetization data.",
            'off_platform': "Error retrieving off-platform monetization data.",
            'sponsorships': "Error retrieving sponsorship data.",
            'merchandise': "Error retrieving merchandise data."
        }
    
async def analyze_content_taxonomy(group_id, db):
    required_keys = ['primary_category', 'secondary_categories', 'content_types', 'themes', 'target_audience', 'vertical', 'niche']
    
    try:
        video_titles = await db.get_video_titles_for_group(group_id)
        logger.info(f"Analyzing content taxonomy for group {group_id} with {len(video_titles)} video titles")
        
        prompt = f"""Analyze the following YouTube video titles from a competitor group:

{', '.join(video_titles[:100])}  # Limit to 100 titles to avoid exceeding token limits

Based on these titles, provide a content taxonomy analysis. Format your response with the following keys:
    primary_category: The main content category.
    secondary_categories: Specific content sub-categories.
    content_types: Common video formats used.
    themes: Prevalent content themes or topics.
    target_audience: The intended audience for these videos.
    vertical: The broader industry or field this content falls under.
    niche: The specific market segment or specialized area within the vertical.

For each key, provide the most common attributes and their estimated percentage of occurrence.
"""
        response = await generate_ai_response(prompt, max_tokens_to_sample=2000, model="claude-3-haiku-20240307")
        logger.info(f"AI response for group {group_id}: {response}")
        
        # Parse the response
        taxonomy = {}
        current_key = None
        for line in response.split('\n'):
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower().replace(' ', '_')
                if key in required_keys:
                    current_key = key
                    taxonomy[current_key] = value.strip()
            elif current_key and line:
                taxonomy[current_key] += ' ' + line
        
        # Ensure all required keys are present
        for key in required_keys:
            if key not in taxonomy:
                taxonomy[key] = "Unknown"
        
        logger.info(f"Parsed taxonomy for group {group_id}: {taxonomy}")
        return taxonomy
    except Exception as e:
        logger.error(f"Error processing AI response for content taxonomy: {str(e)}", exc_info=True)
        return {key: "Unknown" for key in required_keys}

async def generate_multi_voice_over(script: str, voice_selections: Dict[str, str], user_id: int) -> str:
    logger.info(f"Starting generate_multi_voice_over for user {user_id}")
    api_key = await db.get_elevenlabs_api_key(user_id)
    if not api_key:
        logger.error(f"ElevenLabs API key not found for user {user_id}")
        raise ValueError("ElevenLabs API key not found for this user.")

    # Clean up the script first - remove any metadata or formatting
    script = re.sub(r'Word count:.*?\n', '', script)  # Remove word count
    script = re.sub(r'Segment:.*?\n', '', script)  # Remove segment titles
    script = re.sub(r'\n\s*\n', '\n', script)  # Remove extra newlines
    
    # Extract dialogue segments with improved pattern
    dialogue_pattern = r'\[([^\]]+)\]:\s*((?:[^[]+(?:\[(?![\w\s]+\]:)[^[]*)*)+)'
    dialogue_segments = re.findall(dialogue_pattern, script, re.DOTALL)
    
    if not dialogue_segments:
        logger.error("No valid dialogue segments found in script")
        raise ValueError("No valid dialogue segments found in script. Check script format.")
    
    logger.info(f"Found {len(dialogue_segments)} dialogue segments")
    
    audio_segments = []
    segment_timings = []
    current_position = 0
    
    # Process each dialogue segment
    for character, line in dialogue_segments:
        character = character.strip()
        line = line.strip()
        
        if not line:  # Skip empty lines
            continue
            
        logger.info(f"Generating voice over for segment - Character: {character}")
        voice_id = voice_selections.get(character)
        
        if not voice_id:
            logger.error(f"Voice ID not found for character: {character}")
            continue

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": api_key
        }
        data = {
            "text": line,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        audio_segment = await response.read()
                        # Store segment timing
                        segment_length = len(audio_segment) / 32000  # Approximate timing based on audio length
                        segment_timings.append((current_position, current_position + segment_length))
                        current_position += segment_length
                        
                        audio_segments.append(audio_segment)
                        logger.info(f"Successfully generated voice for segment - Character: {character}")
                    else:
                        error_message = await response.text()
                        logger.error(f"Error generating voice for segment - Character: {character}: {error_message}")
                        raise ValueError(f"Error generating voice for segment - Character: {character}: {error_message}")
        except Exception as e:
            logger.error(f"Exception while generating voice for segment - Character: {character}: {str(e)}", exc_info=True)
            raise

    # Combine audio segments
    combined_audio = b''.join(audio_segments)

    # Upload to Google Drive
    logger.info("Uploading combined audio to Google Drive")
    try:
        drive_service = get_drive_service()
        file_metadata = {'name': f'voice_over_{int(time.time())}.mp3'}
        media = MediaIoBaseUpload(io.BytesIO(combined_audio), mimetype='audio/mpeg', resumable=True)
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id,webViewLink').execute()
        
        # Make the file publicly accessible
        drive_service.permissions().create(fileId=file['id'], body={'type': 'anyone', 'role': 'reader'}).execute()

        logger.info(f"Voice over uploaded successfully. URL: {file['webViewLink']}")
        return file['webViewLink']
    except Exception as e:
        logger.error(f"Error uploading voice over to Google Drive: {str(e)}", exc_info=True)
        raise

async def generate_tts(text: str, profile: dict) -> str:
    """Generate TTS using either F5-TTS for cloning or Parler TTS for descriptions"""
    try:
        client = replicate.Client(api_token=REPLICATE_API_TOKEN)
        
        if profile['voice_type'] == 'clone':
            # Use F5-TTS for voice cloning
            output = await client.run(
                "nyxynyx/f5-tts:b4b5e5c2c3e9f3af0a83be8c18eb97ce4f8b7dac51a853014c6e20caf2d56db4",
                input={
                    "text": text,
                    "ref_audio_path": profile['voice_input']
                }
            )
        else:
            # Use Parler TTS for description-based voices
            output = await client.run(
                "andreasjansson/parler-tts:69c4aa53312b8698188d425ba6d25c9a14636adb9ea2ae1fd313a0fd2b45a32b",
                input={
                    "text": text,
                    "description": profile['voice_input']
                }
            )
        
        if output and isinstance(output, dict) and 'audio' in output:
            return output['audio']
        return None
    except Exception as e:
        logger.error(f"Error in TTS generation: {str(e)}")
        raise

async def apply_rvc(audio: bytes, model_id: str) -> bytes:
    """Apply RVC voice conversion using Replicate API"""
    try:
        output = replicate.run(
            "pseudoram/rvc-v2",
            input={
                "audio": audio,
                "model": model_id,
                "pitch_adjust": 0
            }
        )
        
        if output and 'audio' in output:
            async with aiohttp.ClientSession() as session:
                async with session.get(output['audio']) as response:
                    return await response.read()
        return None
    except Exception as e:
        logger.error(f"Error in RVC processing: {str(e)}")
        raise


async def generate_tts_rvc_voice_over(script: str, voice_selections: Dict[str, str], user_id: int) -> str:
    """Generate voice over using TTS+RVC pipeline, following same pattern as ElevenLabs"""
    logger.info(f"Starting TTS+RVC voice over generation for user {user_id}")

    # Clean up script same way as ElevenLabs version
    script = re.sub(r'Word count:.*?\n', '', script)
    script = re.sub(r'Segment:.*?\n', '', script)
    script = re.sub(r'\n\s*\n', '\n', script)
    
    # Use same dialogue pattern for consistency
    dialogue_pattern = r'\[([^\]]+)\]:\s*((?:[^[]+(?:\[(?![\w\s]+\]:)[^[]*)*)+)'
    dialogue_segments = re.findall(dialogue_pattern, script, re.DOTALL)
    
    if not dialogue_segments:
        logger.error("No valid dialogue segments found in script")
        raise ValueError("No valid dialogue segments found in script. Check script format.")
    
    logger.info(f"Found {len(dialogue_segments)} dialogue segments")
    
    # Get user's voice profiles
    voice_profiles = await db.get_tts_rvc_profiles(user_id)
    if not voice_profiles:
        raise ValueError("No voice profiles found for user")
    
    # Create profile lookup dict for quick access
    profile_lookup = {p['id']: p for p in voice_profiles}
    
    audio_segments = []
    segment_timings = []
    current_position = 0
    
    # Process each dialogue segment
    for character, line in dialogue_segments:
        character = character.strip()
        line = line.strip()
        
        if not line:
            continue
            
        logger.info(f"Generating voice over for segment - Character: {character}")
        profile_id = voice_selections.get(character)
        
        if not profile_id:
            logger.error(f"Voice profile not found for character: {character}")
            continue
            
        profile = profile_lookup.get(profile_id)
        if not profile:
            logger.error(f"Profile {profile_id} not found in database")
            continue

        try:
            # Generate TTS first
            logger.info(f"Generating TTS for character {character}")
            tts_audio = await generate_tts(
                text=line,
                emotion=profile['tts_emotion'],
                model_id="x-lance/f5-tts"  # Using F5 TTS for emotion support
            )
            
            if tts_audio:
                # Apply RVC transformation
                logger.info(f"Applying RVC for character {character}")
                rvc_audio = await apply_rvc(
                    audio=tts_audio,
                    model_id=profile['rvc_model']
                )
                
                if rvc_audio:
                    # Calculate timing same way as ElevenLabs version
                    segment_length = len(rvc_audio) / 32000
                    segment_timings.append((current_position, current_position + segment_length))
                    current_position += segment_length
                    
                    audio_segments.append(rvc_audio)
                    logger.info(f"Successfully generated voice for segment - Character: {character}")
                else:
                    logger.error(f"RVC processing failed for character: {character}")
            else:
                logger.error(f"TTS generation failed for character: {character}")
                
        except Exception as e:
            logger.error(f"Error processing segment for {character}: {str(e)}", exc_info=True)
            continue

    if not audio_segments:
        raise ValueError("No audio segments were generated successfully")

    # Combine audio segments
    combined_audio = b''.join(audio_segments)
    
    # Upload to Google Drive - same as ElevenLabs version
    logger.info("Uploading combined audio to Google Drive")
    try:
        drive_service = get_drive_service()
        file_metadata = {'name': f'tts_rvc_voice_over_{int(time.time())}.mp3'}
        media = MediaIoBaseUpload(io.BytesIO(combined_audio), mimetype='audio/mpeg', resumable=True)
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id,webViewLink').execute()
        
        # Make file publicly accessible
        drive_service.permissions().create(fileId=file['id'], body={'type': 'anyone', 'role': 'reader'}).execute()

        logger.info(f"Voice over uploaded successfully. URL: {file['webViewLink']}")
        return file['webViewLink']
    except Exception as e:
        logger.error(f"Error uploading voice over to Google Drive: {str(e)}", exc_info=True)
        raise

async def check_shared_series(series_data, search_result_titles, current_series_name):
    if isinstance(series_data, str):
        try:
            series_data = json.loads(series_data)
        except json.JSONDecodeError:
            # If it's not valid JSON, assume it's already a Python object
            pass
    
    if not isinstance(series_data, list):
        series_data = [series_data]
    
    if not isinstance(search_result_titles, list):
        search_result_titles = [str(search_result_titles)]
    
    
    print(f"Current Series Name: {current_series_name}")
    print(f"Series Data: {json.dumps(series_data, indent=2)}")
    print(f"First 5 Search Result Titles: {search_result_titles[:5]}")
    print(f"Total Search Result Titles: {len(search_result_titles)}")
    
    # Normalize current_series_name
    current_series_name_normalized = current_series_name.strip().lower()

    # Find the series in series_data that matches the current_series_name
    matching_series = None
    for series in series_data:
        series_name_normalized = series.get('name', '').strip().lower()
        if series_name_normalized == current_series_name_normalized:
            matching_series = series
            break

    if not matching_series:
        print(f"Series '{current_series_name}' not found in series_data.")
        # Handle this case appropriately
        result = {
            "shared_series": [],
            "is_eligible": False,
            "shared_series_count": 0
        }
        return result
    
    series_info = []
    example_titles = []
    
    series_info.append(f"Series: {current_series_name}")
    for theme in matching_series.get('themes', []):
        series_info.append(f"  Theme: {theme['name']}")
        for topic in theme.get('topics', []):
            series_info.append(f"    • Topic: {topic['name']}")
            example = topic.get('example', 'N/A')
            series_info.append(f"    • Example: {example}")
            if example != 'N/A':
                example_titles.append(example)
    series_info_str = "\n".join(series_info)
    
    prompt = f"""
    Series Information:
    {series_info_str}

    Search Result Video Titles:
    {json.dumps(search_result_titles[:100], indent=2)}  # Limit to 100 titles

    Analyze the search result video titles and determine if they belong to the series "{current_series_name}". Follow these guidelines strictly:

    1. Match the exact title structure of the series examples provided.
    2. Include variations that maintain the core concept of the examples.
    3. Exclude reaction videos unless the series specifically includes reactions.
    4. Be precise in matching. If in doubt, do not include the title.
    5. Consider the themes and topics provided, but prioritize matching the example title structures.

    Respond with a JSON object:
    {{
        "shared_series": [
            {{
                "name": "{current_series_name}",
                "matching_titles": ["list of exact matching titles"]
            }}
        ],
        "is_eligible": true/false (true if at least 3 matching titles),
        "shared_series_count": 1 if matches found, 0 otherwise
    }}

    Ensure that the matching_titles list contains only the exact titles that match the series structure and concept.
    """

    print(f"\n--- AI Prompt ---\n{prompt}")

    response = await generate_ai_response(prompt, max_tokens_to_sample=2000, model="claude-3-haiku-20240307")
    
    print(f"\n--- Raw AI Response ---\n{response}")

    try:
        cleaned_response = clean_claude_response(response)
        result = json.loads(cleaned_response)
        print(f"\n--- Parsed AI Response ---\n{json.dumps(result, indent=2)}")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response from AI: {str(e)}")
        print(f"\n--- Failed to parse JSON response from AI ---\nError: {str(e)}")
        print(f"Raw response: {response}")
        
        # Fallback: Improved string matching
        matching_titles = []
        for title in search_result_titles:
            if any(example.lower() in title.lower() for example in example_titles):
                matching_titles.append(title)
        
        is_eligible = len(matching_titles) >= 3
        shared_series_count = 1 if matching_titles else 0
        
        result = {
            "shared_series": [
                {
                    "name": current_series_name,
                    "matching_titles": matching_titles
                }
            ],
            "is_eligible": is_eligible,
            "shared_series_count": shared_series_count
        }
        
        print(f"\n--- Fallback Result ---\n{json.dumps(result, indent=2)}")

    
    print(json.dumps(result, indent=2))
    return result

client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

async def generate_voice_over(script: str, voice_name: str) -> str:
    voice = voices().get(voice_name)
    if not voice:
        raise ValueError(f"Voice '{voice_name}' not found.")

    audio = client.generate(text=script, voice=voice)
    
    file_name = f"voice_over_{int(time.time())}.mp3"
    file_path = f"/tmp/{file_name}"
    with open(file_path, "wb") as f:
        f.write(audio)

    drive_service = get_drive_service()
    file_metadata = {'name': file_name}
    media = MediaFileUpload(file_path, resumable=True)
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    
    drive_service.permissions().create(fileId=file.get('id'), body={'type': 'anyone', 'role': 'reader'}).execute()
    file = drive_service.files().get(fileId=file.get('id'), fields='webViewLink').execute()
    
    os.remove(file_path)
    
    return file.get('webViewLink')

def clean_claude_response(response_text: str) -> str:
    # Remove any leading/trailing whitespace
    response_text = response_text.strip()

    # Find the JSON part of the response
    start = response_text.find('{')
    end = response_text.rfind('}') + 1
    if start != -1 and end != -1:
        json_str = response_text[start:end]
    else:
        logger.error("No JSON object found in Claude response.")
        return ""

    # Remove any non-JSON characters
    json_str = re.sub(r'[^\x20-\x7E]', '', json_str)

    # Fix common JSON formatting issues
    json_str = json_str.replace("'", '"')  # Replace single quotes with double quotes
    json_str = re.sub(r'(\w+):', r'"\1":', json_str)  # Add quotes to keys

    return json_str



def extract_series_data_fallback(response_text: str) -> List[Dict]:
    series_pattern = r'"name":\s*"([^"]+)".*?"themes":\s*\[(.*?)\]'
    theme_pattern = r'"name":\s*"([^"]+)".*?"topics":\s*\[(.*?)\]'
    topic_pattern = r'"name":\s*"([^"]+)".*?"example":\s*"([^"]+)"'

    series_data = []
    for series_match in re.finditer(series_pattern, response_text, re.DOTALL):
        series_name = series_match.group(1)
        themes_text = series_match.group(2)
        
        themes = []
        for theme_match in re.finditer(theme_pattern, themes_text, re.DOTALL):
            theme_name = theme_match.group(1)
            topics_text = theme_match.group(2)
            
            topics = []
            for topic_match in re.finditer(topic_pattern, topics_text):
                topic_name = topic_match.group(1)
                topic_example = topic_match.group(2)
                topics.append({"name": topic_name, "example": topic_example})
            
            if topics:  # Only add themes with topics
                themes.append({"name": theme_name, "topics": topics})
        
        if themes:  # Only add series with themes
            series_data.append({"name": series_name, "themes": themes})

    return series_data

async def determine_niche(group_id, db):
    video_titles = await db.get_video_titles_for_group(group_id)
    
    if not video_titles:
        logger.warning(f"No video titles found for group {group_id}")
        return "Unknown"

    niche_categories = [
        "Finance", "Technology", "Education", "Entertainment", "Lifestyle", 
        "Marketing", "Crypto", "Real Estate", "Investing", "Side Hustle", 
        "Entrepreneurship", "Personal Finance", "Business", "Vlogging", 
        "Dropshipping", "Affiliate Marketing", "Print on Demand", "Filmmaking",
        "Travel", "Hustling", "Digital Products", "Motherhood", "Archery",
        "Hunting", "Productivity", "Science", "Space", "Geology", "Paleontology",
        "Astronomy", "History", "Politics", "News", "Gaming", "Sports",
        "Fitness", "Cooking", "Fashion", "Beauty", "DIY", "Home Improvement",
        "Gardening", "Pets", "Music", "Art", "Photography", "Writing",
        "Language Learning", "Food", "Wine", "Beer", "Spirits", "Automotive",
        "Motorcycles", "Boats", "Aviation", "Outdoors", "Survival", "Prepping",
        "Minimalism", "Sustainability", "Eco-friendly", "Parenting", "Relationships",
        "Dating", "Wedding", "Divorce", "Legal", "Insurance", "Healthcare",
        "Mental Health", "Spirituality", "Religion", "Philosophy", "Psychology",
        "Sociology", "Anthropology", "Archaeology", "Engineering", "Architecture",
        "Interior Design", "Graphic Design", "Web Design", "UX/UI", "Programming",
        "Data Science", "Artificial Intelligence", "Robotics", "Blockchain",
        "Cybersecurity", "Cloud Computing", "Internet of Things", "Virtual Reality",
        "Augmented Reality", "3D Printing", "Drones", "Electric Vehicles",
        "Renewable Energy", "Space Exploration", "Quantum Computing", "Nanotechnology",
        "Biotechnology", "Genetics", "Neuroscience", "Medicine", "Pharmacology",
        "Nutrition", "Yoga", "Meditation", "Martial Arts", "Dance", "Theater",
        "Cinema", "Literature", "Poetry", "Comedy", "Magic", "Circus", "Festivals",
        "Concerts", "Nightlife", "Bars", "Restaurants", "Cafes", "Street Food",
        "Luxury Travel", "Budget Travel", "Adventure Travel", "Ecotourism",
        "Cultural Tourism", "Religious Tourism", "Medical Tourism", "Space Tourism",
        "Cruise Travel", "Road Trips", "Backpacking", "Camping", "Hiking",
        "Climbing", "Skiing", "Snowboarding", "Surfing", "Scuba Diving",
        "Skydiving", "Paragliding", "Bungee Jumping", "Extreme Sports"
    ]
    
    prompt = f"""Based on the following YouTube video titles, determine the most appropriate niche category from this list:
    {', '.join(niche_categories)}

    Video titles: {', '.join(video_titles[:50])}

    Respond with ONLY the category name that best fits these video titles. If none of the categories fit well, respond with 'Other'.
    """
    
    response = await generate_ai_response(prompt, max_tokens_to_sample=100, model="claude-3-haiku-20240307")
    niche = response.strip()
    
    if niche == 'Other':
        logger.warning(f"AI couldn't determine a specific niche for group {group_id}")
        return "Unknown"
    elif niche not in niche_categories:
        logger.warning(f"AI returned a niche category not in the predefined list: {niche}. Using it anyway.")
    
    logger.info(f"Determined niche for group {group_id}: {niche}")
    return niche
client = AsyncAnthropic()

async def generate_video_titles(
    series: Dict[str, Any], 
    theme: Dict[str, Any], 
    example_titles: List[str], 
    custom_niche: str = None,
    enable_research: bool = False
) -> List[str]:
    # Add custom niche to the prompt if provided
    niche_text = ""
    niche_guidance = ""
    if custom_niche:
        niche_text = f"\nCustom Niche: {custom_niche}"
        niche_guidance = f"""
Additional Custom Niche Guidance:
- Adapt titles to focus on the custom niche: {custom_niche}
- Maintain the same structure but replace theme-specific terms with appropriate terms for {custom_niche}
- Ensure titles sound natural and authentic within the {custom_niche} domain
"""
    
    # Add research content when enabled
    research_content = ""
    if enable_research:
        try:
            logger.info(f"Performing research for titles: {series['name']} + {theme['name']}")
            
            # Get trending videos and extract keywords using the new approach
            from services.youtube_service import get_trending_videos_with_smart_search
            
            # Gather trending topics and keywords
            trend_info = await get_trending_videos_with_smart_search(series, theme, example_titles, custom_niche)
            
            if trend_info:
                research_content = "\n\nCURRENT TRENDING TOPICS (incorporate these into your titles):\n"
                
                # Add trending titles
                if trend_info.get('trending_titles'):
                    research_content += "Top Trending Titles:\n"
                    for i, title in enumerate(trend_info['trending_titles'][:5], 1):
                        research_content += f"   {i}. {title}\n"
                    research_content += "\n"
                
                # Add trending keywords
                if trend_info.get('trending_keywords'):
                    research_content += "Key Trending Keywords (incorporate these where relevant):\n"
                    keywords_text = ", ".join(trend_info['trending_keywords'][:15])
                    research_content += f"   {keywords_text}\n\n"
                    
        except Exception as e:
            logger.error(f"Error performing research for titles: {str(e)}")
            # Continue without research if it fails
    
    prompt = f"""Generate highly interesting, potentially viral YouTube titles based on this series and theme, considering the target audience:

Series: {series['name']}
Theme: {theme['name']}{niche_text}
Average Views: {series.get('avg_views', 0):,.0f}
Video Count: {series.get('video_count', 0)}
Channels: {len(series.get('channels_with_series', []))}
{research_content}

⚠️ CRITICAL REQUIREMENT: ALL TITLES MUST BE UNDER 100 CHARACTERS ⚠️

IMPORTANT VOLUME INSTRUCTION:
- DO NOT include volume numbers (like V83, V1, Volume 5, etc.) in any titles
- If example titles contain volume numbers (e.g., "Dark Conspiracy Theories for Sleep(V83)"), 
  remove the volume portion completely when creating new titles
- Example: "Dark Conspiracy Theories for Sleep(V83)" → "Dark Conspiracy Theories for Sleep"

Example titles:
{json.dumps(example_titles, indent=2)}
{niche_guidance}

1. Title Analysis and Generation:
   - Carefully analyze the example title's structure, style, and content.
   - Identify the exact format: word order, capitalization, and any special characters.
   - For each theme, create 20 new titles that follow the precise structure of the example.
   - Use the video topic as a strict guide for the type of situations to create.
   - 🔴 MANDATORY: Keep ALL titles under 100 characters to comply with YouTube limits.
   - Count the total character length of each title before submitting it.
   - Make titles more edgy and controversial by:
     * Using provocative questions that challenge conventional wisdom
     * Including shocking revelations or unexpected twists
     * Adding elements of mystery or suspense
     * Using power words that evoke strong emotions
     * Creating a sense of urgency or FOMO
     * Implying exclusive or insider information
     * Suggesting controversy or debate
     * Using clickbait elements while staying within YouTube guidelines

2. Creative Adaptation:
   - Maintain the exact sentence structure and tone of the original title.
   - Be creative with the specific situation described, but only within the confines of the theme and video topic.
   - Use similar language and phrasing as the example. Only introduce new vocabulary if it directly relates to the theme and maintains the tone.
   - Ensure the new situations are realistic and plausible within the context of the series. Avoid fantastical or unrealistic scenarios.
   - Add controversial elements by:
     * Challenging common beliefs or assumptions
     * Presenting alternative viewpoints
     * Highlighting unexpected connections
     * Suggesting hidden agendas or secrets
     * Creating tension between opposing ideas

3. Title Structure:
   - Keep the exact same beginning and ending phrases as the example title.
   - Maintain all specific formatting, including capitalization, punctuation, and spacing.
   - Ensure the length of new titles matches the example title as closely as possible but NEVER exceed 100 characters.
   - 🔴 If example titles exceed 100 characters, create shorter versions while preserving key elements.
   - Add controversial elements by:
     * Using question marks to create intrigue
     * Adding exclamation marks for emphasis
     * Using ellipses to suggest more to come
     * Including numbers or statistics for credibility
     * Using brackets or parentheses for additional context

4. Audience and Theme Consideration:
   - Strictly adhere to the provided theme and video topic.
   - Ensure the situations described are realistic and could actually happen in the context of the series.
   - Consider the target audience and what types of content they would expect from this series.
   - Make titles more engaging by:
     * Addressing audience pain points or concerns
     * Creating a sense of community or belonging
     * Suggesting solutions to common problems
     * Implying insider knowledge or expertise
     * Creating a sense of urgency or timeliness

5. Output Format:
Present the generated titles in this exact format, with no additional explanation or commentary:
[New Title 1]
[New Title 2]
...
[New Title 20]

6. Final Check:
   - Verify that each new title follows the exact structure, formatting, and style of the example.
   - Ensure all situations described are realistic and plausible within the series context.
   - Confirm that each title directly relates to the given theme and video topic.
   - Double-check that no fantastical or impossible scenarios have been introduced.
   - 🔴 COUNT CHARACTERS: Verify EVERY title is under 100 characters. Remove any that exceed this limit.
   - Ensure controversial elements are:
     * Within YouTube community guidelines
     * Not misleading or false
     * Relevant to the content
     * Appropriate for the target audience
     * Balanced with credibility

Always ask yourself: 
1. "Does this title maintain the exact style and structure of the original?"
2. "Is this scenario realistic and plausible within the context of the series?"
3. "Does this title directly relate to the given theme and video topic?"
4. "Is this title under 100 characters in length?"
5. "Is this title controversial enough to drive clicks while staying within guidelines?"
{f'6. "Does this title effectively incorporate the {custom_niche} niche?"' if custom_niche else ""}

If the answer to any of these questions is "no," revise the title immediately.

Remember: Provide only the generated titles in the specified format. Do not include any explanations, analyses, or additional comments in your output."""

    system_message = """You are a YouTube title generator specializing in creating engaging, viral-worthy titles that precisely match the style of provided examples. Your task is to analyze the given series, themes, and example titles, then generate new titles that maintain the exact same structure while being creative within that framework.

⚠️ CRITICAL REQUIREMENT: ALL TITLES MUST BE UNDER 100 CHARACTERS ⚠️
This is a strict YouTube platform limitation. Titles exceeding 100 characters will be rejected.

IMPORTANT VOLUME INSTRUCTION:
- DO NOT include volume numbers (like V83, V1, Volume 5, etc.) in any titles
- If example titles contain volume numbers (e.g., "Dark Conspiracy Theories for Sleep(V83)"), 
  remove the volume portion completely when creating new titles
- Example: "Dark Conspiracy Theories for Sleep(V83)" → "Dark Conspiracy Theories for Sleep"

1. Title Analysis and Generation:
   - Carefully analyze the example title's structure, style, and content.
   - Identify the exact format: word order, capitalization, and any special characters.
   - For each theme, create 20 new titles that follow the precise structure of the example.
   - Use the video topic as a strict guide for the type of situations to create.
   - 🔴 MANDATORY: Keep ALL titles under 100 characters to comply with YouTube limits.
   - Count the total character length of each title before submitting it.
   - Make titles more edgy and controversial by:
     * Using provocative questions that challenge conventional wisdom
     * Including shocking revelations or unexpected twists
     * Adding elements of mystery or suspense
     * Using power words that evoke strong emotions
     * Creating a sense of urgency or FOMO
     * Implying exclusive or insider information
     * Suggesting controversy or debate

2. Creative Adaptation:
   - Maintain the exact sentence structure and tone of the original title.
   - Be creative with the specific situation described, but only within the confines of the theme and video topic.
   - Use similar language and phrasing as the example. Only introduce new vocabulary if it directly relates to the theme and maintains the tone.
   - Ensure the new situations are realistic and plausible within the context of the series. Avoid fantastical or unrealistic scenarios.

3. Title Structure:
   - Keep the exact same beginning and ending phrases as the example title.
   - Maintain all specific formatting, including capitalization, punctuation, and spacing.
   - Ensure the length of new titles matches the example title as closely as possible but NEVER exceed 100 characters.
   - 🔴 If example titles exceed 100 characters, create shorter versions while preserving key elements.

4. Audience and Theme Consideration:
   - Strictly adhere to the provided theme and video topic.
   - Ensure the situations described are realistic and could actually happen in the context of the series.
   - Consider the target audience and what types of content they would expect from this series.

5. Output Format:
Present the generated titles in this exact format, with no additional explanation or commentary:
[New Title 1]
[New Title 2]
...
[New Title 20]

6. Final Check:
   - Verify that each new title follows the exact structure, formatting, and style of the example.
   - Ensure all situations described are realistic and plausible within the series context.
   - Confirm that each title directly relates to the given theme and video topic.
   - Double-check that no fantastical or impossible scenarios have been introduced.
   - 🔴 COUNT CHARACTERS: Verify EVERY title is under 100 characters. Remove any that exceed this limit.

Always ask yourself: 
1. "Does this title maintain the exact style and structure of the original?"
2. "Is this scenario realistic and plausible within the context of the series?"
3. "Does this title directly relate to the given theme and video topic?"
4. "Is this title under 100 characters in length?"

If the answer to any of these questions is "no," revise the title immediately.

When trending topic research is provided:
- Incorporate trending topics naturally into the title structure
- Use trending keywords that fit the established format
- Add elements of timeliness (recent reveals, discoveries, events)
- Keep the core structure intact while modernizing the specific topic
- Blend the familiar title pattern with current interests


Remember: Provide only the generated titles in the specified format. Do not include any explanations, analyses, or additional comments in your output."""

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            temperature=0.6,
            system=system_message,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        # Handle Claude 4 "refusal" stop reason gracefully
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason is None and hasattr(response, "content") and isinstance(response.content, list):
            # Try to get stop_reason from the first message if present (Claude API sometimes nests it)
            stop_reason = getattr(response.content[0], "stop_reason", None)
        if stop_reason == "refusal":
            logger.error("Claude refused to generate titles due to safety or content restrictions.")
            return ["Claude refused to generate titles for this prompt due to safety or content restrictions."]
        content = response.content[0].text if isinstance(response.content, list) else response.content
        titles = parse_titles_from_response(content)
        
        # Log any titles that exceed limit but don't truncate them
        for title in titles:
            if len(title) > 100:
                logger.warning(f"Title exceeds 100 character limit: '{title}' ({len(title)} chars)")
        
        try:
            # Get existing titles for this series/theme
            existing_titles = await db.get_existing_titles(
                series_name=series['name'],
                theme_name=theme['name']
            )
            
            # Filter out any duplicates from existing titles
            new_titles = [title for title in titles if title not in existing_titles]
        except Exception as e:
            logger.warning(f"Failed to check for existing titles: {str(e)}")
            new_titles = titles  # Fall back to all generated titles if db check fails
        
        return new_titles[:20]  # Return up to 20 unique titles
    except Exception as e:
        logger.error(f"Error generating video titles: {str(e)}")
        return [f"Error generating title for {series['name']} - {theme['name']}"]

async def get_example_titles(group_id: str, series_name: str, theme_name: str) -> List[str]:
    return await db.get_example_titles(group_id, series_name, theme_name)

def parse_titles_from_response(response_content: Union[str, List[str]]) -> List[str]:
    if isinstance(response_content, str):
        # Split the content by newlines and remove any empty lines or lines containing "Series:" or "Theme:"
        lines = [line.strip() for line in response_content.split('\n') 
                if line.strip() and not line.startswith(('Series:', 'Theme:'))]
        return lines  # Remove the limit here to get all titles
    elif isinstance(response_content, list):
        return [str(item).strip() for item in response_content]
    else:
        return []

import anthropic

async def breakdown_script(series_name: str, theme_name: str, transcripts: List[Dict[str, Union[str, float]]], video_durations: List[float], video_titles: List[str], video_descriptions: List[str]) -> str:
    client = Anthropic()
    
    # Your existing system and assistant messages remain unchanged
    system_message = """You are an AI assistant specializing in analyzing video series structures and writing styles. Your task is to process the given series name, theme, and provided transcript(s), then generate a comprehensive template that can be applied to future videos in the same series. This template should maintain the structure, style, tone, AND writing style of the series while allowing for different video topics.

Your analysis must include: Do not add any elements or recommendations that are not directly observed in the transcript(s). Provide specific examples, quotes, and timestamps from the transcript(s) to support each point in your analysis, especially in the script templates and other detailed sections

CRITICAL REQUIREMENT: ALL segments MUST be 10 minutes (600 seconds) or LESS in duration. NEVER create segments longer than 10 minutes, no matter what. If you identify a segment longer than 10 minutes, you MUST split it into multiple smaller segments with logical breakpoints. This is a hard constraint that cannot be violated under any circumstances.

1. A detailed Video Structure breakdown with precise timestamps and durations.
2. A comprehensive Segment Outline Template covering all identified segments, including their internal structure and plot points.
3. A list of 3-5 Transition Techniques with specific examples and timestamps.
4. A list of 3-5 Recurring Elements with their frequency and context.
5. A complete Script Template corresponding to the Segment Outline Template, with specific examples and calculated durations for each segment.
6. Clip-Reactive Analysis: Determine if the series is clip-reactive (reacting to specific clips) or follows a structured documentary format. Look for short segments, quick transitions, frequent visual references, and a conversational tone that reacts to the content. If the video is clip-reactive, set "is_clip_reactive" to true, otherwise set it to false.
7. Tone and Style: Analyze the overall tone (e.g., conversational, formal, humorous), language style (e.g., technical, casual, academic), and level of formality used in the series. Provide specific examples from the transcript(s) to support your analysis.
8. Additional Observations: Note any other notable patterns, techniques, or characteristics that could aid in maintaining consistency with the series, such as recurring visual elements, editing patterns, or narrative devices.
9. Video Title Influence: Analyze how the specific video title impacts the structure, content, and flow of the video. Identify any patterns or adjustments made to accommodate the title's premise or topic. Provide examples from the transcript(s) to illustrate this influence.
10. WRITING STYLE ANALYSIS: Deep analysis of the narrative writing style, including:
    - Sentence structure patterns (short vs long sentences, complex vs simple)
    - Vocabulary choices and word frequency (formal vs informal, technical vs casual)
    - Narrative pacing and rhythm (how information is revealed, built up, or delivered)
    - Emotional tone and intensity variations throughout segments
    - Use of rhetorical devices (repetition, alliteration, metaphors, analogies)
    - Dialogue patterns and character voice consistency
    - Transitional phrases and connective language
    - Climactic moments and how tension is built/released
    - Descriptive language patterns and sensory details
    - Humor, irony, or other stylistic elements
    - Cultural references and audience-specific language
    - Callbacks, foreshadowing, or narrative threading techniques

For list-based or segmented video structures:
1. Analyze the transcript(s) to identify if the video follows a list-based or segmented structure, where distinct topics or segments are presented sequentially.
2. If a list-based structure is detected, identify the overall introduction (if any) and the recurring pattern for each list item or segment.
3. Create a template for the recurring segment, including:
   - Introduction format (e.g., "Item X: [Topic]")
   - Internal structure (explanation, examples, analysis, etc.)
   - Transition to the next segment
4. Use placeholders like [ITEM X] or [SEGMENT X] to represent each distinct topic or segment in the template.
5. Include specific examples from the transcript(s) to illustrate the structure and style of each segment.
6. Ensure that the total duration and individual segment durations match the transcript(s) precisely.
7. Note if there is a consistent conclusion segment after all list items or segments have been covered.
8. Analyze how the video title shapes the overall introduction and framing of the list or segments. Provide examples from the transcript(s) to illustrate how the title is incorporated into the setup and transitions between segments.


For educational, explainer, or documentary videos:
1. Identify the overall structure (introduction, main topics/sections, conclusion).
2. For each main topic or section, break down the internal structure and key points.
3. Use placeholders (e.g., [Topic X], [Key Point Y]) to make the template adaptable.
4. Include brief descriptions of the content or purpose of each key point.
5. Note transitions between major topics or sections.
6. Include the approximate duration of each major topic or section.
7. Examine how the video title influences the overall topic selection, framing, and introduction of the main sections or topics covered. Provide examples from the transcript(s) to illustrate how the title is incorporated into the setup and transitions between sections.


For narrative videos (sketches, web series):
1. Identify the overall story structure (setup, inciting incident, rising action, climax, falling action, resolution).
2. Break down the internal structure of each major story beat or plot point.
3. Use placeholders (e.g., [Character], [Conflict], [Resolution]) to make the template adaptable.
4. Include brief descriptions of the content or purpose of each plot point.
5. Note transitions between major story beats or plot points.
6. Include the approximate duration of each major story beat or plot point.
7. Analyze how the video title shapes the overall premise, character introductions, and initial setup of the narrative. Provide examples from the transcript(s) to illustrate how the title is incorporated into the story's setup and early plot points.


For commentary or scripted videos:
1. Identify the overall structure (introduction, main topics/segments, conclusion).
2. For each main topic or segment, break down the internal structure and key points.
3. Use placeholders (e.g., [Topic X], [Key Point Y]) to make the template adaptable.
4. Include brief descriptions of the content or purpose of each key point.
5. Note transitions between major topics or segments.
6. Include the approximate duration of each major topic or segment.
7. Examine how the video title influences the overall topic selection, framing, and introduction of the main segments or commentary points. Provide examples from the transcript(s) to illustrate how the title is incorporated into the setup and transitions between segments.

The goal is to create a flexible template that captures the essence of how information is presented in the specific video format, while allowing for different topics or segments to be inserted into the template structure.
"""


    assistant_message = """You are an AI assistant specializing in analyzing video series structures and writing styles. Your task is to process the given series name, theme, and provided transcript(s), then generate a comprehensive template that can be applied to future videos in the same series. This template should maintain the structure, style, tone, AND writing style of the series while allowing for different video topics.

CRITICAL REQUIREMENT: ALL segments MUST be 10 minutes (600 seconds) or LESS in duration. NEVER create segments longer than 10 minutes, no matter what. If you identify a segment longer than 10 minutes, you MUST split it into multiple smaller segments with logical breakpoints. This is a hard constraint that cannot be violated under any circumstances.

IMPORTANT: When providing examples from transcripts, ALWAYS replace any specific channel names with the placeholder [CHANNEL_NAME]. Never use the actual channel name from the transcript. For example, instead of "Welcome to Morpheus Realm", use "Welcome to [CHANNEL_NAME]" or "Welcome to [HOST_NAME]".

Script Elements:
• Channel Greeting: "Welcome to [HOST_NAME] where..."


Your analysis should be based solely on the information present in the provided transcript(s). Do not add any speculative elements or recommendations that are not directly supported by the transcript(s).

10. WRITING STYLE ANALYSIS:
Analyze the deep writing style and narrative techniques used in the transcript(s). This is CRITICAL for maintaining authentic voice in future scripts. Include:

a) Sentence Structure Analysis:
- Average sentence length and complexity
- Use of short, punchy sentences vs. long, flowing sentences
- Sentence variety patterns (simple, compound, complex)
- Use of fragments, run-ons, or other stylistic choices
- Rhythm and cadence patterns

b) Vocabulary and Language Patterns:
- Formal vs. informal language balance
- Technical terminology usage and frequency
- Slang, colloquialisms, or regional language
- Word choice patterns (concrete vs. abstract, emotional vs. neutral)
- Repetition of specific words or phrases
- Use of intensifiers, qualifiers, or hedging language

c) Narrative Flow and Pacing:
- How information is revealed and built up
- Use of suspense, foreshadowing, or dramatic reveals
- Pacing variations (fast vs. slow sections)
- Emotional intensity curves throughout segments
- How transitions affect narrative momentum

d) Rhetorical and Stylistic Devices:
- Metaphors, similes, and analogies
- Alliteration, assonance, or other sound patterns
- Repetition for emphasis or rhythm
- Parallel structure or antithesis
- Irony, sarcasm, or humor patterns
- Direct address to audience patterns

e) Emotional and Tone Patterns:
- Emotional vocabulary and intensity
- Tone shifts and their triggers
- Use of humor, seriousness, or mixed tones
- How emotions are conveyed through language choice
- Audience emotional manipulation techniques

f) Character Voice and Dialogue:
- Distinctive speech patterns for different characters
- Dialogue tags and attribution patterns
- Character-specific vocabulary or phrases
- How character voices differ from narrator voice
- Consistency in character voice throughout

g) Cultural and Audience-Specific Elements:
- References to specific cultural touchstones
- Audience-specific language or assumptions
- In-jokes or community-specific references
- How the content assumes audience knowledge
- Accessibility vs. insider language balance

h) Structural Writing Techniques:
- Callbacks and references to earlier content
- Foreshadowing and setup-payoff patterns
- Narrative threading across segments
- How information is organized and presented
- Use of lists, examples, or evidence

i) Sensory and Descriptive Language:
- Visual, auditory, or other sensory details
- Specificity vs. generality in descriptions
- Use of vivid imagery or abstract concepts
- How descriptions serve narrative function
- Balance of showing vs. telling

j) Engagement and Audience Interaction:
- Direct questions or calls to action
- Hypothetical scenarios or "what if" statements
- Personal anecdotes or examples
- How the content maintains audience attention
- Interactive elements or participatory language

For each of these categories, provide:
- Specific examples from the transcript(s) with timestamps
- Frequency and context of usage
- How these elements contribute to the overall style
- Patterns that should be replicated in future scripts

For each series and theme, provide the following outputs:

1. Video Structure:
Present this as a list of segments: Time | Segment | Content | Duration
Analyze the transcript(s) to identify the key segments that form the structure of the series. Calculate and include the precise duration of each segment based on the transcript timestamps. Ensure the structure can be applied to different topics within the same theme, but only use information directly observed in the transcript(s).
if you notice that the video is basically just a list of items, give us the structure like intro, list 1, list 2, list 3, list 4, outro (if an outro exists.)

2. Segment Outline Template:
When creating the segment outline:
1. Identify the overall structure (intro, main incidents, secondary incidents, conclusion, etc.).
2. For each main segment type, break down the internal structure and plot points.
3. Use consistent placeholders (e.g., [Streamer], [Rapper]) to make the template adaptable.
4. Include brief descriptions of the content or purpose of each plot point.
5. Highlight any recurring patterns or elements within segments.
6. Note transitions between major segments.
7. Include the approximate duration of each major segment type.

Ensure that the outline captures not just the overall video structure, but also the narrative flow within each significant segment type. This approach should reveal how individual stories or incidents are typically presented and developed throughout the video.

Make sure to include the duration of each segment.

Example format:

a. Introduction (Duration):
   - [Plot point 1]
   - [Plot point 2]

b. Main Segment Structure (Average duration):
   - [Plot point 1] 
   - [Plot point 2]
   - ...
   - [Plot point 6-8]

c. Transition (Duration)

[Continue for all identified segment types]

3. Transition Techniques:
List 3-5 transition techniques observed in the transcript(s) that are likely to be consistent across the series. Include specific examples and timestamps from the transcript(s) for each technique.

4. Recurring Elements:
List 3-5 recurring elements or phrases that are characteristic of the series, based on the transcript(s). These should be elements that can be applied across different topics within the theme. Include the frequency and context of each element's appearance in the transcript(s).

5. Script Template:
Create a script template corresponding to the Segment Outline Template. 
Provide general script elements and placeholders that can be adapted for different topics within the series. Include specific examples from the transcript(s) for each segment and the calculated duration based on the transcript(s).

When creating the script template:
1. Include all major segment types identified in the Segment Outline Template.
2. For each segment, provide a clear and concise content description.
3. List 4-6 specific script elements that capture the narrative flow of the segment.
4. Use placeholders (e.g., [Streamer], [Rapper], [quote]) to make the template adaptable.
5. Include transition elements between segments where appropriate.
6. Provide specific examples or phrasings from the transcript(s) to illustrate the style.
7. Ensure the duration for each segment matches the analysis from the Video Structure section.
8. Document exact hook/intro phrasing and structure with timestamps
9. Note any recurring phrases, expressions or linguistic patterns
10. Capture tone shifts and pacing changes within segments
11. WRITING STYLE GUIDELINES: Include specific writing style instructions for each segment:
    - Sentence structure patterns to follow
    - Vocabulary choices and tone requirements
    - Emotional intensity and pacing guidelines
    - Rhetorical devices to employ
    - Character voice consistency requirements
    - Transitional language patterns
    - Engagement techniques to use
    - Descriptive language requirements
    - Cultural reference patterns
    - Callback and foreshadowing techniques

Example format:

Segment: Introduction/Hook
Content: Channel greeting, topic setup, and engagement hook
Word Count Target: [XXX] words
Script Elements:
• Channel Greeting: "[Exact channel greeting phrase]"
• Topic Introduction: "Today we're looking at [Number] [Subject] who [Action]"
• Hook Setup: "[Specific hook format from transcript]"
• Teaser Elements: "[Example 1], [Example 2]..."
• Engagement Question: "[Question format used]"
• Transition to Main Content: "[Transition phrase]"
Duration: [XX:XX]

Writing Style Guidelines:
• Sentence Structure: [Short punchy sentences vs. flowing complex sentences]
• Vocabulary Level: [Formal/technical vs. casual/conversational]
• Emotional Tone: [Intensity level and emotional vocabulary patterns]
• Rhetorical Devices: [Specific devices used: repetition, alliteration, metaphors]
• Pacing: [Fast-paced vs. measured delivery patterns]
• Character Voice: [How narrator voice differs from character voices]
• Engagement Techniques: [Direct questions, hypotheticals, callbacks]
• Descriptive Language: [Specificity level and sensory detail patterns]
• Cultural References: [Type and frequency of references]
• Transitional Language: [Specific phrases and connective patterns]

For Clip-Reactive Content:
Segment: Opening Clip/Hook
Clip Duration: [XX:XX]
Commentary Duration: [XX:XX]
Script Elements:
• Clip Introduction: "[How the clip is introduced]"
• Key Commentary Points: "[Main reactions/observations]"
• Viewer Engagement: "[Questions/comments to engage viewers]"
• Transition: "[How to move to next clip]"
Total Duration: [XX:XX]

Writing Style Guidelines:
• Reaction Language: "[Specific reaction vocabulary and patterns]"
• Commentary Pacing: "[How commentary flows with visual content]"
• Engagement Style: "[Direct vs. observational commentary patterns]"
• Emotional Responses: "[How emotions are expressed during reactions]"
• Transitional Language: "[Specific phrases for moving between clips]"

Note: For clip-reactive content, focus on:
- Duration-based timing rather than word count
- Natural reaction patterns
- Commentary that enhances but doesn't overshadow clips
- Smooth transitions between clips
- Maintaining viewer engagement through commentary style

[Continue with Main Segment, Secondary Incident, etc., following the same structure]

For listicle-format videos:
   - Analyze the transcripts to identify the recurring structure and patterns for list items
   - Create a comprehensive template that includes:
     a. Introduction segment with brief setup for the overall video topic
     b. Recurring list item structure with:
        - Introduction: "[ITEM X]: [Topic/Premise]" with specific timing
        - Explanation: Clear explanation of the core concept
        - Analysis: Examination of implications, theories, or principles
        - Counterpoints: Presentation of critiques or opposing viewpoints
        - Broader Context: Connections to larger themes or psychological impact
        - Conclusion: Summary of key points and final perspective
        - Transition: Smooth transition to the next item/segment
     c. Conclusion segment with overall summary or final thoughts
   - Use placeholders like [ITEM X] and [Topic/Premise] for adaptable content
   - Include specific examples from the transcripts to guide style and content
   - Ensure precise timing for each segment based on transcript analysis
   - Maintain consistent structure while allowing for topic variation
   - WRITING STYLE ANALYSIS: For each list item, analyze:
     - How each item is introduced and framed
     - Vocabulary patterns specific to list item structure
     - Transitional language between list items
     - Emotional intensity variations across items
     - Rhetorical devices used in list item explanations
     - Character voice consistency throughout list items
     - Engagement techniques specific to list format
     - Descriptive language patterns in list item content
     - Cultural references and their placement in list structure
     - Callback patterns between list items

When processing the information, focus on creating a template that captures the essence of the series and can be easily applied to different video topics within the same theme. Use placeholder text (e.g., [Subject], [Event], [Date]) to create a flexible template.

CRITICAL: The writing style analysis is essential for maintaining authentic voice. Pay special attention to:
- How the original writers construct sentences and paragraphs
- The specific vocabulary and language patterns they use
- Emotional and tonal variations throughout the content
- Rhetorical devices and stylistic choices
- Character voice consistency and differentiation
- Narrative flow and pacing techniques
- Engagement and audience interaction patterns

Ensure that all sections are filled out completely, providing a comprehensive template that maintains the series' structure, timing, AND writing style while allowing for topic variation. Pay particular attention to the timing and duration of segments, using the transcript timestamps for precise calculations.

Use only the information present in the provided transcript(s) as the basis for your analysis. Do not add any elements or recommendations that are not directly observed in the transcript(s). Provide specific examples, quotes, and timestamps from the transcript(s) to support each point in your analysis, especially in the script templates and other detailed sections.

The goal is to create a template that not only captures the structural elements but also the authentic writing voice, narrative style, and linguistic patterns that make the original content compelling and distinctive."""

    # Process each transcript individually
    transcript_chunks = [[t] for t in transcripts]
    logger.info(f"Total transcript chunks: {len(transcript_chunks)}")
    all_breakdowns = []
    
    for i, chunk in enumerate(transcript_chunks):
        try:
            # Add video title and description to context
            title_line = ""
            description_line = ""
            if video_titles and i < len(video_titles):
                title_line = f"Video Title: {video_titles[i]}\n"
            if video_descriptions and i < len(video_descriptions):
                description_line = f"Video Description: {video_descriptions[i]}\n"
            
            # Extract transcript and duration
            transcript_data = chunk[0]
            transcript_text = transcript_data.get("transcript", "")
            video_duration = video_durations[i]
            potential_video_formats = [
                "Educational", "Narrative", "Commentary", "Listicle", "Gaming Content - Roleplay",
                "Challenge videos", "Pranks", "Gaming content (Let's Plays, walkthroughs)",
                "Reaction videos", "Vlogs", "Unboxing videos", "Q&A sessions",
                "Listicle videos (minimal commentary)", "Unscripted interviews",
                "Unscripted commentary", "Live streams", "Explainer videos", "Documentary",
                "Video essays", "Conspiracy theory videos", "Sketches", "Web series",
                "Scripted videos", "Product reviews", "Tutorials", "Gameplay videos",
                "Podcasts", "Talk shows", "News reports", "Interviews", "Animated videos",
                "Music videos", "Short films", "Commercials", "Trailers",
                "Behind-the-scenes videos", "Cooking shows", "Travel vlogs",
                "Comedy sketches", "Parodies", "Rants", "Storytimes", "Hauls",
                "Makeup tutorials", "Product demonstrations", "Fitness videos",
                "DIY videos", "Craft tutorials", "Unboxing videos", "Tech reviews",
                "Gear reviews", "Comparison videos", "Reaction videos", "Challenges",
                "Pranks", "Experiments", "Livestreams", "Podcasts", "Talk shows",
                "Debates", "Panel discussions", "Webinars", "Lectures", "Presentations",
                "Conferences", "Workshops", "Masterclasses", "Courses", "Tutorials",
                "How-to videos", "Guides", "Walkthroughs", "Playthroughs", "Speedruns",
                "Esports events", "Game reviews", "Game analysis", "Game lore videos",
                "Fan theories", "Retrospectives", "Commentaries"
            ]

            user_message = f"""Series: {series_name}
            Theme: {theme_name}
            {title_line}
            {description_line}
            Important Context:
            - Analyzing {len(transcripts)} videos from the same series & theme
            - Current transcript breakdown: {i + 1} of {len(transcript_chunks)}
            - Video Duration: {video_duration} seconds
            - Purpose: Looking for common patterns, structures, timing, and storytelling elements
            - Potential video formats to consider: {', '.join(potential_video_formats)}

            Transcript Analysis for "{video_titles[i]}":
            {transcript_text}

            Instructions:
            1. Carefully review the provided transcript(s) and identify the overall video structure and format based on the content and flow of information, considering the potential video formats provided.
            2. Refer to the specific instructions in the system message for the identified video format (e.g., list-based, educational, narrative, commentary).
            3. Follow those instructions to create a comprehensive Segment Outline Template, Script Template, and other required analyses.
            4. Use the provided examples and placeholders to ensure the templates are adaptable for different topics within the same series and theme.
            5. Include specific quotes, timestamps, and examples from the transcript(s) to support your analysis and illustrate the structure, style, and tone of the series.
            6. Pay close attention to the timing and duration of segments, using the transcript timestamps for precise calculations.
            7. Note any recurring elements, transition techniques, or other patterns that are characteristic of the series and should be maintained in future videos.
            8. Ensure your analysis and templates accurately capture the essence of how information is presented in this series, while allowing for topic variation.
            9. CRITICAL: Deeply analyze the writing style, narrative voice, and linguistic patterns that make this content distinctive and engaging.
            10. Pay special attention to sentence structure, vocabulary choices, emotional tone, rhetorical devices, and character voice consistency.
            11. Document specific writing techniques, pacing patterns, and engagement strategies that should be replicated.

            Remember, your goal is to create a flexible template that can be used to maintain consistency and quality for future videos in the same series and theme. Use the provided context, instructions, and examples to guide your analysis and template creation.
            """
            response = await asyncio.to_thread(
                client.messages.create,
                model="claude-3-7-sonnet-20250219",
                max_tokens=10000,
                temperature=0.2,
                system=system_message,
                messages=[
                    {"role": "assistant", "content": assistant_message},
                    {"role": "user", "content": user_message}
                ]
            )
            
            all_breakdowns.append(response.content[0].text)
            logger.info(f"Chunk {i + 1} processed successfully.")
        except Exception as e:
            logger.error(f"Error generating script breakdown for transcript {i+1}: {str(e)}", exc_info=True)
            continue
    
    # Merge individual transcript analyses
    if len(all_breakdowns) > 1:
        try:
            merge_message = f"""Combine these {len(all_breakdowns)} transcript breakdowns for {series_name} - {theme_name} into one fully fleshed out, comprehensive analysis that reflects all the details (including timing, segment breakdowns, and storytelling elements) from each video:
            
Breakdowns:
{'-' * 40}
""" + f"\n{'-' * 40}\n".join(all_breakdowns)
            
            final_response = await asyncio.to_thread(
                client.messages.create,
                model="claude-3-7-sonnet-20250219",
                max_tokens=10000,
                temperature=0.4,
                system=system_message,
                messages=[
                    {"role": "assistant", "content": assistant_message},
                    {"role": "user", "content": merge_message}
                ]
            )
            
            final_breakdown = final_response.content[0].text
            logger.info("Successfully merged chunks.")
        except Exception as e:
            logger.error(f"Error merging breakdowns: {str(e)}", exc_info=True)
            final_breakdown = all_breakdowns[0] if all_breakdowns else ""
    else:
        final_breakdown = all_breakdowns[0] if all_breakdowns else ""
    
    # Determine clip-reactivity
    is_clip_reactive = "false"
    if "is_clip_reactive: true" in final_breakdown.lower():
        is_clip_reactive = "true"
    
    logger.info(f"Final breakdown is_clip_reactive: {is_clip_reactive}")
    final_breakdown = f'{{"is_clip_reactive": {is_clip_reactive}, "script_breakdown": {final_breakdown}}}'
    
    return final_breakdown

async def chunk_transcripts(transcripts) -> List[List[Dict[str, Union[str, float]]]]:
    """Split transcripts into chunks that won't exceed token limits"""
    CHARS_PER_TOKEN = 4  # Rough estimate of tokens per character
    
    # Ensure transcripts is a list of dictionaries
    if isinstance(transcripts, str):
        transcripts = [{'text': transcripts}]
    elif isinstance(transcripts, list):
        if all(isinstance(t, str) for t in transcripts):
            transcripts = [{'text': t} for t in transcripts]
    
    transcript_chunks = []
    current_chunk = []
    current_length = 0
    
    for transcript in transcripts:
        # Ensure we're working with a dictionary
        if isinstance(transcript, str):
            transcript = {'text': transcript}
            
        text = transcript.get('text', '')
        estimated_tokens = len(text) / CHARS_PER_TOKEN
        
        if current_length + estimated_tokens > 8000:
            transcript_chunks.append(current_chunk)
            current_chunk = []
            current_length = 0
            
        current_chunk.append(transcript)
        current_length += estimated_tokens
        
    if current_chunk:
        transcript_chunks.append(current_chunk)
        
    return transcript_chunks

async def analyze_thumbnail(series: Dict[str, Any], theme: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"""
    Given the following series and theme:
    Series: {series['name']}
    Theme: {theme['name']}

    Analyze and recommend elements for an effective thumbnail design. Consider the genre, target audience, and current YouTube trends.

    Format your response as a Python dictionary with the following structure:
    {{
        "recommended_elements": [
            "Element 1",
            "Element 2",
            ...
        ],
        "color_scheme": ["#ColorHex1", "#ColorHex2", "#ColorHex3"],
        "text_placement": "Description of text placement"
    }}
    """
    response = await generate_ai_response(prompt, max_tokens_to_sample=2000)
    try:
        analysis = eval(response)
        if not isinstance(analysis, dict) or not all(key in analysis for key in ["recommended_elements", "color_scheme", "text_placement"]):
            raise ValueError("Invalid response format")
        return analysis
    except Exception as e:
        logger.error(f"Error processing AI response for thumbnail analysis: {str(e)}")
        return {
            "recommended_elements": [f"Error analyzing thumbnail for {series['name']} - {theme['name']}"],
            "color_scheme": ["#000000"],
            "text_placement": "Error determining text placement"
        }


async def generate_plot_outline(
    title: str, 
    guidelines: str, 
    series: Dict[str, Any], 
    theme: Dict[str, Any], 
    video_length: float, 
    customization: Dict[str, Any] = None,
    enable_research: bool = False,
    max_retries: int = 5
) -> str:  # Update return type to just str
    # Add research capability
    research_data = ""
    research_articles = []  # To return for full script
    
    if enable_research:
        try:
            logger.info(f"Performing fresh research for plot outline: {title}")
            
            # Create focused search based on title and series/theme
            search_query = f"{title} {series['name']} {theme['name']} details facts information"
                
            # Get research specifically for plot structure
            research_results = await research_with_gemini(
                search_query, 
                research_type="plot",
                max_results=3
            )
            
            # Format research for Claude
            if research_results:
                logger.info(f"Found {len(research_results)} research articles for plot outline")
                
                # Process results for plot structure
                research_data = "\n\n## CURRENT RESEARCH FINDINGS (incorporate these facts):\n\n"
                
                for i, result in enumerate(research_results, 1):
                    source_title = result.get('source_title', '')
                    key_facts = result.get('key_facts', [])
                    quote = result.get('quote', '')
                    segment_ideas = result.get('segment_suggestions', [])
                    
                    research_data += f"### Source {i}: {source_title}\n\n"
                    
                    # Add key facts
                    if key_facts:
                        research_data += "Key Facts:\n"
                        for fact in key_facts:
                            research_data += f"- {fact}\n"
                        research_data += "\n"
                    
                    # Add quote
                    if quote:
                        research_data += f"Quote: \"{quote}\"\n\n"
                    
                    # Add segment ideas
                    if segment_ideas:
                        research_data += "Segment Ideas:\n"
                        for idea in segment_ideas:
                            research_data += f"- {idea}\n"
                        research_data += "\n"
                    
                    # Save for returning to full script
                    research_articles.append({
                        'title': source_title,
                        'url': result.get('url', ''),
                        'key_facts': key_facts,
                        'quote': quote
                    })
        except Exception as e:
            logger.error(f"Error performing research for plot outline: {str(e)}")
            # Continue without research if it fails

    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    # Convert video_length to a formatted string for better clarity
    duration_str = ""
    if video_length >= 60:
        hours = int(video_length // 60)
        minutes = video_length % 60
        duration_str = f"{hours}h{minutes:02.0f}m" if minutes else f"{hours}h"
    elif video_length >= 1:
        duration_str = f"{video_length:.2f}m"
    else:
        duration_str = f"{video_length * 60:.0f}s"

    logger.info(f"Starting plot outline generation for title: {title}, series: {series['name']}, theme: {theme['name']}")
    logger.debug(f"Video length: {duration_str}")
    logger.debug(f"Guidelines excerpt: {guidelines[:100]}...")

    system_message = """You are an AI assistant specializing in creating comprehensive, production-ready plot outlines for video content. Your primary goal is to generate a clear, time-segmented plot outline that strictly adheres to the provided series guidelines, maintaining the structure, tone, style, and pacing of the original series, while offering practical guidance for content creators.

    Follow these steps: DO NOT use generic placeholders like "[Continue with similar detailed breakdowns for remaining segments...]". Generate unique content for each segment.

    1. Thoroughly analyze the provided series guidelines, paying close attention to the "Segment Outline Template" section, as this will play a major role in shaping the structure and format of the plot outline.

    2. Create a detailed plot outline using the following format:

Video Title: [Title]
Total Duration: [Duration in H:MM:SS format] ([Duration] minutes)

Video Structure: 
[If applicable: Based on the example timeline patterns and scaled for duration, maintaining similar ratios:]

1. [Segment Name] (HH:MM:SS - HH:MM:SS, Duration: HH:MM:SS)
2. [Segment Name] (HH:MM:SS - HH:MM:SS, Duration: HH:MM:SS)

You MUST list out EVERY SINGLE SEGMENT in the Video Structure section with exact timestamps
    2. If the video is 2 hours long, list out ALL segments for the full 2 hours
    3. If there are 26 segments, write out ALL 26 segments
    4. NEVER use phrases like:
       ❌ "[Continue pattern for remaining segments...]"
       ❌ "Would you like me to continue?"
       ❌ "[Similar segments until HH:MM:SS]"
    5. NO SHORTCUTS OR PLACEHOLDERS ALLOWED

Detailed Segment Breakdown:

IMPORTANT: For the Detailed Segment Breakdown section, ONLY provide detailed breakdowns for:
1. The first example of each UNIQUE segment structure or format
2. Any segments that require special treatment according to the guidelines
3. DO NOT write detailed breakdowns for segments that follow the same structure as already detailed segments
4. After each detailed segment, add a note like: "(Note: Segments X, Y, and Z follow this same structural pattern)"

[Segment Name] (HH:MM:SS - HH:MM:SS, Duration: HH:MM:SS)
[Sub-segment Name] (HH:MM:SS - HH:MM:SS)
- [Key point with specific details]
- [Key point with specific details]
- [Key point with specific details]
[... continue for all sub-segments]

[Next Unique Segment Type] (HH:MM:SS - HH:MM:SS, Duration: HH:MM:SS)
[... continue only for unique segment types]

    3. For each segment:
       a. USE GUIDELINE SEGMENT STRUCTURE FOR TIMING BEATS but RENAME THE SEGMENT TITLES to be STORY‑SPECIFIC and audience‑facing.
          - Do NOT copy guideline labels like "Emergency Broadcast Introduction" or "Primary Warning Signs" as final titles.
          - Craft short, evocative titles (2–6 words) derived from the video title and content (e.g., "When The Block Goes Dark", "Find The Lone Streetlamp").
          - Avoid generic labels (Introduction/Conclusion/Primary/Secondary) and production jargon.
       b. Calculate the start and end times based on the segment duration and the total video duration, ensuring they sum up correctly.
       c. Include a detailed description in the table row, providing comprehensive context, research, and factual information relevant to the segment.
       d. Below the table row, add 3-4 concise key points that offer specific guidance and context thats align with the guidelines, without inventing facts.
       e. Incorporate any formatting or structure specified in the guidelines, such as day structure (Day 1, Day 2, etc.) or specific content requirements.
       f. DO NOT use generic placeholders like "[Continue with similar detailed breakdowns for remaining segments...]". Generate unique content for each segment.

    4. Ensure the total duration and segment durations match exactly with those provided in the guidelines.

    5. Include any technical notes, production guidance, transition techniques, or recurring elements explicitly provided in the guidelines.

    6. For videos covering multiple subjects or list items, adjust the segment structure accordingly, keep the average duration per list item
     and figure out whetever you need to add more segments or take away from others to keep the pacing consistent.

    7. For listicle-format videos (e.g., "Top 10", "When X Happens"):
       a. Extract and analyze segment patterns from example timeline:
          - Calculate actual min, max, and average durations from examples
          - Note: Trust example timelines over stated averages
          - Example: If timeline shows "6:29, 14:29, 18:08, 12:55, 13:46"
            → Real range: 6-18 minutes
            → Most common: 12-15 minutes
            → Outliers: One short (6min), one long (18min)
       
       b. Calculate total segments needed:
          - Total video length / actual average from examples
          - Round to whole number that allows proper pacing
          - Example: 210min video with 13min average = ~16-18 segments
       
       c. Distribute segment lengths following example patterns:
          - Most segments: Use the most common duration (e.g., 12-15min)
          - Few shorter segments: Match shortest example (e.g., 6-7min)
          - Few longer segments: Match longest example (e.g., 18min)
          - Maintain ratio of short/medium/long segments from examples
       
       d. Provide structure for each segment without inventing details
       e. Include general guidelines for content based on theme
       f. Avoid specific dates/names unless in title/guidelines

    8. Emphasize flexibility:
       a. The outline should allow for easy adaptation based on available content.
       b. Provide options for different types of incidents or items that could fit the theme, based on the guidelines.
       c. Include a note that the final content will depend on available footage or verified incidents.

    9. ⚠️ CRITICAL INTRO LENGTH REQUIREMENT ⚠️
       - Introduction segments MUST be 20 seconds or less
       - This is a HARD REQUIREMENT regardless of total video length
       - Even for 3+ hour videos, intros cannot exceed 20 seconds
       - No exceptions to this rule

     10. ⚠️ IMPORTANT SEGMENT DURATION CONSTRAINT ⚠️
        a. For listicles, stories, or episodic content, keep individual segments under 15 minutes unless guidelines EXPLICITLY state longer durations.
        b. If a segment would exceed 15 minutes, split it into multiple shorter segments with connected themes.
        c. This is CRITICAL to ensure successful script generation - shorter segments are more manageable and lead to better quality scripts.
        d. Even if the story is epic or complex, breaking it into related 10-15 minute segments produces better results than one long segment.
        e. Only exceed 15 minutes if the guidelines provide clear examples of successful longer segments.

     11. 🎭 WRITING STYLE INTEGRATION ⚠️
        a. Pay special attention to the "Writing Style Analysis" section in the guidelines
        b. Incorporate writing style elements into segment descriptions:
           - Sentence structure patterns (short vs long, complex vs simple)
           - Vocabulary choices and tone requirements
           - Emotional intensity and pacing guidelines
           - Rhetorical devices to employ
           - Character voice consistency requirements
           - Transitional language patterns
           - Engagement techniques to use
           - Descriptive language requirements
           - Cultural reference patterns
           - Callback and foreshadowing techniques
        c. Ensure each segment description reflects the authentic writing voice identified in the guidelines
        d. Use the writing style analysis to inform how each segment should be written in the final script
   
   
   ‼️ ABSOLUTELY CRITICAL RULES ‼️
    1. You MUST list out EVERY SINGLE SEGMENT in the Video Structure section with exact timestamps
    2. If the video is 2 hours long, list out ALL segments for the full 2 hours
    3. If there are 26 segments, write out ALL 26 segments
    4. NEVER use phrases like:
       ❌ "[Continue with similar detailed breakdowns for remaining segments...]"
       ❌ "Would you like me to continue?"
       ❌ "[Similar segments until HH:MM:SS]"
    5. NO SHORTCUTS OR PLACEHOLDERS ALLOWED
    6. INTROS MUST BE 20 SECONDS OR LESS - NO EXCEPTIONS

    
    Remember: Your primary objective is to create a comprehensive, actionable plot outline that precisely follows the provided guidelines, capturing the essence of the original series in terms of structure, tone, style, and pacing. Adherence to the guidelines and maintaining consistency with the existing series is crucial. Focus on translating the given structure into a detailed, easy-to-implement format for the specific video topic, including any formatting requirements or content specifications outlined in the guidelines."""

    user_message = f"""Generate a comprehensive plot outline based on the following information:

    1. Series Name: {series['name']}
    2. Theme: {theme['name']}
    3. Video Topic: {title}
    4. Desired Video Duration: {duration_str}
    
    YOUR RESPONSE MUST FOLLOW THIS EXACT FORMAT:

    Video Title: [Title]
    Total Duration: [Duration in H:MM:SS format] ([Duration] minutes)

    Video Structure:
    [If applicable: Based on the example timeline patterns and scaled for duration, maintaining similar ratios:]

    1. [Segment Name] (HH:MM:SS - HH:MM:SS, Duration: HH:MM:SS)
    2. [Segment Name] (HH:MM:SS - HH:MM:SS, Duration: HH:MM:SS)

    Detailed Segment Breakdown:

    [Segment Name] (HH:MM:SS - HH:MM:SS, Duration: HH:MM:SS)
    [Sub-segment Name] (HH:MM:SS - HH:MM:SS)
    - [Key point with specific details]
    - [Key point with specific details]
    - [Key point with specific details]
    [... continue for all sub-segments]

    [Next Segment Name] (HH:MM:SS - HH:MM:SS, Duration: HH:MM:SS)
    [... continue for all segments]

    REQUIREMENTS:
    - Keep fixed-length segments (intros, transitions, outros) at their original durations. IF THE GUIDELINES DONT HAVE AN INTRO OR OUTRO DONT INCLUDE ONE.
    - Scale main content segments proportionally while maintaining the established pacing ratios
    - Ensure all segment durations sum up exactly to {duration_str}
    - Provide comprehensive context, research, and details for each segment
    - Maintain consistency with the existing series in terms of structure, tone, style, and pacing
    - Do not use placeholders like "[RESEARCH: ...]" for research or content
    - DO NOT use generic placeholders like "[Continue with similar detailed breakdowns for remaining segments...]"
    - Generate unique content for each segment
    - Use exact HH:MM:SS format for all timestamps
    - Include 3-5 specific key points for each sub-segment

    TITLING RULES (CRITICAL):
    - Keep the guideline segment STRUCTURE and TIMING, but RENAME every segment title to be story‑specific and derived from the video topic.
    - Absolutely NO generic guideline names (e.g., "Emergency Broadcast Introduction", "Primary Warning Signs", "Conclusion").
    - Titles should be 2–6 words, evocative, and audience‑facing. Reflect the video title and the actual events in the script.
    - Examples (for an analog‑horror PSA about lights):
      • "Opening Title" → "When The Block Goes Dark"
      • "Emergency Broadcast Introduction" → "Signal From The City Desk"
      • "Primary Warning Signs" → "The Flicker Starts At 9"
      • "Safety Instructions" → "Stand In The Streetlight Halo"

    ⚠️ CRITICAL REQUIREMENTS ⚠️
    - NO SEGMENT should EVER exceed 10 minutes in duration - this is a HARD REQUIREMENT
    - For long-form content (1+ hours), create MORE segments rather than longer segments
    - This requirement overrides any contradictory instructions in the guidelines
    - Follow guidelines for anything suggesting segments under 10 minutes
    - INTROS MUST BE 20 SECONDS OR LESS - NO EXCEPTIONS

    YOU MUST:
    1. Calculate total segments needed based on total duration and segment length
    2. List out EVERY SINGLE SEGMENT with exact timestamps
    3. Continue until reaching {duration_str} exactly
    4. NEVER use any form of "continuing" or "remaining segments"
    5. Write out every segment even if it's 100 segments
    6. NEVER create segments longer than 10 minutes - split them into multiple parts instead
    7. Keep intros to 20 seconds maximum regardless of video length


    Guidelines: {guidelines}"""
    
    # Add research data to user message if available
    if research_data:
        user_message += f"\n\n{research_data}"
    
    # Initial call to generate the plot outline
    for attempt in range(max_retries):
        try:
            response = await client.messages.create(
                model="claude-3-7-sonnet-20250219",
                max_tokens=10000,
                temperature=0.7,
                system=system_message,
                messages=[{"role": "user", "content": user_message}]
            )
            plot_outline = response.content[0].text
            logger.info("Plot outline generated successfully")
            break
        except Exception as e:
            logger.error(f"Error in generate_plot_outline (attempt {attempt + 1}): {str(e)}")
            if attempt == max_retries - 1:
                logger.error("Max retries reached. Returning error message.")
                return f"Error generating plot outline: {str(e)}"
            await asyncio.sleep(2 ** attempt)
    else:
        return f"Error generating plot outline: Max retries reached"

    # Check exclusively the video structure part for continuation markers (e.g. "Would you like me to continue")
    continuation_prompt = "Would you like me to continue"
    additional_attempts = 0
    max_continuations = 3  # Prevent infinite loops

    # Use the latest Claude Sonnet 4 model and handle 'refusal' stop reasons
    while additional_attempts < max_continuations and continuation_prompt.lower() in plot_outline.lower():
        logger.info("Detected continuation prompt in the VIDEO STRUCTURE portion. Triggering follow-up to complete ONLY the video structure part.")
        try:
            cont_response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                temperature=0.7,
                system=system_message,
                messages=[
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": plot_outline},
                    {"role": "user", "content": (
                        "Continue ONLY the video structure part of the plot outline from the last segment. "
                        "IMPORTANT: You must list out EVERY SINGLE SEGMENT in the video structure section with exact timestamps as per the critical rules. "
                        "Do NOT include any questions, prompts, or placeholders (e.g., 'Would you like me to continue?'). "
                        "Please provide only the remaining segments, formatted exactly as required."
                    )}
                ]
            )
            # Check for refusal stop reason (Claude 4 models)
            if hasattr(cont_response, "stop_reason") and cont_response.stop_reason == "refusal":
                logger.error("Claude 4 refused to continue the video structure. Aborting further attempts.")
                break
            continuation_text = cont_response.content[0].text
            plot_outline += "\n" + continuation_text  # Append the continuation text
            additional_attempts += 1
        except Exception as e:
            logger.error(f"Error during continuation attempt {additional_attempts + 1}: {str(e)}")
            break
    # Final plot_outline is now fully completed and formatted for generate_full_script.
    return plot_outline  # Return only the plot_outline, not the tuple

def calculate_segment_timestamps(segment_durations, total_duration):
    timestamps = []
    current_time = 0

    for duration in segment_durations:
        start_time = current_time
        end_time = current_time + duration
        timestamps.append((start_time, end_time))
        current_time = end_time

    # Adjust the last segment's end time to match the total duration
    timestamps[-1] = (timestamps[-1][0], total_duration)

    return timestamps

async def generate_full_script(
    title: str,
    plot_outline: str,
    script_breakdown: str,
    series: Dict[str, Any],
    theme: Dict[str, Any],
    video_length: float,
    characters: List[str] = None,
    research_articles: List[str] = None,
    host_name: str = None,
    sponsored_info: Dict[str, str] = None,
    max_retries: int = 5
) -> tuple[str, Dict[str, Any]]:
    # Add token tracking variables
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0
    segment_costs = []

    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    
    system_message = """You are an AI assistant specialized in creating precisely timed video scripts for YouTube content. Your primary task is to generate detailed, engaging scripts with strict adherence to specified durations.

CORE FORMATTING REQUIREMENTS:
1. Timing Precision: Use 150 words per minute as baseline. Calculate exact word count for each segment.
2. Segment Format: "Chapter Name (Timestamp - Timestamp, Duration: X:XX)"
   Example: Introduction (00:00 - 02:15, Duration: 02:15)
3. Character Format: ALWAYS use bracketed names. Example: [CHARACTER_NAME]: Dialogue text.
4. Each line MUST begin with [CHARACTER_NAME]: format - this is CRITICAL for voice generation.
5. Introduction/Outro: Unless specified, keep intro under 10 seconds (25 words) with teaser from 60% point.

CONTENT REQUIREMENTS BY TYPE:
1. Scary Stories: Write complete original narratives with full story development. Include character actions, climactic moments, and sensory details. NO placeholders.
2. Listicle Format: Use placeholders [ITEM X] when needed. Create adaptable structure for easy editing later.
3. Clip-Dependent Videos: Use format [CLIP X: Description]. Include timing guidelines and generic narration cues.
4. Educational Content: Focus on accuracy and clarity. Use [RESEARCH] only when necessary.
5. Sponsored Content: Integrate naturally after hook but before main content. Format as:
   SPONSORED SEGMENT (Duration: X:XX)
   [SPONSOR_NAME]: Product description
   Key messaging points
   Natural transition to main content

FORMAT ADHERENCE CRITICAL POINTS:
1. Follow all template guidelines provided in script_breakdown
2. Include all recurring elements mentioned in guidelines
3. Maintain segment timestamps exactly as specified
4. Include accurate transitions between segments
5. Ensure word counts match duration requirements
6. Cross-check against plot outline to include all key points
7. For long segments, maintain narrative flow between chunks

STYLE AND TEMPLATE LOCK (CRITICAL):
- Always mirror tone, diction, and formatting cues present in the provided breakdown/guidelines verbatim.
- Treat the breakdown's writing style as authoritative; do not drift.
- If the series implies an emergency-broadcast/PSA tone (e.g., analog horror), write in that voice consistently.

PROHIBITED CONTENT:
- NO meta-commentary or statements like "Here's the script"
- NO editor notes unless absolutely necessary
- NO word counts embedded in the final script
- NO deviation from specified format
- NO content outside the plot outline

Remember: Every line MUST start with [CHARACTER_NAME]: and adhere to exact timing requirements. Calculate all word counts based on 150 words per minute.
"""
    # Set a static previous context to avoid carrying over any text.
    previous_context = "Starting fresh"

    # Extract segments from the plot outline
    segments = await extract_segments(plot_outline)
    # Remove logger.info
    # logger.info(f"Extracted {len(segments)} segments from the video structure.")

    # Extract Video Structure block for reference
    try:
        video_structure = plot_outline.split('Video Structure:')[1].split('Detailed Segment Breakdown:')[0].strip()
    except IndexError:
        video_structure = ""

    script_segments = []
    
    # Initialize prompt cache for segment processing
    segment_prompt_cache = {}

    # Add a function to clean generated scripts
    def clean_script(script_text, is_first_chunk=False, segment_header=""):
        """
        Remove meta-commentary, duplicate headers, and ensure proper formatting.
        """
        # Remove any "I understand" or similar meta-commentary at the beginning
        script_text = re.sub(r'^I understand[^\.]+\.\s*', '', script_text, flags=re.IGNORECASE)
        script_text = re.sub(r'^Understood\.[^\.]+\.\s*', '', script_text, flags=re.IGNORECASE)
        script_text = re.sub(r'^I will[^\.]+\.\s*', '', script_text, flags=re.IGNORECASE)
        script_text = re.sub(r'^I\'ll[^\.]+\.\s*', '', script_text, flags=re.IGNORECASE)
        script_text = re.sub(r'^Here is[^\.]+\.\s*', '', script_text, flags=re.IGNORECASE)
        script_text = re.sub(r'^Following[^\.]+\.\s*', '', script_text, flags=re.IGNORECASE)
        script_text = re.sub(r'^As requested[^\.]+\.\s*', '', script_text, flags=re.IGNORECASE)
        
        # If this is not the first chunk, remove any headers
        if not is_first_chunk and segment_header:
            script_text = re.sub(rf'{re.escape(segment_header)}\s*\([^)]+\)[^\n]*\n', '', script_text)
        
        # Remove any "Word count: X" at the end or elsewhere in the text
        script_text = re.sub(r'[,\s]*Word count:?\s*\d+\s*$', '', script_text)
        script_text = re.sub(r'[,\s]*\d+\s*words?\s*$', '', script_text)
        script_text = re.sub(r'[,\s]\d+$', '', script_text)  # Catch bare numbers at end
        
        # Make sure all dialogue lines start with a character name in brackets
        lines = script_text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # Skip empty lines
            if not line_stripped:
                cleaned_lines.append(line)
                continue
                
            # IMPORTANT FIX: Check if line is a segment header and preserve it as-is
            if re.match(r'^.+\(\d{2}:\d{2}:\d{2}\s*-\s*\d{2}:\d{2}:\d{2},\s*Duration:', line_stripped) or \
               re.match(r'^.+\(\d{2}:\d{2}:\d{2}\s*-\s*\d{2}:\d{2}:\d{2},\s*Duration:', line_stripped) or \
               (segment_header and line_stripped.startswith(segment_header)):
                cleaned_lines.append(line)
                continue
                
            # Check if line starts with a properly formatted character name
            if not re.match(r'^\s*\[[^\]]+\]:', line):
                # Only convert lines that appear to be dialogue but are missing the character tag
                # Look for dialogue indicators like quotation marks or narrative style
                if (line_stripped.startswith('"') or 
                    re.match(r'^[A-Z][a-z]+\s+[a-z]+', line_stripped) or 
                    re.search(r'said|asked|replied|exclaimed', line_stripped)):
                    line = f"[{host_name if host_name else 'NARRATOR'}]: {line_stripped}"
            
            cleaned_lines.append(line)
            
        return '\n'.join(cleaned_lines)

    # Define a function to process a single segment
    async def process_segment(idx, segment, cache_key=None):
        """Process a single segment and return it with its index to maintain order."""
        # Add nonlocal declaration to access the parent function's variables
        nonlocal total_input_tokens, total_output_tokens, total_cost, segment_costs, segment_prompt_cache
        
        # Calculate the target word count
        dur_parts = segment['duration'].split(':')
        if len(dur_parts) == 2:
            minutes = int(dur_parts[0]) + int(dur_parts[1]) / 60.0
        else:
            hours = int(dur_parts[0])
            minutes = hours*60 + int(dur_parts[1]) + int(dur_parts[2]) / 60.0
        
        # Use 170 words per minute as target
        target_word_count = int(minutes * 170)
        min_word_count = int(minutes * 160)  # Absolute minimum acceptable
        
        # Check if segment is extremely long and needs chunking
        needs_chunking = min_word_count > 1600  # Lower threshold to catch 10+ minute segments
        chunk_count = 1
        
        # Prepare the segment header exactly once
        segment_header = f"{segment['name']} ({segment['timestamp']}, Duration: {segment['duration']})"
        
        logger.info(f"Segment {idx+1} details: Target word count: {target_word_count}, Chunking: {'Yes' if needs_chunking else 'No'}")
        
        if needs_chunking:
            # Calculate how many chunks we need (aim for ~2000 words per chunk)
            chunk_count = math.ceil(min_word_count / 2000)
            logger.info(f"Segment {idx+1} will be split into {chunk_count} chunks")
            
            # Prepare for chunked generation
            chunk_scripts = []
            words_per_chunk = min_word_count // chunk_count
            
            # Generate each chunk
            for chunk_idx in range(chunk_count):
                chunk_valid = False
                chunk_attempts = 0
                max_chunk_attempts = 3  # Fewer attempts per chunk
                
                while not chunk_valid and chunk_attempts < max_chunk_attempts:
                    try:
                        # Determine chunk position (first, middle, last)
                        position = "beginning of" if chunk_idx == 0 else "end of" if chunk_idx == chunk_count-1 else "middle of"
                        
                        # Check if we're using caching and if this is not the first attempt or first chunk
                        use_cached_prompt = cache_key and (chunk_attempts > 0 or chunk_idx > 0)
                        
                        if use_cached_prompt and cache_key in segment_prompt_cache:
                            # Use a condensed prompt with Claude's prompt caching mechanism
                            user_message = f"""Generate chunk {chunk_idx+1}/{chunk_count} for the {position} segment {idx+1}/{len(segments)} "{segment['name']}" for "{title}":

This is a continuation of our conversation about creating a script segment.
Use the same guidelines and requirements as before.

Segment Details:
- Full segment name: {segment['name']}
- Timestamp: {segment['timestamp']}
- Total segment duration: {segment['duration']}
- This is chunk {chunk_idx+1} of {chunk_count}
- Required words: ~{words_per_chunk} words

Previous chunks context: {", ".join(chunk_scripts[:50]) if chunk_scripts else "This is the first chunk"}

Remember to format all dialogue with character names in brackets like [{host_name if host_name else 'NARRATOR'}]:

STYLE/TEMPLATE LOCK (CRITICAL — DO NOT DEVIATE):
- Mirror the writing voice, cadence, and formatting used in the provided breakdown/guidelines exactly (sentence length, punctuation rhythm, vocabulary register, transitions, list/number usage).
- Treat the guidelines as the master template; do not introduce new section types, labels, or tone shifts.
- If this series implies an emergency‑broadcast/PSA tone (analog horror), write in that voice precisely: formal, clipped, procedural, ominous.
- Never narrate or speak timestamps, durations, or structural labels; those only exist in headers.
- Do not add meta explanations or editor notes.
"""
                        else:
                            # Store full prompt in cache for this segment
                            user_message = f"""Generate chunk {chunk_idx+1}/{chunk_count} for the {position} segment {idx+1}/{len(segments)} "{segment['name']}" for "{title}":

Segment Details:
- Full segment name: {segment['name']}
- Timestamp: {segment['timestamp']}
- Total segment duration: {segment['duration']}
- This is chunk {chunk_idx+1} of {chunk_count} for this segment
- Required words for this chunk: ~{words_per_chunk} words

⚠️ CRITICAL REQUIREMENT: Your chunk MUST contain AT LEAST {words_per_chunk} words AND follow the EXACT format guidelines below.

⚠️ VOICE GENERATION WARNING: Your output will be processed by a voice generation system that CANNOT handle any content except the segment header and proper dialogue lines. Any other text will cause serious errors.

⚠️⚠️ CRITICAL HOST NAME REPLACEMENT REQUIREMENTS ⚠️⚠️:
- ALWAYS use [{host_name if host_name else 'NARRATOR'}] as the main narrator
- NEVER use any channel names like "sleep theories", "morpheus realm", or other channel names
- DO NOT copy channel names from guidelines or script_breakdown
- ALWAYS replace channel-specific phrases like "Welcome to sleep theories" with "Welcome to {host_name if host_name else 'our channel'}"
- ALWAYS replace ALL channel-specific references with [{host_name if host_name else 'NARRATOR'}]
- CHECK EVERY LINE OF DIALOGUE to ensure no channel names appear
- This is ABSOLUTELY CRITICAL for proper voice generation

FORMATTING REQUIREMENTS:
1. STRICT FORMAT ADHERENCE:
   • For first chunk only: Start with the segment header exactly as shown below
   • ALWAYS enclose character names in square brackets, like [CHARACTER_NAME]
   • Every line of dialogue MUST be preceded by a character name in this format
   • Use [{host_name if host_name else 'NARRATOR'}] as the main narrator unless specified otherwise
   • DO NOT introduce random new characters not mentioned in the provided list
   • DO NOT include editor notes, word counts, or any meta-commentary
   • DO NOT include scene descriptions without dialogue tags

2. EXAMPLE FORMAT:
   {segment['name']} ({segment['timestamp']}, Duration: {segment['duration']})

   [{host_name if host_name else 'NARRATOR'}]: Continuous dialogue that covers the content...
   [{host_name if host_name else 'NARRATOR'}]: More dialogue continuing the narrative...

3. CHARACTER FORMAT EXAMPLES:
   [{host_name if host_name else 'NARRATOR'}]: The story continues as we explore...
   {f"[{characters[0]}]: Dialogue for this character..." if characters else ""}

4. INSTRUCTIONS:
   • You are writing part {chunk_idx+1} of {chunk_count} of segment "{segment['name']}"
   • Write EXACTLY {words_per_chunk} words of continuous content
   • For first chunk: Include the segment header exactly as shown above
   • For middle/final chunks: Continue the story without headers
   • Maintain consistent style and narrative flow between chunks
   • DO NOT include meta-commentary or word counts in the text
   • DO NOT repeat content from other chunks
   • STRICTLY adhere to the character formatting with names in brackets

5. PROHIBITED CONTENT - NEVER INCLUDE:
   • "Here's the script" or "Here's the continuation" phrases
   • Editor notes like "[NOTE TO EDITOR: This segment is shorter...]"
   • Word counts at the end of segments
   • Meta-commentary about what you're doing
   • Any text that isn't either the segment header or proper dialogue

Previous chunks context: {", ".join(chunk_scripts[:50]) if chunk_scripts else "This is the first chunk"}

Video Structure:
{video_structure}

Plot Outline for this segment:
{plot_outline}

Guidelines:
{script_breakdown}

Characters: {', '.join(characters) if characters else f'Use [{host_name if host_name else "NARRATOR"}] for all narration'}
Host Name: {host_name if host_name else 'NARRATOR'}

CRITICAL REMINDER: EVERY line of dialogue MUST start with a character name in brackets like [{host_name if host_name else 'NARRATOR'}]: and the main narrator should be used for most of the content unless dialogue from specific characters is required. DO NOT include ANY text that isn't dialogue or the segment header.

🎭 WRITING STYLE ADHERENCE (CRITICAL):
- Analyze the "Writing Style Analysis" section in the guidelines thoroughly
- Mirror the authentic writing voice identified in the analysis
- Apply the same sentence structure, vocabulary, tone, and narrative patterns
STYLE/TEMPLATE LOCK (CRITICAL — DO NOT DEVIATE):
- Emulate the writing style implied by the breakdown/guidelines word‑for‑word: match tone, pacing, transitional phrasing, and rhetorical patterns.
- Keep sentence structure and vocabulary register aligned with the template; avoid synonyms that shift tone.
- Do not invent new structural labels or change the order/shape of beats.
- Never read timestamps/durations in narration; they live only in headers.

- 🎭 WRITING STYLE ADHERENCE: Analyze the "Writing Style Analysis" section in guidelines and replicate:
  * Sentence structure patterns (short vs long, complex vs simple)
  * Vocabulary choices and tone requirements
  * Emotional intensity and pacing guidelines
  * Rhetorical devices (repetition, alliteration, metaphors, analogies)
  * Character voice consistency and differentiation
  * Transitional language patterns
  * Engagement techniques (direct questions, hypotheticals, callbacks)
  * Descriptive language requirements (specificity vs generality)
  * Cultural reference patterns and frequency
  * Callback and foreshadowing techniques
- Write in the authentic voice identified in the writing style analysis - this is CRITICAL for authenticity
"""
                            # Store the cache for future use
                            if cache_key:
                                segment_prompt_cache[cache_key] = True

                        # Create the Claude conversation
                        messages = [{"role": "user", "content": user_message}]
                        
                        # If we're using a cached prompt, add the previous message reference
                        if use_cached_prompt:
                            messages[0]["content"] = f"{messages[0]['content']}\n\nContinue with the same context and guidelines as our previous messages."
                        
                        response = await client.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=8000,
                            temperature=0.7,  # Lower temperature for consistency
                            system=system_message,
                            messages=messages
                        )
                        
                        # Track token usage and costs (safely)
                        try:
                            if hasattr(response, 'usage') and response.usage is not None:
                                input_tokens = getattr(response.usage, 'input_tokens', 0)
                                output_tokens = getattr(response.usage, 'output_tokens', 0)
                                
                                # Update totals
                                total_input_tokens += input_tokens
                                total_output_tokens += output_tokens
                                
                                # Calculate cost - Correct Claude 3.5 Sonnet pricing ($3/M input, $15/M output)
                                input_cost = (input_tokens / 1000000) * 3
                                output_cost = (output_tokens / 1000000) * 15
                                segment_cost = input_cost + output_cost
                                total_cost += segment_cost
                                
                                # Track individual segment costs
                                segment_costs.append({
                                    "segment_name": segment['name'],
                                    "chunk": f"{chunk_idx+1}/{chunk_count}",
                                    "input_tokens": input_tokens,
                                    "output_tokens": output_tokens,
                                    "cost": segment_cost,
                                    "cached_prompt": use_cached_prompt
                                })
                                
                                # Add enhanced logging for prompt caching usage
                                if hasattr(response.usage, 'cache_read_input_tokens') and response.usage.cache_read_input_tokens > 0:
                                    cache_read = response.usage.cache_read_input_tokens
                                    logger.info(f"Prompt caching ACTIVE - Reused {cache_read:,} cached tokens for segment {idx+1}")
                                    # Calculate savings
                                    cache_savings = (cache_read / 1000000) * 3 * 0.9  # 90% cheaper for cached tokens
                                    logger.info(f"Cost savings: ${cache_savings:.4f} (90% discount on {cache_read:,} tokens)")
                        except Exception as e:
                            # Just log the error but continue with script generation
                            logger.error(f"Error tracking token usage: {str(e)}")
                        
                        chunk_script = response.content[0].text
                        
                        # Clean the script to remove any meta-commentary
                        chunk_script = clean_script(chunk_script, is_first_chunk=(chunk_idx==0), segment_header=segment_header)
                        
                        # For first chunk, ensure it has the proper header
                        if chunk_idx == 0 and not chunk_script.strip().startswith(segment_header):
                            chunk_script = f"{segment_header}\n\n{chunk_script}"
                        
                        # Validate word count - be more lenient for chunks
                        word_count = len(chunk_script.split())
                        
                        # Accept if within 20% of target or within 100 words
                        word_count_difference = words_per_chunk - word_count
                        close_enough = word_count >= words_per_chunk * 0.8 or word_count_difference <= 100
                        
                        if not close_enough:
                            chunk_attempts += 1
                        else:
                            chunk_valid = True
                            chunk_scripts.append(chunk_script)
                            
                            # Log chunk completion
                            logger.info(f"Segment {idx+1}, chunk {chunk_idx+1}/{chunk_count} completed with {len(chunk_script.split())} words")
                    
                    except Exception as e:
                        chunk_attempts += 1
                        if chunk_attempts >= max_chunk_attempts:
                            chunk_scripts.append(f"[NARRATOR]: Error generating this portion of the story. {words_per_chunk} words should be here.")
                        await asyncio.sleep(2)
            
            # Combine all chunks
            segment_script = "\n\n".join(chunk_scripts)
            
            # Make sure there aren't multiple instances of the header
            header_pattern = r'^.*?\(\d{2}:\d{2}:\d{2}\s*-\s*\d{2}:\d{2}:\d{2}.*?Duration:.*?\)'
            headers = re.findall(header_pattern, segment_script, re.MULTILINE)
            if len(headers) > 1:
                # Keep only the first header
                for header in headers[1:]:
                    segment_script = segment_script.replace(header, "", 1)
            
            # Calculate the total word count for checking
            total_words = len(segment_script.split())
            
            # If still too short after chunking (unlikely), add a note
            if total_words < min_word_count:
                segment_script += f"\n\n[NOTE TO EDITOR: This segment is shorter than required ({total_words}/{min_word_count} words). Please expand content to match the {segment['duration']} duration.]"
        
        else:
            # For normal length segments, use the existing approach
            segment_valid = False
            segment_script = ""
            attempts_for_segment = 0
            max_segment_attempts = max_retries
            
            while not segment_valid and attempts_for_segment < max_segment_attempts:
                try:
                    # Check if we're using caching and if this is not the first attempt
                    use_cached_prompt = cache_key and attempts_for_segment > 0 and cache_key in segment_prompt_cache
                    
                    if use_cached_prompt:
                        # Use a condensed prompt with Claude's prompt caching mechanism
                        user_message = f"""Generate script segment {idx + 1}/{len(segments)} for "{title}":

This is a continuation of our conversation about creating a script segment.
Use the same guidelines and requirements as before.

Segment Details:
- Segment Name: {segment['name']}
- Timestamp: {segment['timestamp']}
- Duration: {segment['duration']} (Target: {target_word_count} words, minimum: {min_word_count} words)

Remember that every line must start with a character name in brackets like [{host_name if host_name else 'NARRATOR'}]:

STYLE/TEMPLATE LOCK (CRITICAL — DO NOT DEVIATE):
- Mirror the writing voice, cadence, and formatting used in the provided breakdown/guidelines exactly (sentence length, punctuation rhythm, vocabulary register, transitions, list/number usage).
- Treat the guidelines as the master template; do not introduce new section types, labels, or tone shifts.
- If this series implies an emergency‑broadcast/PSA tone (analog horror), write in that voice precisely: formal, clipped, procedural, ominous.
- Never narrate or speak timestamps, durations, or structural labels; those only exist in headers.
- Do not add meta explanations or editor notes.
"""
                    else:
                        # Regular full prompt - converted to use Anthropic's prompt caching
                        # Structured content array with cache_control on static parts
                        user_message = [
                            {
                                "type": "text",
                                "text": f"""Video Structure:
{video_structure}

Plot Outline:
{plot_outline}

Guidelines:
{script_breakdown}

Characters: {', '.join(characters) if characters else 'None provided'}
Research Articles: {', '.join(research_articles) if research_articles else 'None provided'}
Host Name: {host_name if host_name else 'Not specified'}

{f'''Sponsored Content:
Segment: {sponsored_info["segment"]}
Requirements: {sponsored_info["requirements"]}

IMPORTANT: Integrate the sponsored segment naturally after the hook but before main content.
''' if sponsored_info else ''}""",
                                "cache_control": "ephemeral"  # Cache the static guidelines content
                            },
                            {
                                "type": "text",
                                "text": f"""Generate script segment {idx + 1}/{len(segments)} for "{title}":

Segment Name: {segment['name']}
Timestamp: {segment['timestamp']}
Duration: {segment['duration']} (Target Word Count: approx. {target_word_count} words)

⚠️ CRITICAL REQUIREMENT: Your script segment MUST contain AT LEAST {min_word_count} words, and ideally {target_word_count} words. 
This is a HARD REQUIREMENT - scripts that are too short will be completely rejected!

⚠️ VOICE GENERATION WARNING: Your output will be processed by a voice generation system that CANNOT handle any content except the segment header and proper dialogue lines. Any other text will cause serious errors.

IMPORTANT: Your output should adhere to the following guidelines:

1. STRICT SEGMENT ADHERENCE:
   • Only generate content for the segment specified above.
   • This segment must appear exactly ONCE and match its exact timestamp as provided.
   • Do not duplicate segments; each segment should only appear in its designated slot.
   • Follow the exact order shown in the video structure.
   PLEASE DO NOT SAY THINGS LIKE "I understand that you want me to generate the script for segment 2/5 of the video". 
   JUST GENERATE THE DIALOGUE FOR THE SEGMENT.

⚠️⚠️ CRITICAL HOST NAME REPLACEMENT REQUIREMENTS ⚠️⚠️:
- ALWAYS use [{host_name if host_name else 'NARRATOR'}] as the main narrator
- NEVER use any channel names like "sleep theories", "morpheus realm", or other channel names 
- DO NOT copy channel names from guidelines or script_breakdown
- ALWAYS replace channel-specific phrases like "Welcome to sleep theories" with "Welcome to {host_name if host_name else 'our channel'}"
- ALWAYS replace ALL channel-specific references with [{host_name if host_name else 'NARRATOR'}]
- CHECK EVERY LINE OF DIALOGUE to ensure no channel names appear
- This is ABSOLUTELY CRITICAL for proper voice generation

2. TIMING AND STRUCTURE:
   • Generate spoken dialogue and action descriptions for the segment's duration.
   • DO NOT create labeled sub-segments within this main segment. Write continuous narration.
   • Maintain a continuous flow of dialogue that covers all required content.
   • Your segment MUST fill the entire duration - scripts that are too short will be rejected.
   • It is better to write slightly LONGER than the minimum than to be too short.

3. FORMATTING:
   • Format the segment exactly as:
     Segment Name (Timestamp - Timestamp, Duration: X:XX)
   • Keep introductions very short but provide a solid hook.
   • ALWAYS enclose character names in square brackets, like [CHARACTER_NAME].
   • Every line of dialogue MUST be preceded by a character name in this format.

4. PROHIBITED CONTENT - NEVER INCLUDE:
   • "Here's the script" or "Here's the continuation" phrases
   • Editor notes like "[NOTE TO EDITOR: This segment is shorter...]"
   • Word counts at the end of segments
   • Meta-commentary about what you're doing
   • Any text that isn't either the segment header or proper dialogue with character tags

Example format:

Chapter/Segment Name (Timestamp - Timestamp, Duration: X:XX)

[HOST NAME]: Continuous dialogue that covers all the required content for this segment...
[HOST NAME]: More dialogue continuing the narrative without sub-segment breaks...

Character Formatting Examples:
       [BONELESS]: Hello, Internet! Welcome to Film Theory.
       [CAW]: But Boneless, that's madness!

       Ensure that every line of dialogue is preceded by a character name in this format.
... ALWAYS HAVE THE NAMES WITHIN BRACKETS LIKE "[HOST NAME]"

4. WORD COUNT & DURATION REQUIREMENTS:
   • CRITICAL: The spoken dialogue must contain AT LEAST {min_word_count} words.
   • It's better to write {target_word_count} words to ensure proper duration.
   • At the end of the segment output, include a brief word count.
   • Do not include extraneous content that might inflate the overall duration.
   DO NOT INCLUDE ANYTHING ELSE IN THE OUTPUT BESIDES THE SPOKEN DIALOGUE AND THE SEGMENT HEADER.

FINAL CRITICAL REMINDER: Your output MUST ONLY contain the segment header at the top and dialogue lines with character tags in brackets. Any other text will break our voice generation system. NO meta-commentary, editor notes, or anything else."""
                                # No cache_control here - this is segment-specific content
                            }
                        ]
                        
                        # Store the cache for future use
                        if cache_key:
                            segment_prompt_cache[cache_key] = True

                    # Create the Claude conversation with updated format for prompt caching
                    if isinstance(user_message, list):
                        # New prompt caching format
                        messages = [{"role": "user", "content": user_message}]
                    else:
                        # Original string format for backward compatibility
                        messages = [{"role": "user", "content": user_message}]
                    
                    # If we're using a cached prompt, add the previous message reference
                    if use_cached_prompt:
                        if isinstance(messages[0]["content"], str):
                            messages[0]["content"] = f"{messages[0]['content']}\n\nContinue with the same context and guidelines as our previous messages."
                        else:
                            # Add reference as a new content item if using structured content array
                            messages[0]["content"].append({
                                "type": "text",
                                "text": "Continue with the same context and guidelines as our previous messages."
                            })
                    
                    response = await client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=8000,
                        temperature=0.7,
                        system=system_message,
                        messages=messages
                    )
                    
                    # Track token usage and costs (safely)
                    try:
                        if hasattr(response, 'usage') and response.usage is not None:
                            input_tokens = getattr(response.usage, 'input_tokens', 0)
                            output_tokens = getattr(response.usage, 'output_tokens', 0)
                            
                            # Update totals
                            total_input_tokens += input_tokens
                            total_output_tokens += output_tokens
                            
                            # Calculate cost - Correct Claude 3.5 Sonnet pricing ($3/M input, $15/M output)
                            input_cost = (input_tokens / 1000000) * 3
                            output_cost = (output_tokens / 1000000) * 15
                            segment_cost = input_cost + output_cost
                            total_cost += segment_cost
                        
                            # Track individual segment costs
                            segment_costs.append({
                                "segment_name": segment['name'],
                                "input_tokens": input_tokens,
                                "output_tokens": output_tokens,
                                "cost": segment_cost,
                                "cached_prompt": use_cached_prompt
                            })
                    except Exception as e:
                        # Just log the error but continue with script generation
                        logger.error(f"Error tracking token usage: {str(e)}")
                    
                    segment_script = response.content[0].text
                    # Clean the script to remove any meta-commentary
                    segment_script = clean_script(segment_script, is_first_chunk=True, segment_header=segment_header)
                    
                    # Ensure it has the proper header
                    if not segment_script.strip().startswith(segment_header):
                        segment_script = f"{segment_header}\n\n{segment_script}"
                    
                    # Make sure there aren't multiple instances of the header
                    header_pattern = r'^.*?\(\d{2}:\d{2}:\d{2}\s*-\s*\d{2}:\d{2}:\d{2}.*?Duration:.*?\)'
                    headers = re.findall(header_pattern, segment_script, re.MULTILINE)
                    if len(headers) > 1:
                        # Keep only the first header
                        for header in headers[1:]:
                            segment_script = segment_script.replace(header, "", 1)
                    
                    # Validate word count with very lenient thresholds
                    word_count = len(segment_script.split())
                    # Remove logger.info
                    # logger.info(f"Segment {segment['name']} generated with {word_count} words (min needed: {min_word_count})")
                    
                    # Accept all segments regardless of length - replacing the length check
                    segment_valid = True
                    
                except Exception as e:
                    attempts_for_segment += 1
                    if attempts_for_segment >= max_segment_attempts:
                        segment_script = f"{segment_header}\n\n[{host_name if host_name else 'NARRATOR'}]: Error generating content for this segment."
                        segment_valid = True
                    await asyncio.sleep(2 ** attempts_for_segment)
        
        # Do a final check to make sure the segment is properly formatted
        if segment_script:
            # 1. Ensure header format is correct
            if not segment_script.strip().startswith(segment_header):
                segment_script = f"{segment_header}\n\n{segment_script}"
                
            # 2. Remove any duplicate headers
            header_pattern = r'^.*?\(\d{2}:\d{2}:\d{2}\s*-\s*\d{2}:\d{2}:\d{2}.*?Duration:.*?\)'
            headers = re.findall(header_pattern, segment_script, re.MULTILINE)
            if len(headers) > 1:
                # Keep only the first header
                for header in headers[1:]:
                    segment_script = segment_script.replace(header, "", 1)
                
            # 3. Make sure there's no meta-commentary left
            segment_script = clean_script(segment_script, is_first_chunk=True, segment_header=segment_header)
        
        # Return the index and the segment script to maintain order
        return idx, segment_script

    # Create a semaphore to limit the number of concurrent API calls
    # This avoids rate limits and excessive resource usage
    semaphore = asyncio.Semaphore(5)  # Process up to 5 segments at a time

    async def process_segment_with_semaphore(idx, segment):
        """Process a segment with semaphore to control concurrency."""
        async with semaphore:
            return await process_segment(idx, segment)

    # Create a cache for prompt components to reduce token usage across segments
    segment_prompt_cache = {}

    # Modified process function that uses the cache
    async def process_segment_with_cache_and_semaphore(idx, segment):
        """Process a segment with semaphore and use prompt caching to reduce token usage."""
        async with semaphore:
            # Generate a cache key based on segment name
            cache_key = f"segment_{idx}"
            logger.info(f"Starting to process segment {idx+1}/{len(segments)}: '{segment['name']}'")
            result = await process_segment(idx, segment, cache_key=cache_key)
            logger.info(f"Completed segment {idx+1}/{len(segments)}: '{segment['name']}'")
            return result

    # Process all segments in parallel with controlled concurrency
    logger.info(f"Starting parallel processing of {len(segments)} segments")
    tasks = []
    for idx, segment in enumerate(segments):
        tasks.append(process_segment_with_cache_and_semaphore(idx, segment))
    
    # Wait for all segments to complete
    results = await asyncio.gather(*tasks)
    
    # Sort results by original segment index to maintain order
    results.sort(key=lambda x: x[0])
    
    # Extract just the scripts in the correct order
    script_segments = [result[1] for result in results]
    
    logger.info(f"Completed parallel processing of all {len(segments)} segments")

    # Merge all segment outputs
    full_script = "\n\n=== SEGMENT BREAK ===\n\n".join(script_segments)
    
    # Final cleanup of the entire script to make sure there are no remaining issues
    # Remove any "I understand" or similar statements
    full_script = re.sub(r'I understand[^\.]+\.\s*', '', full_script, flags=re.IGNORECASE | re.MULTILINE)
    full_script = re.sub(r'Understood\.[^\.]+\.\s*', '', full_script, flags=re.IGNORECASE | re.MULTILINE)
    full_script = re.sub(r'I will[^\.]+\.\s*', '', full_script, flags=re.IGNORECASE | re.MULTILINE)
    full_script = re.sub(r'I\'ll[^\.]+\.\s*', '', full_script, flags=re.IGNORECASE | re.MULTILINE)
    full_script = re.sub(r'Here is[^\.]+\.\s*', '', full_script, flags=re.IGNORECASE | re.MULTILINE)
    
    # Remove "Word count: X" at the end of segments
    full_script = re.sub(r'Word count:?\s*\d+\s*(\n\=\=\= SEGMENT BREAK \=\=\=)?', r'\1', full_script, flags=re.MULTILINE)
    logger.info(f"Successfully merged all segments. Final length: {len(full_script.split())} words")
    
    # Create cost summary
    cost_data = {
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cost": total_cost,
        "segment_costs": segment_costs,
        "timestamp": datetime.now().isoformat(),
        "title": title,
        "model": "claude-sonnet-4-20250514"
    }
    
    # Calculate caching statistics if available
    total_cached_tokens = 0
    cache_savings = 0.0
    segments_with_caching = 0
    
    for cost_item in segment_costs:
        if cost_item.get("cached_prompt"):
            segments_with_caching += 1
        
        # If we have cache metrics for this segment, add them up
        if cost_item.get("cache_read_input_tokens", 0) > 0:
            total_cached_tokens += cost_item["cache_read_input_tokens"]
            # Calculate savings (90% discount on cached tokens)
            cache_savings += (cost_item["cache_read_input_tokens"] / 1000000) * 3 * 0.9
    
# Python standard library
from ast import arg
import asyncio
import base64
import functools
import io
import json
import logging
import math
import os
import random
import re
import shutil
import sys
import tempfile
import time
import traceback
from datetime import datetime
from typing import List, Dict, Optional, Union, Any
import textwrap
import librosa
from services.cloud_service import CloudVideoService
# Third-party packages
import aiohttp
import cv2
import numpy as np
import replicate
from anthropic import Anthropic, AsyncAnthropic, HUMAN_PROMPT, AI_PROMPT
from elevenlabs import Voice, voices
from elevenlabs.client import ElevenLabs
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload, MediaIoBaseDownload
from pydub import AudioSegment
import os
import zipfile
import time
import boto3
import aiohttp
import asyncio
import tenacity
import tempfile
import functools
import hashlib
import google.generativeai as genai
from google.generativeai.types import GenerationConfig, Tool # Import Tool
import os
import json
import logging
import re # For cleaner JSON extraction
from typing import List, Dict, Any # Corrected Type Hinting


# Local imports
from config import (
    ANTHROPIC_API_KEY,
    ELEVENLABS_API_KEY,
    GOOGLE_CREDENTIALS_FILE,
    REPLICATE_API_TOKEN,
    logger
)
from database import db
from services.google_docs_service import get_drive_service, get_credentials

def get_drive_service():
    """Get an authorized Drive service instance with domain delegation"""
    try:
        # Add caching - only create a new service if needed
        if hasattr(get_drive_service, 'cached_service') and get_drive_service.cached_service:
            try:
                # Test if the cached service still works by making a simple API call
                get_drive_service.cached_service.files().list(pageSize=1).execute()
                return get_drive_service.cached_service
            except Exception:
                # If test fails, cached service is invalid, create a new one
                logger.info("Cached Drive service failed, creating new service")
                pass
        
        # Use the same path configuration as google_docs_service
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        SERVICE_ACCOUNT_FILE = os.path.join(project_root, 'googlecred', 'service_account.json')
        
        # Your Workspace user email
        WORKSPACE_USER_EMAIL = 'boneless@nicole-ai.com'
        
        # Use retries for connection errors
        import socket
        import ssl
        import random
        import time
        
        MAX_RETRIES = 5
        
        for retry in range(MAX_RETRIES):
            try:
                # Load credentials from service account file
                credentials = service_account.Credentials.from_service_account_file(
                    SERVICE_ACCOUNT_FILE,
                    scopes=['https://www.googleapis.com/auth/drive.file', 
                           'https://www.googleapis.com/auth/drive']
                )
                
                # Add domain-wide delegation
                delegated_credentials = credentials.with_subject(WORKSPACE_USER_EMAIL)
                
                # Build the service with additional settings
                service = build('drive', 'v3', 
                               credentials=delegated_credentials,
                               cache_discovery=False)
                
                # Cache the service for future use
                get_drive_service.cached_service = service
                
                return service
            except (socket.error, ssl.SSLError, ConnectionError) as e:
                # These are network-related errors that might be transient
                if retry < MAX_RETRIES - 1:
                    wait_time = (2 ** retry) + (random.random() * 0.5)  # Exponential backoff with jitter
                    logger.warning(f"Drive service SSL/network error (attempt {retry+1}/{MAX_RETRIES}): {str(e)}. Retrying in {wait_time:.1f}s")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to initialize Drive service after {MAX_RETRIES} attempts: {str(e)}")
                    return None
    except Exception as e:
        logger.error(f"Error creating Drive service: {str(e)}")
        return None

ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)

print(f"Loading ai_utils.py from: {__file__}")
print(f"Python version: {sys.version}")
print(f"Python path: {sys.path}")

logger = logging.getLogger(__name__)

def cache_claude_analysis(func):
    cache = {}
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        key = str(args) + str(kwargs)
        if key not in cache:
            result = await func(*args, **kwargs)
            cache[key] = result
        return cache[key]
    return wrapper

import asyncio
import json
import logging
import random
import traceback
from typing import List, Dict
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = "your_anthropic_api_key_here"
@cache_claude_analysis
async def get_claude_analysis(video_data: List[Dict], channel_title: str = None, max_retries: int = 5, max_titles: int = 9000):
    video_titles = [video['title'] for video in video_data]
    logger.info(f"Starting Claude analysis for {len(video_titles)} video titles")
    
    if not video_titles:
        logger.error("No video titles provided for analysis")
        raise ValueError("No video titles provided for analysis")

    if len(video_titles) > max_titles:
        logger.warning(f"Number of video titles ({len(video_titles)}) exceeds maximum ({max_titles}). Truncating list.")
        video_titles = video_titles[:max_titles]

    # Add batch processing
    BATCH_SIZE = 80  # Process 50 videos at a time
    all_series_data = []
    
    # Split videos into batches
    video_batches = [video_titles[i:i + BATCH_SIZE] for i in range(0, len(video_titles), BATCH_SIZE)]
    
    # Initialize client and system message BEFORE the batch loop
    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    system_message = """You are a highly skilled YouTube content analyzer. Your task is to analyze video titles to identify top-performing series, themes, and topics. Follow these instructions precisely:

    1. **Hierarchy Understanding:**
       - Understand and maintain the correct hierarchy: Series > Themes > Topics.
       - A Series contains multiple Themes, and each Theme contains multiple Topics.

    2. **Series Identification:**
       - Examine the video titles to identify recurring words, phrases, or structures.
       - A series is a collection of videos with a consistent format, style, or recurring theme that ties them together.
       - Series names should be specific and descriptive, capturing the core concept.
       - Do not use placeholder words like [Person] or [Situation] in series names.
       - Example: If multiple videos start with or end with "Roblox But..." followed by different challenges, they belong to the "Roblox But" series.

    3. **Theme Identification:**
       - Identify the broader, overarching narrative or idea that the series explores.
       - The theme goes beyond the surface-level topic and captures the essence of what the series is about.
       - Themes should be general enough to encompass multiple videos but specific to the series.
       - Derive themes directly from the topics, ensuring they accurately represent the subject matter.
       - Avoid using specific time frames or numerical elements in theme names.
       - Example: For a "Roblox But" series, themes might be "Time-Based Changes" or "Player Limitations."

    4. **Topic Identification:**
       - The topic is the specific subject matter or narrative that each video addresses within the theme.
       - It's what differentiates one episode from another within the series.
       - The topic must be an exact, contiguous phrase taken directly from the title.
       - It should represent the most specific or unique element in the title.
       - Do not paraphrase or interpret the topic; use the exact words from the title.
       - Example: For "Roblox But Acid Rises Every Second", the topic is "Acid Rises".

    5. **Output Format:**
    Present the analysis as a JSON object with the following structure:

    {
      "series": [
        {
          "name": "Series Name",
          "themes": [
            {
              "name": "Theme Name",
              "topics": [
                {
                  "name": "Topic Name",
                  "example": "Full Video Title"
                }
              ]
            }
          ]
        }
      ]
    }

    6. **Constraints:**
       - Include all identified series.
       - For each series, include all identified themes.
       - Each topic MUST include the exact matching video title as its example.
       - Include EVERY video title as a topic somewhere in the structure.
       - Do not add any explanations or notes outside the specified JSON structure.

    7. **Theme Distinctiveness:**
       - Ensure themes within a series are distinct from each other.
       - If two themes are very similar, combine them into a single, more general theme.
       - Never repeat the same or nearly identical themes within a series.

    8. **Series Name Precision:**
       - Series names should be specific and avoid generic placeholders.
       - Capture the recurring pattern or concept that links multiple videos.
       - Ensure the series name is descriptive and unique to the content.
       - Name the series based on the repetitive title structure across multiple videos.
       - ONLY NAME THE SERIES BASED ON THE REPETITIVE TITLE STRUCTURE.
       - Example: If the repetitive title structure across multiple videos is "Roblox But...", the series name should be "Roblox But..."
    
    9. **Theme-Topic Relationship:**
       - Themes should directly relate to and encompass the video topics they contain.
       - Ensure a clear and logical connection between the theme and its video topics.

    10. **Theme-Topic Alignment:**
        - Ensure that the identified theme accurately represents the video topic.
        - The theme should be a broader category that the topic falls under.
        - If the topic is very specific (e.g., "Earth's Evolution"), the theme should be a more general category that encompasses it (e.g., "Planetary Development").
        - Avoid using the exact same wording for both theme and topic unless it's the only logical choice.
    
    11. **Consistency Check:**
        - After identifying themes and topics, review them to ensure consistency across all entries.
        - If you notice a theme that doesn't align well with its topics, reconsider and adjust the theme to better represent the content.
        - Make sure that similar topics across different videos are grouped under the same theme when appropriate.

    12. **Complete Coverage:**
        - Every single video title MUST be assigned to a series, theme, and topic
        - Track which titles have been processed and which haven't
        - Before finalizing output, verify that ALL input titles are included
        - If any titles are missing, create appropriate series/themes to include them
        - CRITICAL: When multiple videos have identical titles, DO NOT consolidate them
        - Each individual video title must appear as a separate topic entry, even if titles are duplicated
        - Example: If "Greek Mythology for Sleep" appears 90 times, create 90 separate topic entries
        
    
    13. **Series and Theme Merging Rules:**
        A. Series Pattern Analysis:
           - BEFORE creating any new series:
             * Check ALL existing series patterns for matches
             * Look for partial matches (e.g., "Upgrading to" vs "Upgrading into")
             * Check if pattern could be a theme of existing series
           
        B. Series Merging Priority:
           1. Exact Pattern Match:
              * If title matches existing series pattern exactly -> Add to that series
              * Example: "Upgrading to X" matches "Upgrading to... in GTA 5"
           
           2. Similar Pattern Match:
              * If title has similar pattern -> Merge into existing series
              * Examples:
                - "Upgrading to" and "Upgrading into" -> Merge as "Upgrading to. in GTA 5"
                - "Character Evolution" and "Character Progression" -> Merge as one series
           
           3. Theme vs Series Decision:
              * If new pattern could be subset of existing series -> Add as theme
              * Example: "Size Transformation" should be theme under "Upgrading" series
        
        C. Theme Merging Priority:
           1. Check Existing Themes:
              * Look for similar theme concepts across ALL series
              * Consolidate themes with similar meanings
              * Example: "Character Power-Ups" and "Basic Transformations" -> Merge as "Character Transformations"
           
           2. Theme Hierarchy:
              * General themes should absorb more specific ones
              * Maintain consistent theme names across series
              * Example: All size-related themes -> "Size Transformations"

        D. New Series Creation Rules:
           - ONLY create new series when:
             1. Title pattern is completely unique
             2. Cannot fit into any existing series
             3. Cannot be converted to theme
             4. Follows clear repetitive structure

    7. **Style Guidelines:**
       - **Do not include any text outside of the JSON object.**
       - **Your response should start immediately with '{' and end with '}'.**
       - **Do not include any introductory text, explanations, or apologies.**

    **Your response must strictly follow the specified JSON format without any deviations. Include every single video title in the analysis, ensuring no titles are missed or omitted. Start your response immediately with the JSON object.**
    """
    
    for batch_num, video_batch in enumerate(video_batches):
        logger.info(f"Processing batch {batch_num + 1}/{len(video_batches)} ({len(video_batch)} videos)")
        
        titles_text = "\n".join([f"- {title}" for title in video_batch])
        
        # Add previous batch series info to the prompt if not first batch
        if batch_num > 0:
            # Include full series structure, not just names
            previous_series_info = []
            for series in all_series_data:
                themes_info = []
                for theme in series.get('themes', []):
                    themes_info.append(f"    - Theme: {theme['name']}")
                    for topic in theme.get('topics', []):
                        themes_info.append(f"      • Topic: {topic['name']} (Example: {topic['example']})")
                
                previous_series_info.extend([
                    f"- Series: {series['name']}",
                    *themes_info
                ])
            
            series_context = "\n".join(previous_series_info)
            
            user_message = f"""Analyze the following video titles with STRICT adherence to the existing series and themes:

Previously identified series structure:
{series_context}

Video titles to analyze:
{titles_text}

Please carefully analyze these titles and:

1. **Add to Existing Series and Themes:**
   - **Mandatory:** Before creating any new series, check if each video title fits into any existing series.
   - Use **exact matching** and **case-insensitive** comparisons for series names to avoid variations.
   - If a title fits multiple series, choose the most specific one.
   - **Critical:** Check EVERY word in the title against existing series patterns, not just the beginning.
   - Example: "When Evil Parents Realize..." should match "When... Get/Try/Realize" series.

2. **Merge Similar Series and Themes:**
   - If a potential new series shares similarities with an existing one, **merge them**.
   - Look for partial matches or variations in naming (e.g., "Upgrading to..." vs. "Upgrading into...").
   - Consolidate themes with overlapping concepts under a more general theme.

3. **Avoid Redundancies:**
   - **Eliminate duplicates** in series, themes, and topics.
   - Ensure that topics are unique and not repeated within the same theme.

4. **Create New Series Only When Necessary:**
   - Only create a new series if the title pattern is **completely unique** and **cannot fit** into any existing series or theme.
   - Ensure the new series follows the established naming conventions.

5. **Maintain Series Name Precision:**
   - Series names must be based on the **exact repetitive title structure**.
   - Enforce uniformity in naming conventions across all batches.

6. **Review and Adjust Hierarchies:**
   - Ensure that themes are correctly placed under the appropriate series.
   - Adjust the hierarchy if a theme aligns better with a different series.

7. **Complete Data Fields:**
   - Populate all data fields for each topic, ensuring no missing information. EVERY SINGLE VIDEO TITLE MUST BE INCLUDED.

8. **Strictly Follow the System Message Guidelines:**
   - Adhere to **all rules** and instructions provided in the system message.

When in doubt, **prefer merging into existing series and themes** over creating new ones. The goal is to have a cohesive, non-redundant structure that accurately categorizes all video titles.

Provide the updated analysis in the specified JSON format without any extra explanations."""
        else:
            user_message = f"""Analyze the following video titles:

{titles_text}

Please analyze these video titles and provide a comprehensive analysis in the specified JSON format without any extra explanations."""

        for attempt in range(max_retries):
            try:
                logger.info(f"Sending request to Claude API (attempt {attempt + 1})")
                response = await client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=8192,
                    temperature=0.2,
                    system=system_message,
                    messages=[{"role": "user", "content": user_message}]
                )
                
                response_text = response.content[0].text
                logger.debug(f"Raw Claude API response for batch {batch_num + 1}: {response_text[:500]}...")
                
                # Clean response - strip markdown code blocks if present
                clean_text = response_text.strip()
                if '```json' in clean_text:
                    clean_text = clean_text.split('```json')[1]
                if '```' in clean_text:
                    clean_text = clean_text.split('```')[0]
                clean_text = clean_text.strip()
                
                try:
                    batch_series_data = json.loads(clean_text)
                    if isinstance(batch_series_data, dict) and 'series' in batch_series_data:
                        all_series_data.extend(batch_series_data['series'])
                        break
                    elif isinstance(batch_series_data, list):
                        all_series_data.extend(batch_series_data)
                        break
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON for batch {batch_num + 1}, retrying...")
                    continue
                    
            except Exception as e:
                logger.error(f"Error in Claude API request for batch {batch_num + 1} (attempt {attempt + 1}): {str(e)}")
                if attempt == max_retries - 1:
                    return None
    # Merge similar series
    merged_series = {}
    for series in all_series_data:
        name = series['name']
        if name not in merged_series:
            merged_series[name] = series
        else:
            for theme in series['themes']:
                existing_themes = merged_series[name]['themes']
                theme_exists = False
                for existing_theme in existing_themes:
                    if existing_theme['name'] == theme['name']:
                        existing_theme['topics'].extend(theme['topics'])
                        theme_exists = True
                        break
                if not theme_exists:
                    existing_themes.append(theme)

    # Add this check right before returning the merged_series data
    if merged_series and len(merged_series) == 1:
        # If we only have one series, check if it contains all videos
        # If not, make sure each video appears at least once in the structure
        series_name = next(iter(merged_series.keys()))
        series = merged_series[series_name]
        
        all_examples = []
        for theme in series.get('themes', []):
            for topic in theme.get('topics', []):
                all_examples.append(topic.get('example', ''))
        
        # Check if any videos are missing from the analysis
        missing_titles = set([video['title'] for video in video_data]) - set(all_examples)
        
        if missing_titles:
            # Create a new theme for missing titles if needed
            if not series.get('themes'):
                series['themes'] = []
                
            # Add missing titles to an appropriate theme or create a new one
            misc_theme = None
            for theme in series['themes']:
                if theme['name'] == 'Miscellaneous':
                    misc_theme = theme
                    break
                    
            if not misc_theme:
                misc_theme = {'name': 'Miscellaneous', 'topics': []}
                series['themes'].append(misc_theme)
                
            for title in missing_titles:
                misc_theme['topics'].append({
                    'name': title.split(' ')[0:3],  # Take first few words as topic name
                    'example': title
                })
    
    return list(merged_series.values()) if merged_series else None

def extract_partial_data(response_string):
    series = []
    current_series = None
    current_theme = None
    
    for line in response_string.split('\n'):
        line = line.strip()
        if '"name":' in line and '"themes":' in line:
            if current_series:
                series.append(current_series)
            current_series = {"name": line.split('"name":')[1].split(',')[0].strip(' "'), "themes": []}
        elif '"name":' in line and '"topics":' in line:
            if current_theme:
                current_series["themes"].append(current_theme)
            current_theme = {"name": line.split('"name":')[1].split(',')[0].strip(' "'), "topics": []}
        elif '"name":' in line and '"example":' in line:
            name = line.split('"name":')[1].split(',')[0].strip(' "')
            example = line.split('"example":')[1].strip(' ",')
            current_theme["topics"].append({"name": name, "example": example})
    
    if current_theme:
        current_series["themes"].append(current_theme)
    if current_series:
        series.append(current_series)
    
    return series


def fix_json_string(json_str):
    # Remove any text before the first '{' and after the last '}'
    json_str = json_str.strip()
    start = json_str.find('{')
    end = json_str.rfind('}') + 1
    json_str = json_str[start:end]

    # Unescape escaped characters
    json_str = json_str.replace('\\"', '"').replace('\\\\', '\\')

    # Fix common JSON formatting issues
    json_str = json_str.replace("'", '"')
    json_str = json_str.replace('True', 'true').replace('False', 'false').replace('None', 'null')

    # Remove any trailing commas before closing brackets
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*]', ']', json_str)

    return json_str

async def check_video_relevance(claude_analysis: Dict, videos: List[Dict]) -> int:
    
    matching_series = 0
    for series in claude_analysis['series']:
        for video in videos:
            if await check_videos_in_series(series['name'], video['title']):
                matching_series += 1
                break
    return matching_series

def check_videos_in_series(series_data: List[Dict], videos: List[str]) -> Dict[str, List[Dict]]:
    result = {}
    
    for series in series_data:
        series_name = series['name']
        result[series_name] = []
        
        for theme in series['themes']:
            theme_name = theme['name']
            
            for topic in theme['topics']:
                topic_name = topic['name']
                topic_keywords = set(re.findall(r'\w+', topic_name.lower()))
                
                for video_title in videos:
                    video_keywords = set(re.findall(r'\w+', video_title.lower()))
                    
                    # Check if there's significant overlap between video title and topic keywords
                    if len(topic_keywords.intersection(video_keywords)) >= 2:
                        result[series_name].append({
                            'title': video_title,
                            'theme': theme_name,
                            'topic': topic_name
                        })
    
    # Remove series with no matching videos
    return {k: v for k, v in result.items() if v}

def parse_claude_response(response: List[Dict]) -> List[Dict]:
    try:
        if not isinstance(response, list):
            logger.error(f"Invalid response structure: {response}")
            return None

        series_data = []
        for series in response:
            if not isinstance(series, dict) or "name" not in series or "themes" not in series:
                logger.error(f"Invalid series structure: {series}")
                continue

            series_info = {
                'name': series['name'],
                'themes': []
            }
            for theme in series['themes']:
                if not isinstance(theme, dict) or "name" not in theme or "topics" not in theme:
                    logger.error(f"Invalid theme structure: {theme}")
                    continue

                theme_info = {
                    'name': theme['name'],
                    'topics': []
                }
                for topic in theme['topics']:
                    if not isinstance(topic, dict) or "name" not in topic or "example" not in topic:
                        logger.error(f"Invalid topic structure: {topic}")
                        continue

                    topic_info = {
                        'name': topic['name'],
                        'example': topic['example']
                    }
                    theme_info['topics'].append(topic_info)
                series_info['themes'].append(theme_info)
            series_data.append(series_info)
        return series_data
    
    except Exception as e:
        logger.error(f"Error parsing Claude response: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return None
def process_series_data(data: dict) -> List[Dict]:
    if not isinstance(data, dict) or 'series' not in data:
        logger.warning("Data is not in the expected format")
        return None

    processed_data = []
    for series in data['series']:
        series_data = {
            "name": series.get('name', 'Unnamed Series'),
            "themes": [{
                "name": theme.get('name', 'Unnamed Theme'),
                "topics": [{
                    "name": topic.get('name', 'Unnamed Topic'),
                    "example": topic.get('example', 'No example')
                } for topic in theme.get('topics', [])]
            } for theme in series.get('themes', [])]
        }
        processed_data.append(series_data)
    return processed_data

def parse_views(view_string: str) -> int:
    if not view_string or view_string.lower() in ['not available', 'n/a']:
        return 0

    view_string = view_string.strip().lower().replace(',', '')
    
    multipliers = {'k': 1000, 'm': 1000000, 'b': 1000000000}
    
    try:
        for suffix, multiplier in multipliers.items():
            if view_string.endswith(suffix):
                return int(float(view_string[:-1]) * multiplier)
        
        return int(float(view_string))
    except ValueError:
        logger.warning(f"Could not parse view count: {view_string}")
        return 0

def parse_niche_and_demographics(response: str) -> Dict:
    lines = response.split('\n')
    result = {}
    current_section = None

    for line in lines:
        line = line.strip()
        if line.startswith("Niche:"):
            result['niche'] = line.split(":", 1)[1].strip()
        elif line == "Target Demographics:":
            current_section = "demographics"
            result['demographics'] = {}
        elif current_section == "demographics":
            if line.startswith("- Age Range:"):
                result['demographics']['age_range'] = line.split(":", 1)[1].strip()
            elif line.startswith("- Gender Split:"):
                result['demographics']['gender_split'] = line.split(":", 1)[1].strip()
            elif line.startswith("- Interests:"):
                result['demographics']['interests'] = [i.strip() for i in line.split(":", 1)[1].strip().split(',')]
            elif line.startswith("- Geographic Regions:"):
                result['demographics']['regions'] = []
            elif line.startswith(tuple("12345")) and 'regions' in result['demographics']:
                result['demographics']['regions'].append(line.split(".", 1)[1].strip())

def calculate_average_views(series_list: List[Dict]) -> float:
    if not series_list:
        return 0.0
    
    total_views = 0
    for series in series_list:
        if "average_views" in series and isinstance(series["average_views"], (int, float)):
            total_views += series["average_views"]
        else:
            # Log a warning or handle the case where average_views is missing or not a number
            print(f"Warning: Invalid average_views for series: {series.get('name', 'Unknown')}")
    
    return total_views / len(series_list)


    return result

async def identify_niche_and_demographics(channel_data: Dict, videos: List[Dict]):
    try:
        system_message = """You are an AI assistant specializing in YouTube channel analysis. Your task is to identify the niche and target demographics for a YouTube channel based on its content and audience."""

        user_message = f"""
        Channel Name: {channel_data.get('title', 'Unknown')}
        Subscriber Count: {channel_data.get('subscriberCount', 'Unknown')}
        Video Count: {channel_data.get('videoCount', 'Unknown')}
        Total Views: {channel_data.get('viewCount', 'Unknown')}

        Channel Description: {channel_data.get('description', 'No description available')}

        Recent Video Titles:
        {chr(10).join([f"- {video.get('title', 'Unknown Title')}" for video in videos[:10]])}

        Please analyze this information and provide:

        1. Niche: Identify the primary niche of this channel. Be specific but concise.
        2. Target Demographics: Estimate the primary target audience in terms of:
           - Age range
           - Gender split (if applicable)
           - Interests
           - Geographic regions (list top 5 countries you think this content would appeal to)

        Format your response as follows:

        Niche: [Identified Niche]

        Target Demographics:
        - Age Range: [Estimated Age Range]
        - Gender Split: [Estimated Gender Distribution or 'Not Specifically Targeted']
        - Interests: [List of 3-5 Primary Interests]
        - Geographic Regions:
          1. [Country 1]
          2. [Country 2]
          3. [Country 3]
          4. [Country 4]
          5. [Country 5]

        Provide only the requested information without any additional explanation.
        """

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "system": system_message,
                    "messages": [
                        {"role": "user", "content": user_message}
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.7
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info("Received response from Claude API")
                    logger.debug(f"Claude response: {data}")
                    if 'content' in data:
                        content_text = data['content'][0]['text']
                        return parse_niche_and_demographics(content_text)
                    else:
                        logger.error(f"Key 'content' not found in response: {data}")
                        raise Exception(f"Key 'content' not found in response: {data}")
                else:
                    error_data = await response.text()
                    logger.error(f"Error in Claude API call: {error_data}")
                    raise Exception(f"Claude API returned an error: {error_data}")

    except Exception as e:
        logger.error(f"Error in identify_niche_and_demographics: {str(e)}", exc_info=True)
        return {
            "niche": "Unknown",
            "demographics": {
                "age_range": "Unknown",
                "gender_split": "Unknown",
                "interests": ["Unknown"],
                "geographic_regions": ["Unknown"]
            }
        }

import aiohttp
from config import ANTHROPIC_API_KEY


async def generate_production_resources(niche):
    prompt = f"Given a YouTube niche of {niche}, what are the typical production resources needed? Include equipment, software, and human resources."
    return await generate_ai_response(prompt)

async def generate_monetization_opportunities(niche):
    prompt = f"For a YouTube channel in the {niche} niche, what are the best monetization opportunities? Include both on-platform and off-platform strategies."
    return await generate_ai_response(prompt)

async def generate_ai_response(prompt, max_tokens_to_sample=1000, model="claude-3-haiku-20240307"):
    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens_to_sample,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"Error in generate_ai_response: {str(e)}")
        raise

async def generate_production_resources(niche, top_video_transcript):
    prompt = f"""Given a YouTube niche of {niche} and the following transcript from a top-performing video in this niche:

Transcript:
{top_video_transcript}

Based on this information, provide detailed production resource requirements. Format your response as a Python dictionary with the following keys:
    'equipment': List common equipment used in this niche.
    'software': Describe software tools typically used in production.
    'human_resources': Outline the team composition and roles needed.
    'estimated_costs': Provide a breakdown of potential production costs.
Ensure the response is a valid Python dictionary.
    """
    response = await generate_ai_response(prompt, max_tokens_to_sample=4000, model="claude-3-haiku-20240307")
    
    try:
        resources = eval(response)
        if not isinstance(resources, dict):
            raise ValueError("Response is not a valid dictionary")
        
        required_keys = ['equipment', 'software', 'human_resources', 'estimated_costs']
        for key in required_keys:
            if key not in resources:
                resources[key] = f"No {key} data available."
        
        return resources
    except Exception as e:
        logger.error(f"Error processing AI response: {str(e)}")
        return {
            'equipment': "Error retrieving equipment data.",
            'software': "Error retrieving software data.",
            'human_resources': "Error retrieving human resources data.",
            'estimated_costs': "Error retrieving cost estimation data."
        }

async def generate_monetization_opportunities(niche, top_video_transcript):
    prompt = f"""Given a YouTube niche of {niche} and the following transcript from a top-performing video in this niche:

Transcript:
{top_video_transcript}

Based on this information, provide detailed monetization opportunities. Format your response as a Python dictionary with the following keys:
    'on_platform': List YouTube-specific monetization methods.
    'off_platform': Describe external revenue streams.
    'sponsorships': Outline potential sponsorship opportunities.
    'merchandise': Suggest product ideas and merchandising strategies.
Ensure the response is a valid Python dictionary.
    """
    response = await generate_ai_response(prompt, max_tokens_to_sample=4000, model="claude-3-haiku-20240307")
    
    try:
        opportunities = eval(response)
        if not isinstance(opportunities, dict):
            raise ValueError("Response is not a valid dictionary")
        
        required_keys = ['on_platform', 'off_platform', 'sponsorships', 'merchandise']
        for key in required_keys:
            if key not in opportunities:
                opportunities[key] = f"No {key} data available."
        
        return opportunities
    except Exception as e:
        logger.error(f"Error processing AI response for monetization opportunities: {str(e)}")
        return {
            'on_platform': "Error retrieving on-platform monetization data.",
            'off_platform': "Error retrieving off-platform monetization data.",
            'sponsorships': "Error retrieving sponsorship data.",
            'merchandise': "Error retrieving merchandise data."
        }
    
async def analyze_content_taxonomy(group_id, db):
    required_keys = ['primary_category', 'secondary_categories', 'content_types', 'themes', 'target_audience', 'vertical', 'niche']
    
    try:
        video_titles = await db.get_video_titles_for_group(group_id)
        logger.info(f"Analyzing content taxonomy for group {group_id} with {len(video_titles)} video titles")
        
        prompt = f"""Analyze the following YouTube video titles from a competitor group:

{', '.join(video_titles[:100])}  # Limit to 100 titles to avoid exceeding token limits

Based on these titles, provide a content taxonomy analysis. Format your response with the following keys:
    primary_category: The main content category.
    secondary_categories: Specific content sub-categories.
    content_types: Common video formats used.
    themes: Prevalent content themes or topics.
    target_audience: The intended audience for these videos.
    vertical: The broader industry or field this content falls under.
    niche: The specific market segment or specialized area within the vertical.

For each key, provide the most common attributes and their estimated percentage of occurrence.
"""
        response = await generate_ai_response(prompt, max_tokens_to_sample=2000, model="claude-3-haiku-20240307")
        logger.info(f"AI response for group {group_id}: {response}")
        
        # Parse the response
        taxonomy = {}
        current_key = None
        for line in response.split('\n'):
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower().replace(' ', '_')
                if key in required_keys:
                    current_key = key
                    taxonomy[current_key] = value.strip()
            elif current_key and line:
                taxonomy[current_key] += ' ' + line
        
        # Ensure all required keys are present
        for key in required_keys:
            if key not in taxonomy:
                taxonomy[key] = "Unknown"
        
        logger.info(f"Parsed taxonomy for group {group_id}: {taxonomy}")
        return taxonomy
    except Exception as e:
        logger.error(f"Error processing AI response for content taxonomy: {str(e)}", exc_info=True)
        return {key: "Unknown" for key in required_keys}

async def generate_multi_voice_over(script: str, voice_selections: Dict[str, str], user_id: int) -> str:
    logger.info(f"Starting generate_multi_voice_over for user {user_id}")
    api_key = await db.get_elevenlabs_api_key(user_id)
    if not api_key:
        logger.error(f"ElevenLabs API key not found for user {user_id}")
        raise ValueError("ElevenLabs API key not found for this user.")

    # Clean up the script first - remove any metadata or formatting
    script = re.sub(r'Word count:.*?\n', '', script)  # Remove word count
    script = re.sub(r'Segment:.*?\n', '', script)  # Remove segment titles
    script = re.sub(r'\n\s*\n', '\n', script)  # Remove extra newlines
    
    # Extract dialogue segments with improved pattern
    dialogue_pattern = r'\[([^\]]+)\]:\s*((?:[^[]+(?:\[(?![\w\s]+\]:)[^[]*)*)+)'
    dialogue_segments = re.findall(dialogue_pattern, script, re.DOTALL)
    
    if not dialogue_segments:
        logger.error("No valid dialogue segments found in script")
        raise ValueError("No valid dialogue segments found in script. Check script format.")
    
    logger.info(f"Found {len(dialogue_segments)} dialogue segments")
    
    audio_segments = []
    segment_timings = []
    current_position = 0
    
    # Process each dialogue segment
    for character, line in dialogue_segments:
        character = character.strip()
        line = line.strip()
        
        if not line:  # Skip empty lines
            continue
            
        logger.info(f"Generating voice over for segment - Character: {character}")
        voice_id = voice_selections.get(character)
        
        if not voice_id:
            logger.error(f"Voice ID not found for character: {character}")
            continue

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": api_key
        }
        data = {
            "text": line,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        audio_segment = await response.read()
                        # Store segment timing
                        segment_length = len(audio_segment) / 32000  # Approximate timing based on audio length
                        segment_timings.append((current_position, current_position + segment_length))
                        current_position += segment_length
                        
                        audio_segments.append(audio_segment)
                        logger.info(f"Successfully generated voice for segment - Character: {character}")
                    else:
                        error_message = await response.text()
                        logger.error(f"Error generating voice for segment - Character: {character}: {error_message}")
                        raise ValueError(f"Error generating voice for segment - Character: {character}: {error_message}")
        except Exception as e:
            logger.error(f"Exception while generating voice for segment - Character: {character}: {str(e)}", exc_info=True)
            raise

    # Combine audio segments
    combined_audio = b''.join(audio_segments)

    # Upload to Google Drive
    logger.info("Uploading combined audio to Google Drive")
    try:
        drive_service = get_drive_service()
        file_metadata = {'name': f'voice_over_{int(time.time())}.mp3'}
        media = MediaIoBaseUpload(io.BytesIO(combined_audio), mimetype='audio/mpeg', resumable=True)
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id,webViewLink').execute()
        
        # Make the file publicly accessible
        drive_service.permissions().create(fileId=file['id'], body={'type': 'anyone', 'role': 'reader'}).execute()

        logger.info(f"Voice over uploaded successfully. URL: {file['webViewLink']}")
        return file['webViewLink']
    except Exception as e:
        logger.error(f"Error uploading voice over to Google Drive: {str(e)}", exc_info=True)
        raise

async def generate_tts(text: str, profile: dict) -> str:
    """Generate TTS using either F5-TTS for cloning or Parler TTS for descriptions"""
    try:
        client = replicate.Client(api_token=REPLICATE_API_TOKEN)
        
        if profile['voice_type'] == 'clone':
            # Use F5-TTS for voice cloning
            output = await client.run(
                "nyxynyx/f5-tts:b4b5e5c2c3e9f3af0a83be8c18eb97ce4f8b7dac51a853014c6e20caf2d56db4",
                input={
                    "text": text,
                    "ref_audio_path": profile['voice_input']
                }
            )
        else:
            # Use Parler TTS for description-based voices
            output = await client.run(
                "andreasjansson/parler-tts:69c4aa53312b8698188d425ba6d25c9a14636adb9ea2ae1fd313a0fd2b45a32b",
                input={
                    "text": text,
                    "description": profile['voice_input']
                }
            )
        
        if output and isinstance(output, dict) and 'audio' in output:
            return output['audio']
        return None
    except Exception as e:
        logger.error(f"Error in TTS generation: {str(e)}")
        raise

async def apply_rvc(audio: bytes, model_id: str) -> bytes:
    """Apply RVC voice conversion using Replicate API"""
    try:
        output = replicate.run(
            "pseudoram/rvc-v2",
            input={
                "audio": audio,
                "model": model_id,
                "pitch_adjust": 0
            }
        )
        
        if output and 'audio' in output:
            async with aiohttp.ClientSession() as session:
                async with session.get(output['audio']) as response:
                    return await response.read()
        return None
    except Exception as e:
        logger.error(f"Error in RVC processing: {str(e)}")
        raise


async def generate_tts_rvc_voice_over(script: str, voice_selections: Dict[str, str], user_id: int) -> str:
    """Generate voice over using TTS+RVC pipeline, following same pattern as ElevenLabs"""
    logger.info(f"Starting TTS+RVC voice over generation for user {user_id}")

    # Clean up script same way as ElevenLabs version
    script = re.sub(r'Word count:.*?\n', '', script)
    script = re.sub(r'Segment:.*?\n', '', script)
    script = re.sub(r'\n\s*\n', '\n', script)
    
    # Use same dialogue pattern for consistency
    dialogue_pattern = r'\[([^\]]+)\]:\s*((?:[^[]+(?:\[(?![\w\s]+\]:)[^[]*)*)+)'
    dialogue_segments = re.findall(dialogue_pattern, script, re.DOTALL)
    
    if not dialogue_segments:
        logger.error("No valid dialogue segments found in script")
        raise ValueError("No valid dialogue segments found in script. Check script format.")
    
    logger.info(f"Found {len(dialogue_segments)} dialogue segments")
    
    # Get user's voice profiles
    voice_profiles = await db.get_tts_rvc_profiles(user_id)
    if not voice_profiles:
        raise ValueError("No voice profiles found for user")
    
    # Create profile lookup dict for quick access
    profile_lookup = {p['id']: p for p in voice_profiles}
    
    audio_segments = []
    segment_timings = []
    current_position = 0
    
    # Process each dialogue segment
    for character, line in dialogue_segments:
        character = character.strip()
        line = line.strip()
        
        if not line:
            continue
            
        logger.info(f"Generating voice over for segment - Character: {character}")
        profile_id = voice_selections.get(character)
        
        if not profile_id:
            logger.error(f"Voice profile not found for character: {character}")
            continue
            
        profile = profile_lookup.get(profile_id)
        if not profile:
            logger.error(f"Profile {profile_id} not found in database")
            continue

        try:
            # Generate TTS first
            logger.info(f"Generating TTS for character {character}")
            tts_audio = await generate_tts(
                text=line,
                emotion=profile['tts_emotion'],
                model_id="x-lance/f5-tts"  # Using F5 TTS for emotion support
            )
            
            if tts_audio:
                # Apply RVC transformation
                logger.info(f"Applying RVC for character {character}")
                rvc_audio = await apply_rvc(
                    audio=tts_audio,
                    model_id=profile['rvc_model']
                )
                
                if rvc_audio:
                    # Calculate timing same way as ElevenLabs version
                    segment_length = len(rvc_audio) / 32000
                    segment_timings.append((current_position, current_position + segment_length))
                    current_position += segment_length
                    
                    audio_segments.append(rvc_audio)
                    logger.info(f"Successfully generated voice for segment - Character: {character}")
                else:
                    logger.error(f"RVC processing failed for character: {character}")
            else:
                logger.error(f"TTS generation failed for character: {character}")
                
        except Exception as e:
            logger.error(f"Error processing segment for {character}: {str(e)}", exc_info=True)
            continue

    if not audio_segments:
        raise ValueError("No audio segments were generated successfully")

    # Combine audio segments
    combined_audio = b''.join(audio_segments)
    
    # Upload to Google Drive - same as ElevenLabs version
    logger.info("Uploading combined audio to Google Drive")
    try:
        drive_service = get_drive_service()
        file_metadata = {'name': f'tts_rvc_voice_over_{int(time.time())}.mp3'}
        media = MediaIoBaseUpload(io.BytesIO(combined_audio), mimetype='audio/mpeg', resumable=True)
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id,webViewLink').execute()
        
        # Make file publicly accessible
        drive_service.permissions().create(fileId=file['id'], body={'type': 'anyone', 'role': 'reader'}).execute()

        logger.info(f"Voice over uploaded successfully. URL: {file['webViewLink']}")
        return file['webViewLink']
    except Exception as e:
        logger.error(f"Error uploading voice over to Google Drive: {str(e)}", exc_info=True)
        raise

async def check_shared_series(series_data, search_result_titles, current_series_name):
    if isinstance(series_data, str):
        try:
            series_data = json.loads(series_data)
        except json.JSONDecodeError:
            # If it's not valid JSON, assume it's already a Python object
            pass
    
    if not isinstance(series_data, list):
        series_data = [series_data]
    
    if not isinstance(search_result_titles, list):
        search_result_titles = [str(search_result_titles)]
    
    
    print(f"Current Series Name: {current_series_name}")
    print(f"Series Data: {json.dumps(series_data, indent=2)}")
    print(f"First 5 Search Result Titles: {search_result_titles[:5]}")
    print(f"Total Search Result Titles: {len(search_result_titles)}")
    
    # Normalize current_series_name
    current_series_name_normalized = current_series_name.strip().lower()

    # Find the series in series_data that matches the current_series_name
    matching_series = None
    for series in series_data:
        series_name_normalized = series.get('name', '').strip().lower()
        if series_name_normalized == current_series_name_normalized:
            matching_series = series
            break

    if not matching_series:
        print(f"Series '{current_series_name}' not found in series_data.")
        # Handle this case appropriately
        result = {
            "shared_series": [],
            "is_eligible": False,
            "shared_series_count": 0
        }
        return result
    
    series_info = []
    example_titles = []
    
    series_info.append(f"Series: {current_series_name}")
    for theme in matching_series.get('themes', []):
        series_info.append(f"  Theme: {theme['name']}")
        for topic in theme.get('topics', []):
            series_info.append(f"    • Topic: {topic['name']}")
            example = topic.get('example', 'N/A')
            series_info.append(f"    • Example: {example}")
            if example != 'N/A':
                example_titles.append(example)
    series_info_str = "\n".join(series_info)
    
    prompt = f"""
    Series Information:
    {series_info_str}

    Search Result Video Titles:
    {json.dumps(search_result_titles[:100], indent=2)}  # Limit to 100 titles

    Analyze the search result video titles and determine if they belong to the series "{current_series_name}". Follow these guidelines strictly:

    1. Match the exact title structure of the series examples provided.
    2. Include variations that maintain the core concept of the examples.
    3. Exclude reaction videos unless the series specifically includes reactions.
    4. Be precise in matching. If in doubt, do not include the title.
    5. Consider the themes and topics provided, but prioritize matching the example title structures.

    Respond with a JSON object:
    {{
        "shared_series": [
            {{
                "name": "{current_series_name}",
                "matching_titles": ["list of exact matching titles"]
            }}
        ],
        "is_eligible": true/false (true if at least 3 matching titles),
        "shared_series_count": 1 if matches found, 0 otherwise
    }}

    Ensure that the matching_titles list contains only the exact titles that match the series structure and concept.
    """

    print(f"\n--- AI Prompt ---\n{prompt}")

    response = await generate_ai_response(prompt, max_tokens_to_sample=2000, model="claude-3-haiku-20240307")
    
    print(f"\n--- Raw AI Response ---\n{response}")

    try:
        cleaned_response = clean_claude_response(response)
        result = json.loads(cleaned_response)
        print(f"\n--- Parsed AI Response ---\n{json.dumps(result, indent=2)}")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response from AI: {str(e)}")
        print(f"\n--- Failed to parse JSON response from AI ---\nError: {str(e)}")
        print(f"Raw response: {response}")
        
        # Fallback: Improved string matching
        matching_titles = []
        for title in search_result_titles:
            if any(example.lower() in title.lower() for example in example_titles):
                matching_titles.append(title)
        
        is_eligible = len(matching_titles) >= 3
        shared_series_count = 1 if matching_titles else 0
        
        result = {
            "shared_series": [
                {
                    "name": current_series_name,
                    "matching_titles": matching_titles
                }
            ],
            "is_eligible": is_eligible,
            "shared_series_count": shared_series_count
        }
        
        print(f"\n--- Fallback Result ---\n{json.dumps(result, indent=2)}")

    
    print(json.dumps(result, indent=2))
    return result

client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

async def generate_voice_over(script: str, voice_name: str) -> str:
    voice = voices().get(voice_name)
    if not voice:
        raise ValueError(f"Voice '{voice_name}' not found.")

    audio = client.generate(text=script, voice=voice)
    
    file_name = f"voice_over_{int(time.time())}.mp3"
    file_path = f"/tmp/{file_name}"
    with open(file_path, "wb") as f:
        f.write(audio)

    drive_service = get_drive_service()
    file_metadata = {'name': file_name}
    media = MediaFileUpload(file_path, resumable=True)
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    
    drive_service.permissions().create(fileId=file.get('id'), body={'type': 'anyone', 'role': 'reader'}).execute()
    file = drive_service.files().get(fileId=file.get('id'), fields='webViewLink').execute()
    
    os.remove(file_path)
    
    return file.get('webViewLink')

def clean_claude_response(response_text: str) -> str:
    # Remove any leading/trailing whitespace
    response_text = response_text.strip()

    # Find the JSON part of the response
    start = response_text.find('{')
    end = response_text.rfind('}') + 1
    if start != -1 and end != -1:
        json_str = response_text[start:end]
    else:
        logger.error("No JSON object found in Claude response.")
        return ""

    # Remove any non-JSON characters
    json_str = re.sub(r'[^\x20-\x7E]', '', json_str)

    # Fix common JSON formatting issues
    json_str = json_str.replace("'", '"')  # Replace single quotes with double quotes
    json_str = re.sub(r'(\w+):', r'"\1":', json_str)  # Add quotes to keys

    return json_str



def extract_series_data_fallback(response_text: str) -> List[Dict]:
    series_pattern = r'"name":\s*"([^"]+)".*?"themes":\s*\[(.*?)\]'
    theme_pattern = r'"name":\s*"([^"]+)".*?"topics":\s*\[(.*?)\]'
    topic_pattern = r'"name":\s*"([^"]+)".*?"example":\s*"([^"]+)"'

    series_data = []
    for series_match in re.finditer(series_pattern, response_text, re.DOTALL):
        series_name = series_match.group(1)
        themes_text = series_match.group(2)
        
        themes = []
        for theme_match in re.finditer(theme_pattern, themes_text, re.DOTALL):
            theme_name = theme_match.group(1)
            topics_text = theme_match.group(2)
            
            topics = []
            for topic_match in re.finditer(topic_pattern, topics_text):
                topic_name = topic_match.group(1)
                topic_example = topic_match.group(2)
                topics.append({"name": topic_name, "example": topic_example})
            
            if topics:  # Only add themes with topics
                themes.append({"name": theme_name, "topics": topics})
        
        if themes:  # Only add series with themes
            series_data.append({"name": series_name, "themes": themes})

    return series_data

async def determine_niche(group_id, db):
    video_titles = await db.get_video_titles_for_group(group_id)
    
    if not video_titles:
        logger.warning(f"No video titles found for group {group_id}")
        return "Unknown"

    niche_categories = [
        "Finance", "Technology", "Education", "Entertainment", "Lifestyle", 
        "Marketing", "Crypto", "Real Estate", "Investing", "Side Hustle", 
        "Entrepreneurship", "Personal Finance", "Business", "Vlogging", 
        "Dropshipping", "Affiliate Marketing", "Print on Demand", "Filmmaking",
        "Travel", "Hustling", "Digital Products", "Motherhood", "Archery",
        "Hunting", "Productivity", "Science", "Space", "Geology", "Paleontology",
        "Astronomy", "History", "Politics", "News", "Gaming", "Sports",
        "Fitness", "Cooking", "Fashion", "Beauty", "DIY", "Home Improvement",
        "Gardening", "Pets", "Music", "Art", "Photography", "Writing",
        "Language Learning", "Food", "Wine", "Beer", "Spirits", "Automotive",
        "Motorcycles", "Boats", "Aviation", "Outdoors", "Survival", "Prepping",
        "Minimalism", "Sustainability", "Eco-friendly", "Parenting", "Relationships",
        "Dating", "Wedding", "Divorce", "Legal", "Insurance", "Healthcare",
        "Mental Health", "Spirituality", "Religion", "Philosophy", "Psychology",
        "Sociology", "Anthropology", "Archaeology", "Engineering", "Architecture",
        "Interior Design", "Graphic Design", "Web Design", "UX/UI", "Programming",
        "Data Science", "Artificial Intelligence", "Robotics", "Blockchain",
        "Cybersecurity", "Cloud Computing", "Internet of Things", "Virtual Reality",
        "Augmented Reality", "3D Printing", "Drones", "Electric Vehicles",
        "Renewable Energy", "Space Exploration", "Quantum Computing", "Nanotechnology",
        "Biotechnology", "Genetics", "Neuroscience", "Medicine", "Pharmacology",
        "Nutrition", "Yoga", "Meditation", "Martial Arts", "Dance", "Theater",
        "Cinema", "Literature", "Poetry", "Comedy", "Magic", "Circus", "Festivals",
        "Concerts", "Nightlife", "Bars", "Restaurants", "Cafes", "Street Food",
        "Luxury Travel", "Budget Travel", "Adventure Travel", "Ecotourism",
        "Cultural Tourism", "Religious Tourism", "Medical Tourism", "Space Tourism",
        "Cruise Travel", "Road Trips", "Backpacking", "Camping", "Hiking",
        "Climbing", "Skiing", "Snowboarding", "Surfing", "Scuba Diving",
        "Skydiving", "Paragliding", "Bungee Jumping", "Extreme Sports"
    ]
    
    prompt = f"""Based on the following YouTube video titles, determine the most appropriate niche category from this list:
    {', '.join(niche_categories)}

    Video titles: {', '.join(video_titles[:50])}

    Respond with ONLY the category name that best fits these video titles. If none of the categories fit well, respond with 'Other'.
    """
    
    response = await generate_ai_response(prompt, max_tokens_to_sample=100, model="claude-3-haiku-20240307")
    niche = response.strip()
    
    if niche == 'Other':
        logger.warning(f"AI couldn't determine a specific niche for group {group_id}")
        return "Unknown"
    elif niche not in niche_categories:
        logger.warning(f"AI returned a niche category not in the predefined list: {niche}. Using it anyway.")
    
    logger.info(f"Determined niche for group {group_id}: {niche}")
    return niche
client = AsyncAnthropic()

async def generate_video_titles(
    series: Dict[str, Any], 
    theme: Dict[str, Any], 
    example_titles: List[str], 
    custom_niche: str = None,
    enable_research: bool = False
) -> List[str]:
    # Add custom niche to the prompt if provided
    niche_text = ""
    niche_guidance = ""
    if custom_niche:
        niche_text = f"\nCustom Niche: {custom_niche}"
        niche_guidance = f"""
Additional Custom Niche Guidance:
- Adapt titles to focus on the custom niche: {custom_niche}
- Maintain the same structure but replace theme-specific terms with appropriate terms for {custom_niche}
- Ensure titles sound natural and authentic within the {custom_niche} domain
"""
    
    # Add research content when enabled
    research_content = ""
    if enable_research:
        try:
            logger.info(f"Performing research for titles: {series['name']} + {theme['name']}")
            
            # Get trending videos and extract keywords using the new approach
            from services.youtube_service import get_trending_videos_with_smart_search
            
            # Gather trending topics and keywords
            trend_info = await get_trending_videos_with_smart_search(series, theme, example_titles, custom_niche)
            
            if trend_info:
                research_content = "\n\nCURRENT TRENDING TOPICS (incorporate these into your titles):\n"
                
                # Add trending titles
                if trend_info.get('trending_titles'):
                    research_content += "Top Trending Titles:\n"
                    for i, title in enumerate(trend_info['trending_titles'][:5], 1):
                        research_content += f"   {i}. {title}\n"
                    research_content += "\n"
                
                # Add trending keywords
                if trend_info.get('trending_keywords'):
                    research_content += "Key Trending Keywords (incorporate these where relevant):\n"
                    keywords_text = ", ".join(trend_info['trending_keywords'][:15])
                    research_content += f"   {keywords_text}\n\n"
                
                # Removed trending channels section as it's not directly useful for title generation
                    
        except Exception as e:
            logger.error(f"Error performing research for titles: {str(e)}")
            # Continue without research if it fails
    
    prompt = f"""Generate highly interesting, potentially viral YouTube titles based on this series and theme, considering the target audience:

Series: {series['name']}
Theme: {theme['name']}{niche_text}
Average Views: {series.get('avg_views', 0):,.0f}
Video Count: {series.get('video_count', 0)}
Channels: {len(series.get('channels_with_series', []))}
{research_content}

⚠️ CRITICAL REQUIREMENT: ALL TITLES MUST BE UNDER 100 CHARACTERS ⚠️

IMPORTANT VOLUME INSTRUCTION:
- DO NOT include volume numbers (like V83, V1, Volume 5, etc.) in any titles
- If example titles contain volume numbers (e.g., "Dark Conspiracy Theories for Sleep(V83)"), 
  remove the volume portion completely when creating new titles
- Example: "Dark Conspiracy Theories for Sleep(V83)" → "Dark Conspiracy Theories for Sleep"

Example titles:
{json.dumps(example_titles, indent=2)}
{niche_guidance}
1. Title Analysis and Generation:
   - Carefully analyze the example title's structure, style, and content.
   - Identify the exact format: word order, capitalization, and any special characters.
   - For each theme, create 20 new titles that follow the precise structure of the example.
   - Use the video topic as a strict guide for the type of situations to create.
   - 🔴 MANDATORY: Keep ALL titles under 100 characters to comply with YouTube limits.
   - Count the total character length of each title before submitting it.

2. Creative Adaptation:
   - Maintain the exact sentence structure and tone of the original title.
   - Be creative with the specific situation described, but only within the confines of the theme and video topic.
   - Use similar language and phrasing as the example. Only introduce new vocabulary if it directly relates to the theme and maintains the tone.
   - Ensure the new situations are realistic and plausible within the context of the series. Avoid fantastical or unrealistic scenarios.

3. Title Structure:
   - Keep the exact same beginning and ending phrases as the example title.
   - Maintain all specific formatting, including capitalization, punctuation, and spacing.
   - Ensure the length of new titles matches the example title as closely as possible but NEVER exceed 100 characters.
   - 🔴 If example titles exceed 100 characters, create shorter versions while preserving key elements.

4. Audience and Theme Consideration:
   - Strictly adhere to the provided theme and video topic.
   - Ensure the situations described are realistic and could actually happen in the context of the series.
   - Consider the target audience and what types of content they would expect from this series.

5. Output Format:
Present the generated titles in this exact format, with no additional explanation or commentary:
[New Title 1]
[New Title 2]
...
[New Title 20]

6. Final Check:
   - Verify that each new title follows the exact structure, formatting, and style of the example.
   - Ensure all situations described are realistic and plausible within the series context.
   - Confirm that each title directly relates to the given theme and video topic.
   - Double-check that no fantastical or impossible scenarios have been introduced.
   - 🔴 COUNT CHARACTERS: Verify EVERY title is under 100 characters. Remove any that exceed this limit.

Always ask yourself: 
1. "Does this title maintain the exact style and structure of the original?"
2. "Is this scenario realistic and plausible within the context of the series?"
3. "Does this title directly relate to the given theme and video topic?"
4. "Is this title under 100 characters in length?"
{f'5. "Does this title effectively incorporate the {custom_niche} niche?"' if custom_niche else ""}

If the answer to any of these questions is "no," revise the title immediately.

Remember: Provide only the generated titles in the specified format. Do not include any explanations, analyses, or additional comments in your output."""

    system_message = """You are a YouTube title generator specializing in creating engaging, viral-worthy titles that precisely match the style of provided examples. Your task is to analyze the given series, themes, and example titles, then generate new titles that maintain the exact same structure while being creative within that framework.

⚠️ CRITICAL REQUIREMENT: ALL TITLES MUST BE UNDER 100 CHARACTERS ⚠️
This is a strict YouTube platform limitation. Titles exceeding 100 characters will be rejected.

IMPORTANT VOLUME INSTRUCTION:
- DO NOT include volume numbers (like V83, V1, Volume 5, etc.) in any titles
- If example titles contain volume numbers (e.g., "Dark Conspiracy Theories for Sleep(V83)"), 
  remove the volume portion completely when creating new titles
- Example: "Dark Conspiracy Theories for Sleep(V83)" → "Dark Conspiracy Theories for Sleep"

1. Title Analysis and Generation:
   - Carefully analyze the example title's structure, style, and content.
   - Identify the exact format: word order, capitalization, and any special characters.
   - For each theme, create 20 new titles that follow the precise structure of the example.
   - Use the video topic as a strict guide for the type of situations to create.
   - 🔴 MANDATORY: Keep ALL titles under 100 characters to comply with YouTube limits.
   - Count the total character length of each title before submitting it.

2. Creative Adaptation:
   - Maintain the exact sentence structure and tone of the original title.
   - Be creative with the specific situation described, but only within the confines of the theme and video topic.
   - Use similar language and phrasing as the example. Only introduce new vocabulary if it directly relates to the theme and maintains the tone.
   - Ensure the new situations are realistic and plausible within the context of the series. Avoid fantastical or unrealistic scenarios.

3. Title Structure:
   - Keep the exact same beginning and ending phrases as the example title.
   - Maintain all specific formatting, including capitalization, punctuation, and spacing.
   - Ensure the length of new titles matches the example title as closely as possible but NEVER exceed 100 characters.
   - 🔴 If example titles exceed 100 characters, create shorter versions while preserving key elements.

4. Audience and Theme Consideration:
   - Strictly adhere to the provided theme and video topic.
   - Ensure the situations described are realistic and could actually happen in the context of the series.
   - Consider the target audience and what types of content they would expect from this series.

5. Output Format:
Present the generated titles in this exact format, with no additional explanation or commentary:
[New Title 1]
[New Title 2]
...
[New Title 20]

6. Final Check:
   - Verify that each new title follows the exact structure, formatting, and style of the example.
   - Ensure all situations described are realistic and plausible within the series context.
   - Confirm that each title directly relates to the given theme and video topic.
   - Double-check that no fantastical or impossible scenarios have been introduced.
   - 🔴 COUNT CHARACTERS: Verify EVERY title is under 100 characters. Remove any that exceed this limit.

Always ask yourself: 
1. "Does this title maintain the exact style and structure of the original?"
2. "Is this scenario realistic and plausible within the context of the series?"
3. "Does this title directly relate to the given theme and video topic?"
4. "Is this title under 100 characters in length?"

If the answer to any of these questions is "no," revise the title immediately.

When trending topic research is provided:
- Incorporate trending topics naturally into the title structure
- Use trending keywords that fit the established format
- Add elements of timeliness (recent reveals, discoveries, events)
- Keep the core structure intact while modernizing the specific topic
- Blend the familiar title pattern with current interests


Remember: Provide only the generated titles in the specified format. Do not include any explanations, analyses, or additional comments in your output."""

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            temperature=0.6,
            system=system_message,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        content = response.content[0].text if isinstance(response.content, list) else response.content
        titles = parse_titles_from_response(content)
        
        # Log any titles that exceed limit but don't truncate them
        for title in titles:
            if len(title) > 100:
                logger.warning(f"Title exceeds 100 character limit: '{title}' ({len(title)} chars)")
        
        try:
            # Get existing titles for this series/theme
            existing_titles = await db.get_existing_titles(
                series_name=series['name'],
                theme_name=theme['name']
            )
            
            # Filter out any duplicates from existing titles
            new_titles = [title for title in titles if title not in existing_titles]
        except Exception as e:
            logger.warning(f"Failed to check for existing titles: {str(e)}")
            new_titles = titles  # Fall back to all generated titles if db check fails
        
        return new_titles[:20]  # Return up to 20 unique titles
    except Exception as e:
        logger.error(f"Error generating video titles: {str(e)}")
        return [f"Error generating title for {series['name']} - {theme['name']}"]

async def get_example_titles(group_id: str, series_name: str, theme_name: str) -> List[str]:
    return await db.get_example_titles(group_id, series_name, theme_name)

def parse_titles_from_response(response_content: Union[str, List[str]]) -> List[str]:
    if isinstance(response_content, str):
        # Split the content by newlines and remove any empty lines or lines containing "Series:" or "Theme:"
        lines = [line.strip() for line in response_content.split('\n') 
                if line.strip() and not line.startswith(('Series:', 'Theme:'))]
        return lines  # Remove the limit here to get all titles
    elif isinstance(response_content, list):
        return [str(item).strip() for item in response_content]
    else:
        return []

import anthropic

async def breakdown_script(series_name: str, theme_name: str, transcripts: List[Dict[str, Union[str, float]]], video_durations: List[float], video_titles: List[str], video_descriptions: List[str]) -> str:
    client = Anthropic()
    
    # Your existing system and assistant messages remain unchanged
    system_message = """You are an AI assistant specializing in analyzing video series structures. Your task is to process the given series name, theme, and provided transcript(s), then generate a comprehensive template that can be applied to future videos in the same series. This template should maintain the structure, style, and tone of the series while allowing for different video topics.

CRITICAL REQUIREMENT: ALL segments MUST be 10 minutes (600 seconds) or LESS in duration. NEVER create segments longer than 10 minutes, no matter what. If you identify a segment longer than 10 minutes, you MUST split it into multiple smaller segments with logical breakpoints. This is a hard constraint that cannot be violated under any circumstances.

Your analysis must include: Do not add any elements or recommendations that are not directly observed in the transcript(s). Provide specific examples, quotes, and timestamps from the transcript(s) to support each point in your analysis, especially in the script templates and other detailed sections

1. A detailed Video Structure breakdown with precise timestamps and durations.
2. A comprehensive Segment Outline Template covering all identified segments, including their internal structure and plot points.
3. A list of 3-5 Transition Techniques with specific examples and timestamps.
4. A list of 3-5 Recurring Elements with their frequency and context.
5. A complete Script Template corresponding to the Segment Outline Template, with specific examples and calculated durations for each segment.
6. Clip-Reactive Analysis: Determine if the series is clip-reactive (reacting to specific clips) or follows a structured documentary format. Look for short segments, quick transitions, frequent visual references, and a conversational tone that reacts to the content. If the video is clip-reactive, set "is_clip_reactive" to true, otherwise set it to false.
7. Tone and Style: Analyze the overall tone (e.g., conversational, formal, humorous), language style (e.g., technical, casual, academic), and level of formality used in the series. Provide specific examples from the transcript(s) to support your analysis.
8. Additional Observations: Note any other notable patterns, techniques, or characteristics that could aid in maintaining consistency with the series, such as recurring visual elements, editing patterns, or narrative devices.
9. Video Title Influence: Analyze how the specific video title impacts the structure, content, and flow of the video. Identify any patterns or adjustments made to accommodate the title's premise or topic. Provide examples from the transcript(s) to illustrate this influence.

For list-based or segmented video structures:
1. Analyze the transcript(s) to identify if the video follows a list-based or segmented structure, where distinct topics or segments are presented sequentially.
2. If a list-based structure is detected, identify the overall introduction (if any) and the recurring pattern for each list item or segment.
3. Create a template for the recurring segment, including:
   - Introduction format (e.g., "Item X: [Topic]")
   - Internal structure (explanation, examples, analysis, etc.)
   - Transition to the next segment
4. Use placeholders like [ITEM X] or [SEGMENT X] to represent each distinct topic or segment in the template.
5. Include specific examples from the transcript(s) to illustrate the structure and style of each segment.
6. Ensure that the total duration and individual segment durations match the transcript(s) precisely.
7. Note if there is a consistent conclusion segment after all list items or segments have been covered.
8. Analyze how the video title shapes the overall introduction and framing of the list or segments. Provide examples from the transcript(s) to illustrate how the title is incorporated into the setup and transitions between segments.


For educational, explainer, or documentary videos:
1. Identify the overall structure (introduction, main topics/sections, conclusion).
2. For each main topic or section, break down the internal structure and key points.
3. Use placeholders (e.g., [Topic X], [Key Point Y]) to make the template adaptable.
4. Include brief descriptions of the content or purpose of each key point.
5. Note transitions between major topics or sections.
6. Include the approximate duration of each major topic or section.
7. Examine how the video title influences the overall topic selection, framing, and introduction of the main sections or topics covered. Provide examples from the transcript(s) to illustrate how the title is incorporated into the setup and transitions between sections.


For narrative videos (sketches, web series):
1. Identify the overall story structure (setup, inciting incident, rising action, climax, falling action, resolution).
2. Break down the internal structure of each major story beat or plot point.
3. Use placeholders (e.g., [Character], [Conflict], [Resolution]) to make the template adaptable.
4. Include brief descriptions of the content or purpose of each plot point.
5. Note transitions between major story beats or plot points.
6. Include the approximate duration of each major story beat or plot point.
7. Analyze how the video title shapes the overall premise, character introductions, and initial setup of the narrative. Provide examples from the transcript(s) to illustrate how the title is incorporated into the story's setup and early plot points.


For commentary or scripted videos:
1. Identify the overall structure (introduction, main topics/segments, conclusion).
2. For each main topic or segment, break down the internal structure and key points.
3. Use placeholders (e.g., [Topic X], [Key Point Y]) to make the template adaptable.
4. Include brief descriptions of the content or purpose of each key point.
5. Note transitions between major topics or segments.
6. Include the approximate duration of each major topic or segment.
7. Examine how the video title influences the overall topic selection, framing, and introduction of the main segments or commentary points. Provide examples from the transcript(s) to illustrate how the title is incorporated into the setup and transitions between segments.

The goal is to create a flexible template that captures the essence of how information is presented in the specific video format, while allowing for different topics or segments to be inserted into the template structure.
"""


    assistant_message = """You arg an AI assistant specializing in analyzing video series structures. Your task is to process the given series name, theme, and provided transcript(s), then generate a comprehensive template that can be applied to future videos in the same series. This template should maintain the structure, style, and tone of the series while allowing for different video topics.

CRITICAL REQUIREMENT: ALL segments MUST be 10 minutes (600 seconds) or LESS in duration. NEVER create segments longer than 10 minutes, no matter what. If you identify a segment longer than 10 minutes, you MUST split it into multiple smaller segments with logical breakpoints. This is a hard constraint that cannot be violated under any circumstances.

IMPORTANT: When providing examples from transcripts, ALWAYS replace any specific channel names with the placeholder [CHANNEL_NAME]. Never use the actual channel name from the transcript. For example, instead of "Welcome to Morpheus Realm", use "Welcome to [CHANNEL_NAME]" or "Welcome to [HOST_NAME]".

Script Elements:
• Channel Greeting: "Welcome to [HOST_NAME] where..."


Your analysis should be based solely on the information present in the provided transcript(s). Do not add any speculative elements or recommendations that are not directly supported by the transcript(s).

For each series and theme, provide the following outputs:

1. Video Structure:
Present this as a list of segments: Time | Segment | Content | Duration
Analyze the transcript(s) to identify the key segments that form the structure of the series. Calculate and include the precise duration of each segment based on the transcript timestamps. Ensure the structure can be applied to different topics within the same theme, but only use information directly observed in the transcript(s).
if you notice that the video is basically just a list of items, give us the structure like intro, list 1, list 2, list 3, list 4, outro (if an outro exists.)

2. Segment Outline Template:
When creating the segment outline:
1. Identify the overall structure (intro, main incidents, secondary incidents, conclusion, etc.).
2. For each main segment type, break down the internal structure and plot points.
3. Use consistent placeholders (e.g., [Streamer], [Rapper]) to make the template adaptable.
4. Include brief descriptions of the content or purpose of each plot point.
5. Highlight any recurring patterns or elements within segments.
6. Note transitions between major segments.
7. Include the approximate duration of each major segment type.

Ensure that the outline captures not just the overall video structure, but also the narrative flow within each significant segment type. This approach should reveal how individual stories or incidents are typically presented and developed throughout the video.

Make sure to include the duration of each segment.

Example format:

a. Introduction (Duration):
   - [Plot point 1]
   - [Plot point 2]

b. Main Segment Structure (Average duration):
   - [Plot point 1] 
   - [Plot point 2]
   - ...
   - [Plot point 6-8]

c. Transition (Duration)

[Continue for all identified segment types]

3. Transition Techniques:
List 3-5 transition techniques observed in the transcript(s) that are likely to be consistent across the series. Include specific examples and timestamps from the transcript(s) for each technique.

4. Recurring Elements:
List 3-5 recurring elements or phrases that are characteristic of the series, based on the transcript(s). These should be elements that can be applied across different topics within the theme. Include the frequency and context of each element's appearance in the transcript(s).

5. Script Template:
Create a script template corresponding to the Segment Outline Template. 
Provide general script elements and placeholders that can be adapted for different topics within the series. Include specific examples from the transcript(s) for each segment and the calculated duration based on the transcript(s).

When creating the script template:
1. Include all major segment types identified in the Segment Outline Template.
2. For each segment, provide a clear and concise content description.
3. List 4-6 specific script elements that capture the narrative flow of the segment.
4. Use placeholders (e.g., [Streamer], [Rapper], [quote]) to make the template adaptable.
5. Include transition elements between segments where appropriate.
6. Provide specific examples or phrasings from the transcript(s) to illustrate the style.
7. Ensure the duration for each segment matches the analysis from the Video Structure section.
8. Document exact hook/intro phrasing and structure with timestamps
9. Note any recurring phrases, expressions or linguistic patterns
10. Capture tone shifts and pacing changes within segments

Example format:

Segment: Introduction/Hook
Content: Channel greeting, topic setup, and engagement hook
Word Count Target: [XXX] words
Script Elements:
• Channel Greeting: "[Exact channel greeting phrase]"
• Topic Introduction: "Today we're looking at [Number] [Subject] who [Action]"
• Hook Setup: "[Specific hook format from transcript]"
• Teaser Elements: "[Example 1], [Example 2]..."
• Engagement Question: "[Question format used]"
• Transition to Main Content: "[Transition phrase]"
Duration: [XX:XX]

For Clip-Reactive Content:
Segment: Opening Clip/Hook
Clip Duration: [XX:XX]
Commentary Duration: [XX:XX]
Script Elements:
• Clip Introduction: "[How the clip is introduced]"
• Key Commentary Points: "[Main reactions/observations]"
• Viewer Engagement: "[Questions/comments to engage viewers]"
• Transition: "[How to move to next clip]"
Total Duration: [XX:XX]

Note: For clip-reactive content, focus on:
- Duration-based timing rather than word count
- Natural reaction patterns
- Commentary that enhances but doesn't overshadow clips
- Smooth transitions between clips
- Maintaining viewer engagement through commentary style

[Continue with Main Segment, Secondary Incident, etc., following the same structure]

For listicle-format videos:
   - Analyze the transcripts to identify the recurring structure and patterns for list items
   - Create a comprehensive template that includes:
     a. Introduction segment with brief setup for the overall video topic
     b. Recurring list item structure with:
        - Introduction: "[ITEM X]: [Topic/Premise]" with specific timing
        - Explanation: Clear explanation of the core concept
        - Analysis: Examination of implications, theories, or principles
        - Counterpoints: Presentation of critiques or opposing viewpoints
        - Broader Context: Connections to larger themes or psychological impact
        - Conclusion: Summary of key points and final perspective
        - Transition: Smooth transition to the next item/segment
     c. Conclusion segment with overall summary or final thoughts
   - Use placeholders like [ITEM X] and [Topic/Premise] for adaptable content
   - Include specific examples from the transcripts to guide style and content
   - Ensure precise timing for each segment based on transcript analysis
   - Maintain consistent structure while allowing for topic variation

When processing the information, focus on creating a template that captures the essence of the series and can be easily applied to different video topics within the same theme. Use placeholder text (e.g., [Subject], [Event], [Date]) to create a flexible template.

Ensure that all sections are filled out completely, providing a comprehensive template that maintains the series' structure while allowing for topic variation. Pay particular attention to the timing and duration of segments, using the transcript timestamps for precise calculations.

Use only the information present in the provided transcript(s) as the basis for your analysis. Do not add any elements or recommendations that are not directly observed in the transcript(s). Provide specific examples, quotes, and timestamps from the transcript(s) to support each point in your analysis, especially in the script templates and other detailed sections."""

    # Process each transcript individually
    transcript_chunks = [[t] for t in transcripts]
    logger.info(f"Total transcript chunks: {len(transcript_chunks)}")
    all_breakdowns = []
    
    for i, chunk in enumerate(transcript_chunks):
        try:
            # Add video title and description to context
            title_line = ""
            description_line = ""
            if video_titles and i < len(video_titles):
                title_line = f"Video Title: {video_titles[i]}\n"
            if video_descriptions and i < len(video_descriptions):
                description_line = f"Video Description: {video_descriptions[i]}\n"
            
            # Extract transcript and duration
            transcript_data = chunk[0]
            transcript_text = transcript_data.get("transcript", "")
            video_duration = video_durations[i]
            potential_video_formats = [
                "Educational", "Narrative", "Commentary", "Listicle", "Gaming Content - Roleplay",
                "Challenge videos", "Pranks", "Gaming content (Let's Plays, walkthroughs)",
                "Reaction videos", "Vlogs", "Unboxing videos", "Q&A sessions",
                "Listicle videos (minimal commentary)", "Unscripted interviews",
                "Unscripted commentary", "Live streams", "Explainer videos", "Documentary",
                "Video essays", "Conspiracy theory videos", "Sketches", "Web series",
                "Scripted videos", "Product reviews", "Tutorials", "Gameplay videos",
                "Podcasts", "Talk shows", "News reports", "Interviews", "Animated videos",
                "Music videos", "Short films", "Commercials", "Trailers",
                "Behind-the-scenes videos", "Cooking shows", "Travel vlogs",
                "Comedy sketches", "Parodies", "Rants", "Storytimes", "Hauls",
                "Makeup tutorials", "Product demonstrations", "Fitness videos",
                "DIY videos", "Craft tutorials", "Unboxing videos", "Tech reviews",
                "Gear reviews", "Comparison videos", "Reaction videos", "Challenges",
                "Pranks", "Experiments", "Livestreams", "Podcasts", "Talk shows",
                "Debates", "Panel discussions", "Webinars", "Lectures", "Presentations",
                "Conferences", "Workshops", "Masterclasses", "Courses", "Tutorials",
                "How-to videos", "Guides", "Walkthroughs", "Playthroughs", "Speedruns",
                "Esports events", "Game reviews", "Game analysis", "Game lore videos",
                "Fan theories", "Retrospectives", "Commentaries"
            ]

            user_message = f"""Series: {series_name}
            Theme: {theme_name}
            {title_line}
            {description_line}
            Important Context:
            - Analyzing {len(transcripts)} videos from the same series & theme
            - Current transcript breakdown: {i + 1} of {len(transcript_chunks)}
            - Video Duration: {video_duration} seconds
            - Purpose: Looking for common patterns, structures, timing, and storytelling elements
            - Potential video formats to consider: {', '.join(potential_video_formats)}
            - CRITICAL REQUIREMENT: ALL segments MUST be 10 minutes (600 seconds) or LESS in duration. Never create segments longer than 10 minutes.

            Transcript Analysis for "{video_titles[i]}":
            {transcript_text}

            Instructions:
            1. Carefully review the provided transcript(s) and identify the overall video structure and format based on the content and flow of information, considering the potential video formats provided.
            2. Refer to the specific instructions in the system message for the identified video format (e.g., list-based, educational, narrative, commentary).
            3. Follow those instructions to create a comprehensive Segment Outline Template, Script Template, and other required analyses.
            4. Use the provided examples and placeholders to ensure the templates are adaptable for different topics within the same series and theme.
            5. Include specific quotes, timestamps, and examples from the transcript(s) to support your analysis and illustrate the structure, style, and tone of the series.
            6. Pay close attention to the timing and duration of segments, using the transcript timestamps for precise calculations.
            7. Note any recurring elements, transition techniques, or other patterns that are characteristic of the series and should be maintained in future videos.
            8. Ensure your analysis and templates accurately capture the essence of how information is presented in this series, while allowing for topic variation.
            9. NEVER create segments longer than 10 minutes (600 seconds). If you identify a longer segment from the transcript, split it into multiple smaller segments with logical breakpoints.

            Remember, your goal is to create a flexible template that can be used to maintain consistency and quality for future videos in the same series and theme. Use the provided context, instructions, and examples to guide your analysis and template creation.
            """
            response = await asyncio.to_thread(
                client.messages.create,
                model="claude-3-7-sonnet-20250219",
                max_tokens=10000,
                temperature=0.2,
                system=system_message,
                messages=[
                    {"role": "assistant", "content": assistant_message},
                    {"role": "user", "content": user_message}
                ]
            )
            
            all_breakdowns.append(response.content[0].text)
            logger.info(f"Chunk {i + 1} processed successfully.")
        except Exception as e:
            logger.error(f"Error generating script breakdown for transcript {i+1}: {str(e)}", exc_info=True)
            continue
    
    # Merge individual transcript analyses
    if len(all_breakdowns) > 1:
        try:
            merge_message = f"""Combine these {len(all_breakdowns)} transcript breakdowns for {series_name} - {theme_name} into one fully fleshed out, comprehensive analysis that reflects all the details (including timing, segment breakdowns, and storytelling elements) from each video:
            
Breakdowns:
{'-' * 40}
""" + f"\n{'-' * 40}\n".join(all_breakdowns)
            
            final_response = await asyncio.to_thread(
                client.messages.create,
                model="claude-3-7-sonnet-20250219",
                max_tokens=10000,
                temperature=0.4,
                system=system_message,
                messages=[
                    {"role": "assistant", "content": assistant_message},
                    {"role": "user", "content": merge_message}
                ]
            )
            
            final_breakdown = final_response.content[0].text
            logger.info("Successfully merged chunks.")
        except Exception as e:
            logger.error(f"Error merging breakdowns: {str(e)}", exc_info=True)
            final_breakdown = all_breakdowns[0] if all_breakdowns else ""
    else:
        final_breakdown = all_breakdowns[0] if all_breakdowns else ""
    
    # Determine clip-reactivity
    is_clip_reactive = "false"
    if "is_clip_reactive: true" in final_breakdown.lower():
        is_clip_reactive = "true"
    
    logger.info(f"Final breakdown is_clip_reactive: {is_clip_reactive}")
    final_breakdown = f'{{"is_clip_reactive": {is_clip_reactive}, "script_breakdown": {final_breakdown}}}'
    
    return final_breakdown

async def chunk_transcripts(transcripts) -> List[List[Dict[str, Union[str, float]]]]:
    """Split transcripts into chunks that won't exceed token limits"""
    CHARS_PER_TOKEN = 4  # Rough estimate of tokens per character
    
    # Ensure transcripts is a list of dictionaries
    if isinstance(transcripts, str):
        transcripts = [{'text': transcripts}]
    elif isinstance(transcripts, list):
        if all(isinstance(t, str) for t in transcripts):
            transcripts = [{'text': t} for t in transcripts]
    
    transcript_chunks = []
    current_chunk = []
    current_length = 0
    
    for transcript in transcripts:
        # Ensure we're working with a dictionary
        if isinstance(transcript, str):
            transcript = {'text': transcript}
            
        text = transcript.get('text', '')
        estimated_tokens = len(text) / CHARS_PER_TOKEN
        
        if current_length + estimated_tokens > 8000:
            transcript_chunks.append(current_chunk)
            current_chunk = []
            current_length = 0
            
        current_chunk.append(transcript)
        current_length += estimated_tokens
        
    if current_chunk:
        transcript_chunks.append(current_chunk)
        
    return transcript_chunks

async def analyze_thumbnail(series: Dict[str, Any], theme: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"""
    Given the following series and theme:
    Series: {series['name']}
    Theme: {theme['name']}

    Analyze and recommend elements for an effective thumbnail design. Consider the genre, target audience, and current YouTube trends.

    Format your response as a Python dictionary with the following structure:
    {{
        "recommended_elements": [
            "Element 1",
            "Element 2",
            ...
        ],
        "color_scheme": ["#ColorHex1", "#ColorHex2", "#ColorHex3"],
        "text_placement": "Description of text placement"
    }}
    """
    response = await generate_ai_response(prompt, max_tokens_to_sample=2000)
    try:
        analysis = eval(response)
        if not isinstance(analysis, dict) or not all(key in analysis for key in ["recommended_elements", "color_scheme", "text_placement"]):
            raise ValueError("Invalid response format")
        return analysis
    except Exception as e:
        logger.error(f"Error processing AI response for thumbnail analysis: {str(e)}")
        return {
            "recommended_elements": [f"Error analyzing thumbnail for {series['name']} - {theme['name']}"],
            "color_scheme": ["#000000"],
            "text_placement": "Error determining text placement"
        }


async def generate_plot_outline(
    title: str, 
    guidelines: str, 
    series: Dict[str, Any], 
    theme: Dict[str, Any], 
    video_length: float, 
    customization: Dict[str, Any] = None,
    enable_research: bool = False,
    max_retries: int = 5
) -> str:  # Update return type to just str
    # Add research capability
    research_data = ""
    research_articles = []  # To return for full script
    
    if enable_research:
        try:
            logger.info(f"Performing fresh research for plot outline: {title}")
            
            # Create focused search based on title and series/theme
            search_query = f"{title} {series['name']} {theme['name']} details facts information"
                
            # Get research specifically for plot structure
            research_results = await research_with_gemini(
                search_query, 
                research_type="plot",
                max_results=3
            )
            
            # Format research for Claude
            if research_results:
                logger.info(f"Found {len(research_results)} research articles for plot outline")
                
                # Process results for plot structure
                research_data = "\n\n## CURRENT RESEARCH FINDINGS (incorporate these facts):\n\n"
                
                for i, result in enumerate(research_results, 1):
                    source_title = result.get('source_title', '')
                    key_facts = result.get('key_facts', [])
                    quote = result.get('quote', '')
                    segment_ideas = result.get('segment_suggestions', [])
                    
                    research_data += f"### Source {i}: {source_title}\n\n"
                    
                    # Add key facts
                    if key_facts:
                        research_data += "Key Facts:\n"
                        for fact in key_facts:
                            research_data += f"- {fact}\n"
                        research_data += "\n"
                    
                    # Add quote
                    if quote:
                        research_data += f"Quote: \"{quote}\"\n\n"
                    
                    # Add segment ideas
                    if segment_ideas:
                        research_data += "Segment Ideas:\n"
                        for idea in segment_ideas:
                            research_data += f"- {idea}\n"
                        research_data += "\n"
                    
                    # Save for returning to full script
                    research_articles.append({
                        'title': source_title,
                        'url': result.get('url', ''),
                        'key_facts': key_facts,
                        'quote': quote
                    })
        except Exception as e:
            logger.error(f"Error performing research for plot outline: {str(e)}")
            # Continue without research if it fails

    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    # Convert video_length to a formatted string for better clarity
    duration_str = ""
    if video_length >= 60:
        hours = int(video_length // 60)
        minutes = video_length % 60
        duration_str = f"{hours}h{minutes:02.0f}m" if minutes else f"{hours}h"
    elif video_length >= 1:
        duration_str = f"{video_length:.2f}m"
    else:
        duration_str = f"{video_length * 60:.0f}s"

    logger.info(f"Starting plot outline generation for title: {title}, series: {series['name']}, theme: {theme['name']}")
    logger.debug(f"Video length: {duration_str}")
    logger.debug(f"Guidelines excerpt: {guidelines[:100]}...")

    system_message = """You are an AI assistant specializing in creating comprehensive, production-ready plot outlines for video content. Your primary goal is to generate a clear, time-segmented plot outline that strictly adheres to the provided series guidelines, maintaining the structure, tone, style, and pacing of the original series, while offering practical guidance for content creators.

    Follow these steps: DO NOT use generic placeholders like "[Continue with similar detailed breakdowns for remaining segments...]". Generate unique content for each segment.

    1. Thoroughly analyze the provided series guidelines, paying close attention to the "Segment Outline Template" section, as this will play a major role in shaping the structure and format of the plot outline.

    2. Create a detailed plot outline using the following format:

Video Title: [Title]
Total Duration: [Duration in H:MM:SS format] ([Duration] minutes)

Video Structure: 
[If applicable: Based on the example timeline patterns and scaled for duration, maintaining similar ratios:]

1. [Segment Name] (HH:MM:SS - HH:MM:SS, Duration: HH:MM:SS)
2. [Segment Name] (HH:MM:SS - HH:MM:SS, Duration: HH:MM:SS)

You MUST list out EVERY SINGLE SEGMENT in the Video Structure section with exact timestamps
    2. If the video is 2 hours long, list out ALL segments for the full 2 hours
    3. If there are 26 segments, write out ALL 26 segments
    4. NEVER use phrases like:
       ❌ "[Continue with similar detailed breakdowns for remaining segments...]"
       ❌ "Would you like me to continue?"
       ❌ "[Similar segments until HH:MM:SS]"
    5. NO SHORTCUTS OR PLACEHOLDERS ALLOWED

Detailed Segment Breakdown:

IMPORTANT: For the Detailed Segment Breakdown section, ONLY provide detailed breakdowns for:
1. The first example of each UNIQUE segment structure or format
2. Any segments that require special treatment according to the guidelines
3. DO NOT write detailed breakdowns for segments that follow the same structure as already detailed segments
4. After each detailed segment, add a note like: "(Note: Segments X, Y, and Z follow this same structural pattern)"

[Segment Name] (HH:MM:SS - HH:MM:SS, Duration: HH:MM:SS)
[Sub-segment Name] (HH:MM:SS - HH:MM:SS)
- [Key point with specific details]
- [Key point with specific details]
- [Key point with specific details]
[... continue for all sub-segments]

[Next Unique Segment Type] (HH:MM:SS - HH:MM:SS, Duration: HH:MM:SS)
[... continue only for unique segment types]

    3. For each segment:
       a. USE GUIDELINE SEGMENT STRUCTURE AND TIMING, but RENAME THE SEGMENT TITLES to be STORY‑SPECIFIC and audience‑facing.
          - Do NOT copy guideline labels like "Opening Title", "Emergency Broadcast Introduction", "Primary Warning Signs", "Safety Instructions", or "Broadcast Sign-off" as final titles.
          - Craft short, evocative titles (2–6 words) derived from the video title and the actual content.
          - Avoid generic labels (Introduction/Conclusion/Safety/Broadcast/Overview) and production jargon.
          - Example renames for a topic like "Do NOT Look Under Your Bed Tonight":
            • "Opening Title" → "When the Room Goes Still"
            • "Emergency Broadcast Introduction" → "Do Not Look Down"
            • "Primary Warning Signs" → "Scratches Beneath the Springs"
            • "Secondary Warning Signs" → "Sheets That Breathe Back"
            • "Danger Explanation" → "What Lives Underneath"
            • "Safety Instructions" → "Survive Until Morning"
            • "Emergency Contact Information" → "If It Whispers Your Name"
            • "Broadcast Sign-off" → "Keep Your Feet Up"
       b. Calculate the start and end times based on the segment duration and the total video duration, ensuring they sum up correctly.
       c. Include a detailed description in the table row, providing comprehensive context, research, and factual information relevant to the segment.
       d. Below the table row, add 3-4 concise key points that offer specific guidance and context thats align with the guidelines, without inventing facts.
       e. Incorporate any formatting or structure specified in the guidelines, such as day structure (Day 1, Day 2, etc.) or specific content requirements.
       f. DO NOT use generic placeholders like "[Continue with similar detailed breakdowns for remaining segments...]". Generate unique content for each segment.

    4. Ensure the total duration and segment durations match exactly with those provided in the guidelines.

    5. Include any technical notes, production guidance, transition techniques, or recurring elements explicitly provided in the guidelines.

    6. For videos covering multiple subjects or list items, adjust the segment structure accordingly, keep the average duration per list item
     and figure out whetever you need to add more segments or take away from others to keep the pacing consistent.

    7. For listicle-format videos (e.g., "Top 10", "When X Happens"):
       a. Extract and analyze segment patterns from example timeline:
          - Calculate actual min, max, and average durations from examples
          - Note: Trust example timelines over stated averages
          - Example: If timeline shows "6:29, 14:29, 18:08, 12:55, 13:46"
            → Real range: 6-18 minutes
            → Most common: 12-15 minutes
            → Outliers: One short (6min), one long (18min)
       
       b. Calculate total segments needed:
          - Total video length / actual average from examples
          - Round to whole number that allows proper pacing
          - Example: 210min video with 13min average = ~16-18 segments
       
       c. Distribute segment lengths following example patterns:
          - Most segments: Use the most common duration (e.g., 12-15min)
          - Few shorter segments: Match shortest example (e.g., 6-7min)
          - Few longer segments: Match longest example (e.g., 18min)
          - Maintain ratio of short/medium/long segments from examples
       
       d. Provide structure for each segment without inventing details
       e. Include general guidelines for content based on theme
       f. Avoid specific dates/names unless in title/guidelines

    8. Emphasize flexibility:
       a. The outline should allow for easy adaptation based on available content.
       b. Provide options for different types of incidents or items that could fit the theme, based on the guidelines.
       c. Include a note that the final content will depend on available footage or verified incidents.

    9. Keep the introduction segment concise, aiming for a maximum duration of 15 seconds, unless the guidelines specify otherwise.

     10. ⚠️ CRITICAL SEGMENT DURATION REQUIREMENTS ⚠️
        a. ABSOLUTELY NO SEGMENT should EVER exceed 10 minutes (600 seconds) in duration - this is a HARD REQUIREMENT
        b. Each segment MUST be 10 minutes or less - NO EXCEPTIONS WHATSOEVER
        c. For long-form content (1+ hours), create MORE segments rather than longer segments
        d. Split any segment that would be longer than 10 minutes into multiple connected segments
        e. This requirement overrides any contradictory instructions in the guidelines
   
   
   ‼️ ABSOLUTELY CRITICAL RULES ‼️
    1. You MUST list out EVERY SINGLE SEGMENT in the Video Structure section with exact timestamps
    2. If the video is 2 hours long, list out ALL segments for the full 2 hours
    3. If there are 26 segments, write out ALL 26 segments
    4. NEVER use phrases like:
       ❌ "[Continue with similar detailed breakdowns for remaining segments...]"
       ❌ "Would you like me to continue?"
       ❌ "[Similar segments until HH:MM:SS]"
    5. NO SHORTCUTS OR PLACEHOLDERS ALLOWED

    
    Remember: Your primary objective is to create a comprehensive, actionable plot outline that precisely follows the provided guidelines, capturing the essence of the original series in terms of structure, tone, style, and pacing. Adherence to the guidelines and maintaining consistency with the existing series is crucial. Focus on translating the given structure into a detailed, easy-to-implement format for the specific video topic, including any formatting requirements or content specifications outlined in the guidelines."""

    user_message = f"""Generate a comprehensive plot outline based on the following information:

    1. Series Name: {series['name']}
    2. Theme: {theme['name']}
    3. Video Topic: {title}
    4. Desired Video Duration: {duration_str}
    
    YOUR RESPONSE MUST FOLLOW THIS EXACT FORMAT:

    Video Title: [Title]
    Total Duration: [Duration in H:MM:SS format] ([Duration] minutes)

    Video Structure:
    [If applicable: Based on the example timeline patterns and scaled for duration, maintaining similar ratios:]

    1. [Segment Name] (HH:MM:SS - HH:MM:SS, Duration: HH:MM:SS)
    2. [Segment Name] (HH:MM:SS - HH:MM:SS, Duration: HH:MM:SS)

    Detailed Segment Breakdown:

    [Segment Name] (HH:MM:SS - HH:MM:SS, Duration: HH:MM:SS)
    [Sub-segment Name] (HH:MM:SS - HH:MM:SS)
    - [Key point with specific details]
    - [Key point with specific details]
    - [Key point with specific details]
    [... continue for all sub-segments]

    [Next Segment Name] (HH:MM:SS - HH:MM:SS, Duration: HH:MM:SS)
    [... continue for all segments]

    REQUIREMENTS:
    - Keep fixed-length segments (intros, transitions, outros) at their original durations. IF THE GUIDELINES DONT HAVE AN INTRO OR OUTRO DONT INCLUDE ONE.
    - Scale main content segments proportionally while maintaining the established pacing ratios
    - Ensure all segment durations sum up exactly to {duration_str}
    - Provide comprehensive context, research, and details for each segment
    - Maintain consistency with the existing series in terms of structure, tone, style, and pacing
    - Do not use placeholders like "[RESEARCH: ...]" for research or content
    - DO NOT use generic placeholders like "[Continue with similar detailed breakdowns for remaining segments...]"
    - Generate unique content for each segment
    - Use exact HH:MM:SS format for all timestamps
    - Include 3-5 specific key points for each sub-segment

    TITLING RULES (CRITICAL):
    - Keep the guideline segment STRUCTURE and TIMING, but RENAME every segment title to be story‑specific and derived from the video topic.
    - Absolutely NO generic guideline names (e.g., "Opening Title", "Emergency Broadcast Introduction", "Primary Warning Signs", "Safety Instructions", "Broadcast Sign-off").
    - Titles should be 2–6 words, evocative, audience‑facing, and reflect the actual beat of the segment.
    - Examples for a topic like "Do NOT Look Under Your Bed Tonight":
      • "Opening Title" → "When the Room Goes Still"
      • "Emergency Broadcast Introduction" → "Do Not Look Down"
      • "Primary Warning Signs" → "Scratches Beneath the Springs"
      • "Secondary Warning Signs" → "Sheets That Breathe Back"
      • "Danger Explanation" → "What Lives Underneath"
      • "Safety Instructions" → "Survive Until Morning"
      • "Emergency Contact Information" → "If It Whispers Your Name"
      • "Broadcast Sign-off" → "Keep Your Feet Up"

    ⚠️ CRITICAL SEGMENT DURATION REQUIREMENTS ⚠️
    - ABSOLUTELY NO SEGMENT should EVER exceed 10 minutes (600 seconds) in duration - this is a HARD REQUIREMENT
    - Each segment MUST be 10 minutes or less - NO EXCEPTIONS WHATSOEVER
    - For long-form content (1+ hours), create MORE segments rather than longer segments
    - Split any segment that would be longer than 10 minutes into multiple connected segments
    - This requirement overrides any contradictory instructions in the guidelines.
    - follow guidelines for anything suggesting segments under 10 minutes.

    YOU MUST:
    1. Calculate total segments needed based on total duration and segment length
    2. List out EVERY SINGLE SEGMENT with exact timestamps
    3. Continue until reaching {duration_str} exactly
    4. NEVER use any form of "continuing" or "remaining segments"
    5. Write out every segment even if it's 100 segments
    6. NEVER create segments longer than 10 minutes - split them into multiple parts instead


    Guidelines: {guidelines}
    Video Title Influence: {guidelines}['video_title_influence']"""
    
    # Add research data to user message if available
    if research_data:
        user_message += f"\n\n{research_data}"
    
    # Initial call to generate the plot outline
    for attempt in range(max_retries):
        try:
            response = await client.messages.create(
                model="claude-3-7-sonnet-20250219",
                max_tokens=10000,
                temperature=0.7,
                system=system_message,
                messages=[{"role": "user", "content": user_message}]
            )
            plot_outline = response.content[0].text
            logger.info("Plot outline generated successfully")
            break
        except Exception as e:
            logger.error(f"Error in generate_plot_outline (attempt {attempt + 1}): {str(e)}")
            if attempt == max_retries - 1:
                logger.error("Max retries reached. Returning error message.")
                return f"Error generating plot outline: {str(e)}"
            await asyncio.sleep(2 ** attempt)
    else:
        return f"Error generating plot outline: Max retries reached"

    # Check exclusively the video structure part for continuation markers (e.g. "Would you like me to continue")
    continuation_prompt = "Would you like me to continue"
    additional_attempts = 0
    max_continuations = 3  # Prevent infinite loops

    while additional_attempts < max_continuations and continuation_prompt.lower() in plot_outline.lower():
        logger.info("Detected continuation prompt in the VIDEO STRUCTURE portion. Triggering follow-up to complete ONLY the video structure part.")
        try:
            cont_response = await client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=8192,
                temperature=0.7,
                system=system_message,
                messages=[
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": plot_outline},
                    {"role": "user", "content": (
                        "Continue ONLY the video structure part of the plot outline from the last segment. "
                        "IMPORTANT: You must list out EVERY SINGLE SEGMENT in the video structure section with exact timestamps as per the critical rules. "
                        "Do NOT include any questions, prompts, or placeholders (e.g., 'Would you like me to continue?'). "
                        "Please provide only the remaining segments, formatted exactly as required."
                    )}
                ]
            )
            continuation_text = cont_response.content[0].text
            plot_outline += "\n" + continuation_text  # Append the continuation text
            additional_attempts += 1
        except Exception as e:
            logger.error(f"Error during continuation attempt {additional_attempts + 1}: {str(e)}")
            break

    # Final plot_outline is now fully completed and formatted for generate_full_script.
    return plot_outline  # Return only the plot_outline, not the tuple
def calculate_segment_timestamps(segment_durations, total_duration):
    timestamps = []
    current_time = 0

    for duration in segment_durations:
        start_time = current_time
        end_time = current_time + duration
        timestamps.append((start_time, end_time))
        current_time = end_time

    # Adjust the last segment's end time to match the total duration
    timestamps[-1] = (timestamps[-1][0], total_duration)

    return timestamps

async def generate_full_script(
    title: str,
    plot_outline: str,
    script_breakdown: str,
    series: Dict[str, Any],
    theme: Dict[str, Any],
    video_length: float,
    characters: List[str] = None,
    research_articles: List[str] = None,
    host_name: str = None,
    sponsored_info: Dict[str, str] = None,
    max_retries: int = 5
) -> tuple[str, Dict[str, Any]]:
    # Add token tracking variables
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0
    segment_costs = []

    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    
    system_message = """You are an AI assistant specialized in creating precisely timed video scripts for YouTube content. Your primary task is to generate detailed, engaging scripts with strict adherence to specified durations.

CORE FORMATTING REQUIREMENTS:
1. Timing Precision: Use 150 words per minute as baseline. Calculate exact word count for each segment.
2. Segment Format: "Chapter Name (Timestamp - Timestamp, Duration: X:XX)"
   Example: Introduction (00:00 - 02:15, Duration: 02:15)
3. Character Format: ALWAYS use bracketed names. Example: [CHARACTER_NAME]: Dialogue text.
4. Each line MUST begin with [CHARACTER_NAME]: format - this is CRITICAL for voice generation.
5. Introduction/Outro: Unless specified, keep intro under 10 seconds (25 words) with teaser from 60% point.

CONTENT REQUIREMENTS BY TYPE:
1. Scary Stories: Write complete original narratives with full story development. Include character actions, climactic moments, and sensory details. NO placeholders.
2. Listicle Format: Use placeholders [ITEM X] when needed. Create adaptable structure for easy editing later.
3. Clip-Dependent Videos: Use format [CLIP X: Description]. Include timing guidelines and generic narration cues.
4. Educational Content: Focus on accuracy and clarity. Use [RESEARCH] only when necessary.
5. Sponsored Content: Integrate naturally after hook but before main content. Format as:
   SPONSORED SEGMENT (Duration: X:XX)
   [SPONSOR_NAME]: Product description
   Key messaging points
   Natural transition to main content

FORMAT ADHERENCE CRITICAL POINTS:
1. Follow all template guidelines provided in script_breakdown
2. Include all recurring elements mentioned in guidelines
3. Maintain segment timestamps exactly as specified
4. Include accurate transitions between segments
5. Ensure word counts match duration requirements
6. Cross-check against plot outline to include all key points
7. For long segments, maintain narrative flow between chunks

🎭 WRITING STYLE ADHERENCE (CRITICAL):
1. Analyze the "Writing Style Analysis" section in script_breakdown thoroughly
2. Mirror the authentic writing voice identified in the guidelines:
   - Sentence structure patterns (short vs long, complex vs simple)
   - Vocabulary choices and tone requirements
   - Emotional intensity and pacing guidelines
   - Rhetorical devices (repetition, alliteration, metaphors, analogies)
   - Character voice consistency and differentiation
   - Transitional language patterns
   - Engagement techniques (direct questions, hypotheticals, callbacks)
   - Descriptive language requirements (specificity vs generality)
   - Cultural reference patterns and frequency
   - Callback and foreshadowing techniques
3. Apply writing style guidelines to each segment:
   - Use the identified sentence structure patterns
   - Employ the same vocabulary level and tone
   - Match emotional intensity curves
   - Include the same rhetorical devices
   - Maintain character voice consistency
   - Use the same engagement techniques
   - Apply descriptive language patterns
   - Include cultural references appropriately
   - Implement callback and foreshadowing patterns
4. Ensure the script feels authentic to the original series voice
5. Don't just follow structure - replicate the writing style and narrative voice

PROHIBITED CONTENT:
- NO meta-commentary or statements like "Here's the script"
- NO editor notes unless absolutely necessary
- NO word counts embedded in the final script
- NO deviation from specified format
- NO content outside the plot outline
- NO generic writing that doesn't match the identified style

Remember: Every line MUST start with [CHARACTER_NAME]: and adhere to exact timing requirements. Calculate all word counts based on 150 words per minute. MOST IMPORTANTLY: Write in the authentic voice identified in the writing style analysis.
"""
    # Set a static previous context to avoid carrying over any text.
    previous_context = "Starting fresh"

    # Extract segments from the plot outline
    segments = await extract_segments(plot_outline)
    # Remove logger.info
    # logger.info(f"Extracted {len(segments)} segments from the video structure.")

    # Extract Video Structure block for reference
    try:
        video_structure = plot_outline.split('Video Structure:')[1].split('Detailed Segment Breakdown:')[0].strip()
    except IndexError:
        video_structure = ""

    script_segments = []
    
    # Initialize prompt cache for segment processing
    segment_prompt_cache = {}

    # Add a function to clean generated scripts
    def clean_script(script_text, is_first_chunk=False, segment_header=""):
        """
        Remove meta-commentary, duplicate headers, and ensure proper formatting.
        """
        # Remove any "I understand" or similar meta-commentary at the beginning
        script_text = re.sub(r'^I understand[^\.]+\.\s*', '', script_text, flags=re.IGNORECASE)
        script_text = re.sub(r'^Understood\.[^\.]+\.\s*', '', script_text, flags=re.IGNORECASE)
        script_text = re.sub(r'^I will[^\.]+\.\s*', '', script_text, flags=re.IGNORECASE)
        script_text = re.sub(r'^I\'ll[^\.]+\.\s*', '', script_text, flags=re.IGNORECASE)
        script_text = re.sub(r'^Here is[^\.]+\.\s*', '', script_text, flags=re.IGNORECASE)
        script_text = re.sub(r'^Following[^\.]+\.\s*', '', script_text, flags=re.IGNORECASE)
        script_text = re.sub(r'^As requested[^\.]+\.\s*', '', script_text, flags=re.IGNORECASE)
        
        # If this is not the first chunk, remove any headers
        if not is_first_chunk and segment_header:
            script_text = re.sub(rf'{re.escape(segment_header)}\s*\([^)]+\)[^\n]*\n', '', script_text)
        
        # Remove any "Word count: X" at the end or elsewhere in the text
        script_text = re.sub(r'[,\s]*Word count:?\s*\d+\s*$', '', script_text)
        script_text = re.sub(r'[,\s]*\d+\s*words?\s*$', '', script_text)
        script_text = re.sub(r'[,\s]\d+$', '', script_text)  # Catch bare numbers at end
        
        # Make sure all dialogue lines start with a character name in brackets
        lines = script_text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # Skip empty lines
            if not line_stripped:
                cleaned_lines.append(line)
                continue
                
            # IMPORTANT FIX: Check if line is a segment header and preserve it as-is
            if re.match(r'^.+\(\d{2}:\d{2}:\d{2}\s*-\s*\d{2}:\d{2}:\d{2},\s*Duration:', line_stripped) or \
               re.match(r'^.+\(\d{2}:\d{2}:\d{2}\s*-\s*\d{2}:\d{2}:\d{2},\s*Duration:', line_stripped) or \
               (segment_header and line_stripped.startswith(segment_header)):
                cleaned_lines.append(line)
                continue
                
            # Check if line starts with a properly formatted character name
            if not re.match(r'^\s*\[[^\]]+\]:', line):
                # Only convert lines that appear to be dialogue but are missing the character tag
                # Look for dialogue indicators like quotation marks or narrative style
                if (line_stripped.startswith('"') or 
                    re.match(r'^[A-Z][a-z]+\s+[a-z]+', line_stripped) or 
                    re.search(r'said|asked|replied|exclaimed', line_stripped)):
                    line = f"[{host_name if host_name else 'NARRATOR'}]: {line_stripped}"
            
            cleaned_lines.append(line)
            
        return '\n'.join(cleaned_lines)

    # Define a function to process a single segment
    async def process_segment(idx, segment, cache_key=None):
        """Process a single segment and return it with its index to maintain order."""
        # Add nonlocal declaration to access the parent function's variables
        nonlocal total_input_tokens, total_output_tokens, total_cost, segment_costs, segment_prompt_cache
        
        # Calculate the target word count
        dur_parts = segment['duration'].split(':')
        if len(dur_parts) == 2:
            minutes = int(dur_parts[0]) + int(dur_parts[1]) / 60.0
        else:
            hours = int(dur_parts[0])
            minutes = hours*60 + int(dur_parts[1]) + int(dur_parts[2]) / 60.0
        
        # Use 170 words per minute as target
        target_word_count = int(minutes * 170)
        min_word_count = int(minutes * 160)  # Absolute minimum acceptable
        
        # Check if segment is extremely long and needs chunking
        needs_chunking = min_word_count > 1600  # Lower threshold to catch 10+ minute segments
        chunk_count = 1
        
        # Prepare the segment header exactly once
        segment_header = f"{segment['name']} ({segment['timestamp']}, Duration: {segment['duration']})"
        
        logger.info(f"Segment {idx+1} details: Target word count: {target_word_count}, Chunking: {'Yes' if needs_chunking else 'No'}")
        
        if needs_chunking:
            # Calculate how many chunks we need (aim for ~2000 words per chunk)
            chunk_count = math.ceil(min_word_count / 2000)
            logger.info(f"Segment {idx+1} will be split into {chunk_count} chunks")
            
            # Prepare for chunked generation
            chunk_scripts = []
            words_per_chunk = min_word_count // chunk_count
            
            # Generate each chunk
            for chunk_idx in range(chunk_count):
                chunk_valid = False
                chunk_attempts = 0
                max_chunk_attempts = 3  # Fewer attempts per chunk
                
                while not chunk_valid and chunk_attempts < max_chunk_attempts:
                    try:
                        # Determine chunk position (first, middle, last)
                        position = "beginning of" if chunk_idx == 0 else "end of" if chunk_idx == chunk_count-1 else "middle of"
                        
                        # Check if we're using caching and if this is not the first attempt or first chunk
                        use_cached_prompt = cache_key and (chunk_attempts > 0 or chunk_idx > 0)
                        
                        if use_cached_prompt and cache_key in segment_prompt_cache:
                            # Use a condensed prompt with Claude's prompt caching mechanism
                            user_message = f"""Generate chunk {chunk_idx+1}/{chunk_count} for the {position} segment {idx+1}/{len(segments)} "{segment['name']}" for "{title}":

This is a continuation of our conversation about creating a script segment.
Use the same guidelines and requirements as before.

Segment Details:
- Full segment name: {segment['name']}
- Timestamp: {segment['timestamp']}
- Total segment duration: {segment['duration']}
- This is chunk {chunk_idx+1} of {chunk_count}
- Required words: ~{words_per_chunk} words

Previous chunks context: {", ".join(chunk_scripts[:50]) if chunk_scripts else "This is the first chunk"}

Remember to format all dialogue with character names in brackets like [{host_name if host_name else 'NARRATOR'}]:
"""
                        else:
                            # Store full prompt in cache for this segment
                            user_message = f"""Generate chunk {chunk_idx+1}/{chunk_count} for the {position} segment {idx+1}/{len(segments)} "{segment['name']}" for "{title}":

Segment Details:
- Full segment name: {segment['name']}
- Timestamp: {segment['timestamp']}
- Total segment duration: {segment['duration']}
- This is chunk {chunk_idx+1} of {chunk_count} for this segment
- Required words for this chunk: ~{words_per_chunk} words

⚠️ CRITICAL REQUIREMENT: Your chunk MUST contain AT LEAST {words_per_chunk} words AND follow the EXACT format guidelines below.

⚠️ VOICE GENERATION WARNING: Your output will be processed by a voice generation system that CANNOT handle any content except the segment header and proper dialogue lines. Any other text will cause serious errors.

⚠️⚠️ CRITICAL HOST NAME REPLACEMENT REQUIREMENTS ⚠️⚠️:
- ALWAYS use [{host_name if host_name else 'NARRATOR'}] as the main narrator
- NEVER use any channel names like "sleep theories", "morpheus realm", or other channel names
- DO NOT copy channel names from guidelines or script_breakdown
- ALWAYS replace channel-specific phrases like "Welcome to sleep theories" with "Welcome to {host_name if host_name else 'our channel'}"
- ALWAYS replace ALL channel-specific references with [{host_name if host_name else 'NARRATOR'}]
- CHECK EVERY LINE OF DIALOGUE to ensure no channel names appear
- This is ABSOLUTELY CRITICAL for proper voice generation

FORMATTING REQUIREMENTS:
1. STRICT FORMAT ADHERENCE:
   • For first chunk only: Start with the segment header exactly as shown below
   • ALWAYS enclose character names in square brackets, like [CHARACTER_NAME]
   • Every line of dialogue MUST be preceded by a character name in this format
   • Use [{host_name if host_name else 'NARRATOR'}] as the main narrator unless specified otherwise
   • DO NOT introduce random new characters not mentioned in the provided list
   • DO NOT include editor notes, word counts, or any meta-commentary
   • DO NOT include scene descriptions without dialogue tags

2. EXAMPLE FORMAT:
   {segment['name']} ({segment['timestamp']}, Duration: {segment['duration']})

   [{host_name if host_name else 'NARRATOR'}]: Continuous dialogue that covers the content...
   [{host_name if host_name else 'NARRATOR'}]: More dialogue continuing the narrative...

3. CHARACTER FORMAT EXAMPLES:
   [{host_name if host_name else 'NARRATOR'}]: The story continues as we explore...
   {f"[{characters[0]}]: Dialogue for this character..." if characters else ""}

4. INSTRUCTIONS:
   • You are writing part {chunk_idx+1} of {chunk_count} of segment "{segment['name']}"
   • Write EXACTLY {words_per_chunk} words of continuous content
   • For first chunk: Include the segment header exactly as shown above
   • For middle/final chunks: Continue the story without headers
   • Maintain consistent style and narrative flow between chunks
   • DO NOT include meta-commentary or word counts in the text
   • DO NOT repeat content from other chunks
   • STRICTLY adhere to the character formatting with names in brackets

5. PROHIBITED CONTENT - NEVER INCLUDE:
   • "Here's the script" or "Here's the continuation" phrases
   • Editor notes like "[NOTE TO EDITOR: This segment is shorter...]"
   • Word counts at the end of segments
   • Meta-commentary about what you're doing
   • Any text that isn't either the segment header or proper dialogue

Previous chunks context: {", ".join(chunk_scripts[:50]) if chunk_scripts else "This is the first chunk"}

Video Structure:
{video_structure}

Plot Outline for this segment:
{plot_outline}

Guidelines:
{script_breakdown}

Characters: {', '.join(characters) if characters else f'Use [{host_name if host_name else "NARRATOR"}] for all narration'}
Host Name: {host_name if host_name else 'NARRATOR'}

CRITICAL REMINDER: EVERY line of dialogue MUST start with a character name in brackets like [{host_name if host_name else 'NARRATOR'}]: and the main narrator should be used for most of the content unless dialogue from specific characters is required. DO NOT include ANY text that isn't dialogue or the segment header.
"""
                            # Store the cache for future use
                            if cache_key:
                                segment_prompt_cache[cache_key] = True

                        # Create the Claude conversation
                        messages = [{"role": "user", "content": user_message}]
                        
                        # If we're using a cached prompt, add the previous message reference
                        if use_cached_prompt:
                            messages[0]["content"] = f"{messages[0]['content']}\n\nContinue with the same context and guidelines as our previous messages."
                        
                        # Use Claude Sonnet 4 model and handle 'refusal' stop reason
                        response = await client.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=8000,
                            temperature=0.7,  # Lower temperature for consistency
                            system=system_message,
                            messages=messages
                        )

                        # Check for 'refusal' stop reason (Claude 4)
                        if hasattr(response, "stop_reason") and response.stop_reason == "refusal":
                            logger.error(f"Claude 4 refused to generate content for segment {idx+1}, chunk {chunk_idx+1}. Aborting this chunk.")
                            chunk_attempts += 1
                            if chunk_attempts >= max_chunk_attempts:
                                chunk_scripts.append(f"[NARRATOR]: Error generating this portion of the story due to model refusal. {words_per_chunk} words should be here.")
                            await asyncio.sleep(2)
                            continue
                        
                        # Track token usage and costs (safely)
                        try:
                            if hasattr(response, 'usage') and response.usage is not None:
                                input_tokens = getattr(response.usage, 'input_tokens', 0)
                                output_tokens = getattr(response.usage, 'output_tokens', 0)
                                
                                # Update totals
                                total_input_tokens += input_tokens
                                total_output_tokens += output_tokens
                                
                                # Calculate cost - Claude 4 pricing (update as needed)
                                input_cost = (input_tokens / 1000000) * 3
                                output_cost = (output_tokens / 1000000) * 15
                                segment_cost = input_cost + output_cost
                                total_cost += segment_cost
                                
                                # Track individual segment costs
                                segment_costs.append({
                                    "segment_name": segment['name'],
                                    "chunk": f"{chunk_idx+1}/{chunk_count}",
                                    "input_tokens": input_tokens,
                                    "output_tokens": output_tokens,
                                    "cost": segment_cost,
                                    "cached_prompt": use_cached_prompt
                                })
                                
                                # Add enhanced logging for prompt caching usage
                                if hasattr(response.usage, 'cache_read_input_tokens') and response.usage.cache_read_input_tokens > 0:
                                    cache_read = response.usage.cache_read_input_tokens
                                    logger.info(f"Prompt caching ACTIVE - Reused {cache_read:,} cached tokens for segment {idx+1}")
                                    # Calculate savings
                                    cache_savings = (cache_read / 1000000) * 3 * 0.9  # 90% cheaper for cached tokens
                                    logger.info(f"Cost savings: ${cache_savings:.4f} (90% discount on {cache_read:,} tokens)")
                        except Exception as e:
                            # Just log the error but continue with script generation
                            logger.error(f"Error tracking token usage: {str(e)}")
                        
                        chunk_script = response.content[0].text
                        
                        # Clean the script to remove any meta-commentary
                        chunk_script = clean_script(chunk_script, is_first_chunk=(chunk_idx==0), segment_header=segment_header)
                        
                        # For first chunk, ensure it has the proper header
                        if chunk_idx == 0 and not chunk_script.strip().startswith(segment_header):
                            chunk_script = f"{segment_header}\n\n{chunk_script}"
                        
                        # Validate word count - be more lenient for chunks
                        word_count = len(chunk_script.split())
                        
                        # Accept if within 20% of target or within 100 words
                        word_count_difference = words_per_chunk - word_count
                        close_enough = word_count >= words_per_chunk * 0.8 or word_count_difference <= 100
                        
                        if not close_enough:
                            chunk_attempts += 1
                        else:
                            chunk_valid = True
                            chunk_scripts.append(chunk_script)
                            
                            # Log chunk completion
                            logger.info(f"Segment {idx+1}, chunk {chunk_idx+1}/{chunk_count} completed with {len(chunk_script.split())} words")
                    
                    except Exception as e:
                        chunk_attempts += 1
                        if chunk_attempts >= max_chunk_attempts:
                            chunk_scripts.append(f"[NARRATOR]: Error generating this portion of the story. {words_per_chunk} words should be here.")
                        await asyncio.sleep(2)
            
            # Combine all chunks
            segment_script = "\n\n".join(chunk_scripts)
            
            # Make sure there aren't multiple instances of the header
            header_pattern = r'^.*?\(\d{2}:\d{2}:\d{2}\s*-\s*\d{2}:\d{2}:\d{2}.*?Duration:.*?\)'
            headers = re.findall(header_pattern, segment_script, re.MULTILINE)
            if len(headers) > 1:
                # Keep only the first header
                for header in headers[1:]:
                    segment_script = segment_script.replace(header, "", 1)
            
            # Calculate the total word count for checking
            total_words = len(segment_script.split())
            
            # If still too short after chunking (unlikely), add a note
            if total_words < min_word_count:
                segment_script += f"\n\n[NOTE TO EDITOR: This segment is shorter than required ({total_words}/{min_word_count} words). Please expand content to match the {segment['duration']} duration.]"
        
        else:
            # For normal length segments, use the existing approach
            segment_valid = False
            segment_script = ""
            attempts_for_segment = 0
            max_segment_attempts = max_retries
            
            while not segment_valid and attempts_for_segment < max_segment_attempts:
                try:
                    # Check if we're using caching and if this is not the first attempt
                    use_cached_prompt = cache_key and attempts_for_segment > 0 and cache_key in segment_prompt_cache
                    
                    if use_cached_prompt:
                        # Use a condensed prompt with Claude's prompt caching mechanism
                        user_message = f"""Generate script segment {idx + 1}/{len(segments)} for "{title}":

This is a continuation of our conversation about creating a script segment.
Use the same guidelines and requirements as before.
Segment Details:
- Segment Name: {segment['name']}
- Timestamp: {segment['timestamp']}
- Duration: {segment['duration']} (Target: {target_word_count} words, minimum: {min_word_count} words)

Remember that every line must start with a character name in brackets like [{host_name if host_name else 'NARRATOR'}]:
"""
                    else:
                        # Regular full prompt - converted to use Anthropic's prompt caching
                        # Structured content array with cache_control on static parts
                        user_message = [
                            {
                                "type": "text",
                                "text": f"""Video Structure:
{video_structure}

Plot Outline:
{plot_outline}

Guidelines:
{script_breakdown}

Characters: {', '.join(characters) if characters else 'None provided'}
Research Articles: {', '.join(research_articles) if research_articles else 'None provided'}
Host Name: {host_name if host_name else 'Not specified'}

{f'''Sponsored Content:
Segment: {sponsored_info["segment"]}
Requirements: {sponsored_info["requirements"]}

IMPORTANT: Integrate the sponsored segment naturally after the hook but before main content.
''' if sponsored_info else ''}""",
                                "cache_control": "ephemeral"  # Cache the static guidelines content
                            },
                            {
                                "type": "text",
                                "text": f"""Generate script segment {idx + 1}/{len(segments)} for "{title}":

Segment Name: {segment['name']}
Timestamp: {segment['timestamp']}
Duration: {segment['duration']} (Target Word Count: approx. {target_word_count} words)

⚠️ CRITICAL REQUIREMENT: Your script segment MUST contain AT LEAST {min_word_count} words, and ideally {target_word_count} words. 
This is a HARD REQUIREMENT - scripts that are too short will be completely rejected!

⚠️ VOICE GENERATION WARNING: Your output will be processed by a voice generation system that CANNOT handle any content except the segment header and proper dialogue lines. Any other text will cause serious errors.

IMPORTANT: Your output should adhere to the following guidelines:

1. STRICT SEGMENT ADHERENCE:
   • Only generate content for the segment specified above.
   • This segment must appear exactly ONCE and match its exact timestamp as provided.
   • Do not duplicate segments; each segment should only appear in its designated slot.
   • Follow the exact order shown in the video structure.
   PLEASE DO NOT SAY THINGS LIKE "I understand that you want me to generate the script for segment 2/5 of the video". 
   JUST GENERATE THE DIALOGUE FOR THE SEGMENT.

⚠️⚠️ CRITICAL HOST NAME REPLACEMENT REQUIREMENTS ⚠️⚠️:
- ALWAYS use [{host_name if host_name else 'NARRATOR'}] as the main narrator
- NEVER use any channel names like "sleep theories", "morpheus realm", or other channel names 
- DO NOT copy channel names from guidelines or script_breakdown
- ALWAYS replace channel-specific phrases like "Welcome to sleep theories" with "Welcome to {host_name if host_name else 'our channel'}"
- ALWAYS replace ALL channel-specific references with [{host_name if host_name else 'NARRATOR'}]
- CHECK EVERY LINE OF DIALOGUE to ensure no channel names appear
- This is ABSOLUTELY CRITICAL for proper voice generation

2. TIMING AND STRUCTURE:
   • Generate spoken dialogue and action descriptions for the segment's duration.
   • DO NOT create labeled sub-segments within this main segment. Write continuous narration.
   • Maintain a continuous flow of dialogue that covers all required content.
   • Your segment MUST fill the entire duration - scripts that are too short will be rejected.
   • It is better to write slightly LONGER than the minimum than to be too short.

3. FORMATTING:
   • Format the segment exactly as:
     Segment Name (Timestamp - Timestamp, Duration: X:XX)
   • Keep introductions very short but provide a solid hook.
   • ALWAYS enclose character names in square brackets, like [CHARACTER_NAME].
   • Every line of dialogue MUST be preceded by a character name in this format.

4. PROHIBITED CONTENT - NEVER INCLUDE:
   • "Here's the script" or "Here's the continuation" phrases
   • Editor notes like "[NOTE TO EDITOR: This segment is shorter...]"
   • Word counts at the end of segments
   • Meta-commentary about what you're doing
   • Any text that isn't either the segment header or proper dialogue with character tags

Example format:

Chapter/Segment Name (Timestamp - Timestamp, Duration: X:XX)

[HOST NAME]: Continuous dialogue that covers all the required content for this segment...
[HOST NAME]: More dialogue continuing the narrative without sub-segment breaks...

Character Formatting Examples:
       [BONELESS]: Hello, Internet! Welcome to Film Theory.
       [CAW]: But Boneless, that's madness!

       Ensure that every line of dialogue is preceded by a character name in this format.
... ALWAYS HAVE THE NAMES WITHIN BRACKETS LIKE "[HOST NAME]"

4. WORD COUNT & DURATION REQUIREMENTS:
   • CRITICAL: The spoken dialogue must contain AT LEAST {min_word_count} words.
   • It's better to write {target_word_count} words to ensure proper duration.
   • At the end of the segment output, include a brief word count.
   • Do not include extraneous content that might inflate the overall duration.
   DO NOT INCLUDE ANYTHING ELSE IN THE OUTPUT BESIDES THE SPOKEN DIALOGUE AND THE SEGMENT HEADER.

FINAL CRITICAL REMINDER: Your output MUST ONLY contain the segment header at the top and dialogue lines with character tags in brackets. Any other text will break our voice generation system. NO meta-commentary, editor notes, or anything else."""
                                # No cache_control here - this is segment-specific content
                            }
                        ]
                        
                        # Store the cache for future use
                        if cache_key:
                            segment_prompt_cache[cache_key] = True

                    # Create the Claude conversation with updated format for prompt caching
                    if isinstance(user_message, list):
                        # New prompt caching format
                        messages = [{"role": "user", "content": user_message}]
                    else:
                        # Original string format for backward compatibility
                        messages = [{"role": "user", "content": user_message}]
                    
                    # If we're using a cached prompt, add the previous message reference
                    if use_cached_prompt:
                        if isinstance(messages[0]["content"], str):
                            messages[0]["content"] = f"{messages[0]['content']}\n\nContinue with the same context and guidelines as our previous messages."
                        else:
                            # Add reference as a new content item if using structured content array
                            messages[0]["content"].append({
                                "type": "text",
                                "text": "Continue with the same context and guidelines as our previous messages."
                            })
                    
                    # Use Claude 4 model and handle refusal stop reason
                    response = await client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=8000,
                        temperature=0.7,
                        system=system_message,
                        messages=messages
                    )

                    # Check for refusal stop reason (Claude 4 models)
                    if hasattr(response, "stop_reason") and response.stop_reason == "refusal":
                        logger.error(f"Claude 4 refused to generate segment {segment['name']} (stop_reason=refusal). Aborting this segment.")
                        segment_script = f"{segment_header}\n\n[{host_name if host_name else 'NARRATOR'}]: Error: Claude 4 refused to generate content for this segment."
                        segment_valid = True
                        # End early for this segment
                        return idx, segment_script

                    # Track token usage and costs (safely)
                    try:
                        if hasattr(response, 'usage') and response.usage is not None:
                            input_tokens = getattr(response.usage, 'input_tokens', 0)
                            output_tokens = getattr(response.usage, 'output_tokens', 0)
                            
                            # Update totals
                            total_input_tokens += input_tokens
                            total_output_tokens += output_tokens
                            
                            # Calculate cost - Use Claude 4 pricing if available, fallback to 3.5 Sonnet pricing
                            # (You may want to update these values if Anthropic publishes new pricing)
                            input_cost = (input_tokens / 1000000) * 3
                            output_cost = (output_tokens / 1000000) * 15
                            segment_cost = input_cost + output_cost
                            total_cost += segment_cost
                        
                            # Track individual segment costs
                            segment_costs.append({
                                "segment_name": segment['name'],
                                "input_tokens": input_tokens,
                                "output_tokens": output_tokens,
                                "cost": segment_cost,
                                "cached_prompt": use_cached_prompt
                            })
                    except Exception as e:
                        # Just log the error but continue with script generation
                        logger.error(f"Error tracking token usage: {str(e)}")
                    
                    segment_script = response.content[0].text
                    # Clean the script to remove any meta-commentary
                    segment_script = clean_script(segment_script, is_first_chunk=True, segment_header=segment_header)
                    
                    # Ensure it has the proper header
                    if not segment_script.strip().startswith(segment_header):
                        segment_script = f"{segment_header}\n\n{segment_script}"
                    
                    # Make sure there aren't multiple instances of the header
                    header_pattern = r'^.*?\(\d{2}:\d{2}:\d{2}\s*-\s*\d{2}:\d{2}:\d{2}.*?Duration:.*?\)'
                    headers = re.findall(header_pattern, segment_script, re.MULTILINE)
                    if len(headers) > 1:
                        # Keep only the first header
                        for header in headers[1:]:
                            segment_script = segment_script.replace(header, "", 1)
                    
                    # Validate word count with very lenient thresholds
                    word_count = len(segment_script.split())
                    # Remove logger.info
                    # logger.info(f"Segment {segment['name']} generated with {word_count} words (min needed: {min_word_count})")
                    
                    # Accept all segments regardless of length - replacing the length check
                    segment_valid = True
                    
                except Exception as e:
                    attempts_for_segment += 1
                    if attempts_for_segment >= max_segment_attempts:
                        segment_script = f"{segment_header}\n\n[{host_name if host_name else 'NARRATOR'}]: Error generating content for this segment."
                        segment_valid = True
                    await asyncio.sleep(2 ** attempts_for_segment)
        
        # Do a final check to make sure the segment is properly formatted
        if segment_script:
            # 1. Ensure header format is correct
            if not segment_script.strip().startswith(segment_header):
                segment_script = f"{segment_header}\n\n{segment_script}"
                
            # 2. Remove any duplicate headers
            header_pattern = r'^.*?\(\d{2}:\d{2}:\d{2}\s*-\s*\d{2}:\d{2}:\d{2}.*?Duration:.*?\)'
            headers = re.findall(header_pattern, segment_script, re.MULTILINE)
            if len(headers) > 1:
                # Keep only the first header
                for header in headers[1:]:
                    segment_script = segment_script.replace(header, "", 1)
                
            # 3. Make sure there's no meta-commentary left
            segment_script = clean_script(segment_script, is_first_chunk=True, segment_header=segment_header)
        
        # Return the index and the segment script to maintain order
        return idx, segment_script

    # Create a semaphore to limit the number of concurrent API calls
    # This avoids rate limits and excessive resource usage
    semaphore = asyncio.Semaphore(5)  # Process up to 5 segments at a time

    async def process_segment_with_semaphore(idx, segment):
        """Process a segment with semaphore to control concurrency."""
        async with semaphore:
            return await process_segment(idx, segment)

    # Create a cache for prompt components to reduce token usage across segments
    segment_prompt_cache = {}

    # Modified process function that uses the cache
    async def process_segment_with_cache_and_semaphore(idx, segment):
        """Process a segment with semaphore and use prompt caching to reduce token usage."""
        async with semaphore:
            # Generate a cache key based on segment name
            cache_key = f"segment_{idx}"
            logger.info(f"Starting to process segment {idx+1}/{len(segments)}: '{segment['name']}'")
            result = await process_segment(idx, segment, cache_key=cache_key)
            logger.info(f"Completed segment {idx+1}/{len(segments)}: '{segment['name']}'")
            return result

    # Process all segments in parallel with controlled concurrency
    logger.info(f"Starting parallel processing of {len(segments)} segments")
    tasks = []
    for idx, segment in enumerate(segments):
        tasks.append(process_segment_with_cache_and_semaphore(idx, segment))
    
    # Wait for all segments to complete
    results = await asyncio.gather(*tasks)
    
    # Sort results by original segment index to maintain order
    results.sort(key=lambda x: x[0])
    
    # Extract just the scripts in the correct order
    script_segments = [result[1] for result in results]
    
    logger.info(f"Completed parallel processing of all {len(segments)} segments")

    # Merge all segment outputs
    full_script = "\n\n=== SEGMENT BREAK ===\n\n".join(script_segments)
    
    # Final cleanup of the entire script to make sure there are no remaining issues
    # Remove any "I understand" or similar statements
    full_script = re.sub(r'I understand[^\.]+\.\s*', '', full_script, flags=re.IGNORECASE | re.MULTILINE)
    full_script = re.sub(r'Understood\.[^\.]+\.\s*', '', full_script, flags=re.IGNORECASE | re.MULTILINE)
    full_script = re.sub(r'I will[^\.]+\.\s*', '', full_script, flags=re.IGNORECASE | re.MULTILINE)
    full_script = re.sub(r'I\'ll[^\.]+\.\s*', '', full_script, flags=re.IGNORECASE | re.MULTILINE)
    full_script = re.sub(r'Here is[^\.]+\.\s*', '', full_script, flags=re.IGNORECASE | re.MULTILINE)
    
    # Remove "Word count: X" at the end of segments
    full_script = re.sub(r'Word count:?\s*\d+\s*(\n\=\=\= SEGMENT BREAK \=\=\=)?', r'\1', full_script, flags=re.MULTILINE)
    logger.info(f"Successfully merged all segments. Final length: {len(full_script.split())} words")
    
    # Create cost summary
    cost_data = {
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cost": total_cost,
        "segment_costs": segment_costs,
        "timestamp": datetime.now().isoformat(),
        "title": title,
        "model": "claude-sonnet-4-20250514"
    }
    
    # Calculate caching statistics if available
    total_cached_tokens = 0
    cache_savings = 0.0
    segments_with_caching = 0
    
    for cost_item in segment_costs:
        if cost_item.get("cached_prompt"):
            segments_with_caching += 1
        
        # If we have cache metrics for this segment, add them up
        if cost_item.get("cache_read_input_tokens", 0) > 0:
            total_cached_tokens += cost_item["cache_read_input_tokens"]
            # Calculate savings (90% discount on cached tokens)
            cache_savings += (cost_item["cache_read_input_tokens"] / 1000000) * 3 * 0.9
    
    # Add caching metrics to cost data
    cost_data["total_cached_tokens"] = total_cached_tokens
    cost_data["cache_savings"] = cache_savings
    cost_data["segments_with_caching"] = segments_with_caching
    
    # Enhanced logging with cache information
    if total_cached_tokens > 0:
        logger.info(f"Script generation cost summary: Input tokens: {total_input_tokens:,}, Output tokens: {total_output_tokens:,}, Total cost: ${total_cost:.2f}")
        logger.info(f"Prompt caching saved ${cache_savings:.2f} by reusing {total_cached_tokens:,} tokens across {segments_with_caching} segments")
    else:
        logger.info(f"Script generation cost summary: Input tokens: {total_input_tokens:,}, Output tokens: {total_output_tokens:,}, Total cost: ${total_cost:.2f}")
    
    return full_script, cost_data


from typing import List, Dict

async def extract_segments(plot_outline: str) -> List[Dict[str, str]]:
    """
    Extracts segments from the plot outline using the markers "Video Structure:" 
    and "Detailed Segment Breakdown:".
    Expected format for each line in the Video Structure section:
      "1. The Trolley Problem (00:00 - 13:15, Duration: 13:15)"
      
    This updated version supports timestamps in the following formats:
      - mm:ss (e.g., "15:45")
      - hh:mm:ss (e.g., "1:00:00" or "10:00:00")
    and allows for videos longer than 10 hours.
    """
    try:
        structure_block = plot_outline.split('Video Structure:')[1].split('Detailed Segment Breakdown:')[0].strip()
    except IndexError:
        raise ValueError("Plot outline formatting error: Cannot locate 'Video Structure:' or 'Detailed Segment Breakdown:' sections.")

    segments = []
    for line in structure_block.splitlines():
        line = line.strip()
        if not line:
            continue
        # Updated regex:
        # - \d+ allows one or more digits for hours (or minutes if no hour part)
        # - :\d{2} matches minutes, and an optional :\d{2} for seconds.
        match = re.search(
            r"^\d+\.\s+(.*?)\s+\(((?:\d+:\d{2}(?::\d{2})?)\s*-\s*(?:\d+:\d{2}(?::\d{2})?)),\s*Duration:\s*(.*?)\)$",
            line
        )
        if match:
            segments.append({
                "name": match.group(1).strip(),
                "timestamp": match.group(2).strip(),
                "duration": match.group(3).strip(),
            })
    if not segments:
        raise ValueError("No segments found in the 'Video Structure' section.")
    return segments


async def merge_script_chunks(client, system_message, chunks, video_length):
    logger.info(f"Merging {len(chunks)} chunks with smart chunking")
    total_content = "\n".join(chunks)
    if len(total_content.split()) < 2000:
        try:
            merged = await merge_single_chunk(client, system_message, chunks, video_length)
            logger.debug("Direct merge successful in merge_script_chunks.")
            return merged
        except Exception as e:
            logger.error(f"Direct merge failed: {str(e)}")
            return total_content

    final_chunks = []
    chunk_size = 3
    for i in range(0, len(chunks), chunk_size):
        batch = chunks[i:i + chunk_size]
        try:
            merged = await merge_single_chunk(
                client, 
                system_message,
                batch,
                video_length,
                f"Part {i//chunk_size + 1}"
            )
            final_chunks.append(merged)
            logger.info(f"Chunk merge successful for batch starting at index {i}")
        except Exception as e:
            logger.error(f"Chunk merge failed for batch starting at index {i}, using original batch: {str(e)}")
            final_chunks.extend(batch)

    final_merged = "\n\n" + "="*40 + " SEGMENT BREAK " + "="*40 + "\n\n".join(final_chunks)
    logger.debug(f"Final merged script preview: {final_merged[:300]}")
    return final_merged

async def merge_single_chunk(client, system_message, chunks, video_length, part_label=""):
    merge_message = f"""Combine these script segments into one cohesive section.
    Maintain ALL original content and formatting.
    
    Rules:
    1. Keep ALL dialogue and scene descriptions
    2. Maintain ALL [CLIP NEEDED] sections
    3. Preserve ALL character names in [BRACKETS]
    4. Keep ALL timing information
    5. Maintain exact segment structure
    
    Duration: {video_length} minutes
    {part_label}
    
    DO NOT summarize or truncate. Keep ALL original content.
    
    {'-' * 40}
    """ + f"\n{'-' * 40}\n".join(chunks)

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,  # Stay within Sonnet's limits
        temperature=0.1,
        system=system_message,
        messages=[{"role": "user", "content": merge_message}]
    )
    
    merged = response.content[0].text
    
    # Validate merged content
    if len(merged.split()) < len("\n".join(chunks).split()) * 0.9:
        logger.warning("Merged content appears truncated, using original chunks")
        return "\n\n".join(chunks)
        
    return merged

async def determine_script_need(series: Dict[str, Any], theme: Dict[str, Any], script_breakdown: str) -> bool:
    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    
    prompt = f"""Analyze the following series, theme, and script breakdown to determine if a full script is needed:

Series: {series['name']}
Theme: {theme['name']}
Script Breakdown:
{script_breakdown}

Consider these content types that typically require full scripts:
1. Educational content (tutorials, how-tos, explainers)
2. Narrative videos (sketches, web series, storytelling)
3. Video essays and documentary-style content
4. Scripted commentary and analysis
5. Complex topic explanations
6. Character-driven content
7. Highly structured informational content
8. Step-by-step tutorials
9. Historical or research-based content
10. Conspiracy theory or investigation videos

Content types that usually don't need full scripts:
1. Vlogs and daily life content
2. Reaction videos
3. Gaming gameplay (unless heavily narrative)
4. Unboxing videos
5. Live streams
6. Simple product reviews
7. Casual commentary
8. Impromptu style videos

Based on this information, determine if a full script is needed. Respond with either 'True' if a full script is needed, or 'False' if only a plot outline is sufficient."""

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            temperature=0,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        result = response.content[0].text.strip().lower()
        return result == 'true'
    except Exception as e:
        logger.error(f"Error in determine_script_need: {str(e)}")
        return True  # Default to needing a full script if there's an error

from google.cloud import vision
import io
import os
from config import vision_client


from google.cloud import vision
import io
import os
from config import vision_client

async def optimize_script_guidelines(
    series_name: str,
    theme_name: str,
    video_data: List[Dict],
    existing_guidelines: Dict
) -> Dict:
    """Optimize script guidelines based on retention data and script analysis"""
    
    system_message = """You are an AI expert in YouTube audience retention optimization while maintaining content identity.
    Your task is to analyze video performance, scripts, and suggest strategic improvements that preserve the core series structure.
    
    ANALYSIS FRAMEWORK:
    1. Script Structure Analysis
        - High-retention script patterns
        - Successful hook structures
        - Engaging dialogue patterns
        - Effective transitions
        - Pacing variations
    
    2. Content Flow Analysis
        - Script-to-retention correlation
        - Drop-off point analysis
        - Peak engagement moments
        - Recovery patterns
        - Time-based engagement triggers
    
    3. Series Identity Elements
        - Core catchphrases
        - Character dynamics
        - Recurring segments
        - Signature transitions
        - Brand elements
        
    4. Optimization Targets
        - Hook (0-30s): 85%+ retention
        - Core Content: 65%+ baseline
        - Key Points: 70%+ retention spikes
        - Overall: 50%+ average retention"""

    # Enhanced video data analysis with script correlation
    analysis_data = []
    for video in video_data:
        retention_points = video['retention_data']
        full_script = video.get('script', '')
        plot_outline = video.get('plot_outline', '')
        
        # Map retention to script segments
        script_segments = full_script.split('\n\n') if full_script else []
        segment_retention = []
        
        if retention_points and script_segments:
            points_per_segment = len(retention_points) / len(script_segments)
            for i, segment in enumerate(script_segments):
                start_point = int(i * points_per_segment)
                end_point = int((i + 1) * points_per_segment)
                avg_retention = sum(retention_points[start_point:end_point]) / (end_point - start_point)
                
                # Analyze segment characteristics
                segment_retention.append({
                    'segment': segment,
                    'retention': avg_retention,
                    'position': i / len(script_segments),  # Relative position in video
                    'word_count': len(segment.split()),
                    'is_dialogue': '"' in segment or "'" in segment,
                    'has_action': any(word in segment.lower() for word in ['walk', 'run', 'jump', 'move', 'turn', 'look'])
                })

        analysis_data.append({
            'title': video['title'],
            'retention_graph': retention_points,
            'segment_analysis': segment_retention,
            'plot_outline': plot_outline,
            'high_retention_segments': [s for s in segment_retention if s['retention'] > 65],
            'script_structure': {
                'total_segments': len(script_segments),
                'avg_segment_length': sum(len(s.split()) for s in script_segments) / len(script_segments) if script_segments else 0,
                'dialogue_ratio': sum(1 for s in segment_retention if s['is_dialogue']) / len(segment_retention) if segment_retention else 0,
                'action_ratio': sum(1 for s in segment_retention if s['has_action']) / len(segment_retention) if segment_retention else 0
            }
        })

    user_message = f"""Analyze these {len(video_data)} videos in the {series_name} series with {theme_name} theme:

    CURRENT GUIDELINES:
    {json.dumps(existing_guidelines, indent=2)}

    PERFORMANCE ANALYSIS:
    {json.dumps(analysis_data, indent=2)}

    OPTIMIZATION REQUIREMENTS:
    1. Maintain core series structure and identity
    2. Identify successful script patterns from high-retention segments
    3. Optimize segment lengths and pacing based on retention data
    4. Enhance hook structure while preserving series style
    5. Improve dialogue-to-action ratios based on engagement
    6. Optimize transition points between segments
    7. Maintain successful recurring elements
    8. Suggest specific timing for key engagement points

    Provide optimized guidelines that maintain series authenticity while improving retention.
    Format response as a JSON object matching the existing guidelines structure."""

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        temperature=0.7,
        system=system_message,
        messages=[{"role": "user", "content": user_message}]
    )

    try:
        optimized_guidelines = json.loads(response.content[0].text)
        
        # Validate optimization maintains core elements
        core_elements = set(existing_guidelines.get('core_elements', []))
        optimized_elements = set(optimized_guidelines.get('core_elements', []))
        
        if not core_elements.issubset(optimized_elements):
            logger.warning("Optimization removed core elements - reverting to preserve series identity")
            optimized_guidelines['core_elements'] = list(core_elements | optimized_elements)
        
        return optimized_guidelines
    except json.JSONDecodeError:
        logger.error("Failed to parse optimization response")
        return existing_guidelines

async def generate_thumbnail_concepts(guidelines: str, video_title: str, reference_urls: List[str], num_concepts: int = 3, custom_niche: str = None) -> List[str]:
    anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    
    try:
        # Get image contents for reference
        image_contents = []
        successful_downloads = 0
        for url in reference_urls:
            url_to_process = url['url'] if isinstance(url, dict) else url
            try:
                img_data, media_type = await get_image_data(url_to_process)
                if img_data:  # Only add if we got actual data
                    image_contents.append({
                        "type": "image", 
                        "source": {
                            "type": "base64", 
                            "media_type": media_type, 
                            "data": img_data
                        }
                    })
                    successful_downloads += 1
            except Exception as e:
                logger.error(f"Error processing image from {url}: {str(e)}")
            
            # Break early if we have enough successful images
            if successful_downloads >= 5:  # 5 is usually enough for reference
                break

        # Only log a warning if we have no valid images, but continue anyway
        if not image_contents:
            logger.warning("No valid reference images could be downloaded. Will generate concepts without image references.")
        
        # Add custom niche information to prompt if provided
        niche_info = ""
        if custom_niche:
            niche_info = f"\n\nIMPORTANT: This video is about '{custom_niche}'. Use this specific niche in your design and replace any generic series title text with '{custom_niche} FOR SLEEP' or similar appropriate branding based on this niche. The niche should be prominently featured in the thumbnail design."
        
        prompt = f"""You are a thumbnail design specialist with expert knowledge of YouTube thumbnail psychology. First, carefully analyze these sections of the guidelines to understand the series style:
1. TRAINING_GUIDANCE section - Focus on:
  - "critical_elements.must_maintain" for required elements that CANNOT change:
    * These elements must stay consistent in every thumbnail
    * Pay special attention to maintaining these core elements
  - "critical_elements.can_vary" for flexible elements that can be adapted
  - "concept_generation.style_markers" for unique style identifiers
  - "concept_generation.key_descriptors" for essential elements
  - "concept_generation.prompt_template" for the exact template pattern to follow, but be creative and make it interesting and engaging.

2. BASE_IMAGE_REQUIREMENTS section - Study:
   - Composition rules
   - Subject placement
   - Lighting requirements

3. SERIES_PATTERN_ANALYSIS section - Note:
   - Visual constants
   - Series identifiers
   - Title integration patterns

After analyzing these sections in the guidelines below, generate {num_concepts} thumbnail concepts for: "{video_title}"

Complete Guidelines:
{guidelines}

Requirements for your response:
1. Output ONLY numbered concepts (1., 2., 3., etc.)
2. Each concept should be one detailed paragraph
3. Include all mandatory series elements
4. Match the exact style from reference thumbnails
5. Be specific about layout and composition
6. NO explanatory text, ONLY the numbered concepts
7. Follow the prompt_template pattern if provided in the guidelines.
8. build the concept in the same way as the reference thumbnails.
9. make creative concepts that are interesting and engaging.
10. make sure the concepts are not too similar to each other.
11. never put the title of the video in the image or thumbnail concept. try to keep the words in the image down to 3 words maximum.
12. make sure that the arrangement of the elements in the image are not too crowded and clearly visible and easy to understand.
13. ‼️ CRITICAL REQUIREMENT: Text must be MASSIVE and DOMINANT, taking up 45-55% of the thumbnail's width or height. For titles like "GREEK SLEEP TALES", the text should be EXTREMELY LARGE with perfect visibility even at tiny thumbnail sizes. Text must be the most visually dominant element along with the main character/subject.
14. ⚠️ EXACT REFERENCE MATCHING: Study the reference thumbnails carefully and match the exact text size proportions - if text takes up 50% of the width in references, specify that exact same proportion.
15. Text must have strong contrast with the background using appropriate shadows, outlines, or backing elements to ensure perfect readability.{niche_info}

YOUTUBE CLICK PSYCHOLOGY - Advanced Tactics:

1. THE 3-SECOND RULE:
   - Design for initial attention capture within 3 seconds on mobile devices
   - Create a clear focal hierarchy that guides the eye to critical elements INSTANTLY
   - Position the most compelling element in the center-right "hotspot" zone
   - Use visual tension to create immediate emotional response
   - Apply the "Attention Gradient" principle: strongest element → moderate element → subtle element
   - Create "scroll-stopping power" by placing high-contrast elements at natural thumb-stop positions

2. ATTENTION PATTERN MAPPING:
   - Position elements to match F-pattern and Z-pattern eye movement
   - Place the main subject in the top-right golden ratio point (mobile-optimized)
   - Create directional cues that lead to the play button
   - Use depth to create a layered visual hierarchy
   - Implement "visual anchors" at 1.6-second scan points
   - Apply the 70/30 rule for negative space distribution to draw eye attention

3. COLOR PSYCHOLOGY TRIGGERS:
   - Use color contrast ratios of 4.5:1 minimum for maximum neural activation
   - Employ complementary colors to create visual tension
   - Use red, orange, or yellow as accent colors (stimulate urgency)
   - Create targeted color dissonance to disrupt scroll patterns
   - Apply the "Color Isolation Theory" to make one element pop dramatically
   - Use red/blue contrasts for 31% higher click-through rates

4. EMOTIONAL TRIGGER FRAMEWORK:
   - Use the FOMO principle (Fear Of Missing Out) through composition
   - Create visual question marks that trigger curiosity completion instinct
   - Employ the "information gap theory" using juxtaposed elements
   - Create visual puzzles that can only be solved by watching
   - Use emotional faces that trigger mirror neuron response
   - Position faces looking TOWARD important elements (directional gaze)
   - Implement "Emotional Contrast" elements that create 2.7x higher engagement
   - Use aspirational imagery that triggers self-identification and desire
   - Apply "Visual Cliffhanger" techniques that create unresolved tension

5. PATTERN INTERRUPTION SCIENCE:
   - Include unexpected juxtapositions that force attention
   - Create subtle visual tensions that demand resolution
   - Employ optical illusions that force re-examination
   - Use "visual jolts" - elements that break the expected pattern
   - Implement the "2-second Cognitive Reset" principle where pattern breaks reset attention
   - Create perceptual contrast that stands out from the normal feed aesthetics

6. MOBILE OPTIMIZATION:
   - Design for phone screens FIRST - elements must be clear at 120x68px
   - Create visual priority for the top 60% of the thumbnail (above fold)
   - Use touch target zones that align with thumb scrolling patterns
   - Design for ultra-high contrast visibility in outdoor settings
   - Position key elements in the "thumb-stop zone" (middle-right of composition)
   - Create visual velocity breaks that interrupt rapid scrolling

7. THUMBNAIL-TITLE SYNERGY:
   - Create visual elements that connect with the title keywords
   - Build tension between thumbnail and title (answer in video)
   - Use the Zeigarnik effect - unfinished visual stories that need completion
   - Create a sequential narrative between thumbnail and title
   - Implement curiosity bridges that force title-thumbnail comparison
   - Use semantic gaps between title and visual elements to create intrigue

8. PRIMITIVE BRAIN ACTIVATION:
   - Use primal triggers that activate the limbic system:
     * Threat/danger elements that trigger safety concerns
     * Food-like colors that stimulate appetite response
     * Reward cues that trigger dopamine circuits
     * Status/social proof signals that activate social comparison
   - Position elements to trigger depth perception (looming effect)
   - Create perceived motion that activates the dorsal visual stream
   - Apply neurological contrast mapping for maximum reptilian brain activation
   - Use triangular compositions for subliminal stability and trust
   - Incorporate forced perspective elements that create immersion

9. ALGORITHM OPTIMIZATION CUES:
   - Use vibrant, high-saturation focal points (+18% CTR according to research)
   - Create clear object separation with defined edges for algorithm recognition
   - Use 40% higher brightness in key focus areas for recommendation engine advantage
   - Position faces within the AI-detection hotspots (upper right quadrant)
   - Implement visual patterns that match trending click metrics
   - Create "algorithmic affinity" using colors and compositions proven to boost recommendation

10. VISUAL COMPETITIVE ADVANTAGE:
    - Design elements that disrupt the visual flow of competing thumbnails
    - Use contrasting styles that stand out within your category
    - Apply the uniqueness principle - one element must be unlike any competitor
    - Implement visual velocity cues that suggest motion/action (+23% CTR)
    - Simplify the thumbnail to reduce cognitive load and increase decision clarity
    - Create "scroll-stream pattern breakers" that force attention

PSYCHOLOGICAL TRIGGERS - Incorporate these elements to create highly clickable thumbnails:
1. CURIOSITY GAP: Create a visual "question" that can only be answered by watching
   - Use unexpected juxtapositions
   - Show partial revelations that prompt curiosity
   - Create visual suspense that needs resolution
   - Apply the "revealed secret" technique - showing evidence of insider information
   - Use incompletion elements that create a need for cognitive closure
   - Create mystery anchors that suggest a story beyond the thumbnail

2. EMOTIONAL TRIGGERS:
   - Use strong emotional expressions on faces where appropriate
   - Incorporate colors proven to trigger emotional responses
   - Create visual metaphors for powerful emotions
   - Use lighting to create mood that sparks emotional interest
   - Apply emotional transference elements that make viewers feel specific emotions
   - Use contrast states - show before/after emotional states to create intrigue
   - Implement emotional mirroring to reflect viewer emotions

3. PATTERN INTERRUPTION:
   - Include one unexpected element that breaks visual patterns
   - Create slight visual tensions that demand resolution
   - Use optical illusions or unexpected perspectives
   - Apply cognitive reset triggers that force mental reengagement
   - Use visual jolts to create immediate pattern breaks
   - Implement expectation violations that force attention through contrast

4. URGENCY & SCARCITY:
   - Visual elements that suggest limited time or opportunity
   - Create compositions suggesting action or movement
   - Incorporate subtle visual cues of exclusivity
   - Use time perception triggers that create feelings of urgency
   - Apply visual countdown elements that suggest limited availability
   - Create constraint markers that suggest barriers to access

5. CLICKBAIT PSYCHOLOGY (ETHICAL):
   - Use subtle exaggeration without misleading
   - Create optical illusions that draw eye attention
   - Incorporate visual hyperbole for effect
   - Use visual metaphors that trigger primal responses
   - Create compositions with slight edge or provocative elements without being inappropriate
   - Apply reward prediction elements that suggest value in clicking
   - Use revelation promises - subtle cues promising new information
   - Implement transformation markers - elements that suggest positive change

IMPORTANT - THREE ELEMENT RULE:
Unless the guidelines EXPLICITLY require more complexity, follow the three element rule:
- Limit each thumbnail concept to a maximum of 3 main visual elements
- Focus on SIMPLICITY and CLEAN design above all else
- Each element should be clear, bold, and immediately recognizable
- Avoid cluttered compositions - when in doubt, use fewer elements
- Use negative space effectively to highlight the main elements
- Apply 70/20/10 focus ratio - 70% attention to primary element, 20% to secondary, 10% to tertiary

IDEAL THUMBNAIL STRUCTURE:
1. ONE dominant visual/character (50-60% recognition factor)
2. ONE clear text element (1-3 words maximum, taking up 45-55% of width/height)
3. ONE supporting background/context element
4. Use the rule of visual weight distribution: 50% main character / 45% text / 5% supporting
5. Place key elements at 1.8-second scan points for maximum attention capture

TEXT SIZE GUIDANCE:
- 🔴 Title text MUST be MASSIVELY LARGE, taking up 45-55% of the available width or height
- 🔴 Match EXACTLY the text size from reference thumbnails - maintain identical proportions
- 🔴 Text must be THE dominant visual element alongside the main character
- Text must be easily readable from 10 feet away on a phone screen
- Use bold, heavy fonts with strong weights and clean edges
- Make sure text has perfect contrast - white text with dark stroke/shadow
- Text should have a contrast ratio of at least 7:1 against its background
- Make main words 300% larger than any secondary text
- Use background isolation techniques to make text pop with 92% contrast minimum

CLICKABILITY BOOSTERS:
- Use high contrast to create a "pop" effect
- Position key elements on eye-tracking hotspots (upper-right, center, faces)
- Create subtle visual cues that direct attention to the most important element
- Incorporate "pattern interrupt" elements that force attention
- Use visual tricks to create impression of movement or action
- Create a "visual cliffhanger" that suggests resolution in the video
- Arrange elements in dopamine-triggering patterns
- Use psychological completion cues that suggest answers in the video
- Place high-impact elements at the 1/3 points in the composition

REFERENCE ANALYSIS:
Study these reference thumbnails carefully to match:
- Exact composition style
- Visual treatment
- Emotional impact
- Positioning and layout
- Color schemes and effects
- 🔴 Text placement and EXACT SIZING - match the precise dimensions from references
- Subject framing and scale
- 🔴 TEXT SIZE AND DOMINANCE - copy the exact proportions from references
- Key visual elements that establish brand recognition
- Foundation elements with creative variation

FORMAT REQUIREMENTS:
- Single detailed paragraph
- Start with layout description
- Include ALL mandatory elements
- End with style specifications
- Maintain exact series structure
- PRIORITIZE SIMPLICITY
- EMPHASIZE EXTREMELY LARGE TEXT (45-55% of width/height)
- Ensure elements work as a single unified design
- Arrange elements in attention priority order

STRICT RULES:
- Follow layout grid precisely
- Include every visual constant
- Maintain series-specific styling
- Keep consistent structure across concepts
- Use exact positioning guidelines
- TEXT MUST BE ENORMOUSLY LARGE AND DOMINANT (45-55% of width/height)
- Maintain core elements for channel identity
- Optimize for algorithm preference systems

DO NOT:
- Vary from established layout
- Skip any required elements
- Add technical specifications
- Include trigger words
- Add explanatory text
- OVERCROWD the thumbnail with too many elements
- Use small or medium-sized text - TEXT MUST BE MASSIVELY LARGE
- Create unclear compositions with competing elements
- Use elements that divide focus rather than guide it

CONCEPT FORMAT:
1. Start each concept with a number and period (1., 2., 3.)
2. Write one detailed paragraph per concept
3. Follow exact base template structure
4. Include all mandatory style elements
5. Match reference thumbnail style precisely
6. EMPHASIZE SIMPLICITY AND CLEAN DESIGN
7. Differentiate from competitors while maintaining series consistency
8. Optimize every element placement for maximum click psychology

QUALITY STANDARDS:
1. Detail Level:
   - Minimum 3 specific technical details per concept
   - Clear description of visual effects
   - Precise positioning and framing
   - Specific emotional/dramatic elements
   - Visual impact triggers that create immediate attention
   - Memory anchors that create lasting recall of thumbnail
   - Elements that reduce hesitation to click

Study the reference thumbnails provided to ensure perfect style matching.
"""

        response = await anthropic_client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=8000,
            temperature=1,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    *image_contents
                ]
            }]
        )
        
        # Split response into separate concepts and clean them
        concepts = [
            concept.strip()
            for concept in response.content[0].text.split('\n')
            if concept.strip() and not concept.startswith(('•', '-', '#', '*'))
        ][:num_concepts]
        
        return concepts

    except Exception as e:
        logger.error(f"Error generating thumbnail concepts: {str(e)}")
        return []

from anthropic import AsyncAnthropic
import logging

logger = logging.getLogger(__name__)

import base64
import httpx
from PIL import Image
from io import BytesIO
from anthropic import AsyncAnthropic
import logging

logger = logging.getLogger(__name__)

async def get_image_data(url: str) -> tuple[str, str]:
    """
    Download, process, and encode image data from URL.
    Returns tuple of (base64_encoded_data, media_type)
    """
    try:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=30) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to download image from {url}, status code: {response.status}")
                        return "", "image/jpeg"  # Return empty data instead of raising exception
                    
                    data = await response.read()
                    if not data:
                        logger.warning(f"Empty data received from {url}")
                        return "", "image/jpeg"
                    
                    try:
                        img = Image.open(BytesIO(data))
                        format = img.format
                        if format is None:
                            format = "JPEG"  # Default to JPEG if format is None
                        format = format.lower()
                        
                        # Resize if needed (for AI model compatibility)
                        if img.width > 1568 or img.height > 1568:
                            img.thumbnail((1568, 1568))
                        
                        # Convert to RGB if it's RGBA to avoid issues
                        if img.mode == 'RGBA':
                            img = img.convert('RGB')
                        
                        buffered = BytesIO()
                        img.save(buffered, format=format.upper())
                        img_str = base64.b64encode(buffered.getvalue()).decode()
                        
                        return img_str, f"image/{format}"
                    except Exception as img_error:
                        logger.warning(f"Error processing image data from {url}: {str(img_error)}")
                        return "", "image/jpeg"
            except (aiohttp.ClientError, TimeoutError) as e:
                logger.warning(f"Error downloading image from {url}: {str(e)}")
                return "", "image/jpeg"
    except Exception as e:
        logger.error(f"Error in get_image_data: {str(e)}")
        return "", "image/jpeg"  # Return empty data instead of raising exception

async def analyze_thumbnails_with_ai(thumbnail_urls: List[str], series_name: str, theme_name: str) -> str:
    try:
        image_contents = []
        for url in thumbnail_urls:
            # Fix: Handle dictionary input
            url_to_process = url['url'] if isinstance(url, dict) else url
            try:
                img_data, media_type = await get_image_data(url_to_process)
                image_contents.append({
                    "type": "image", 
                    "source": {
                        "type": "base64", 
                        "media_type": media_type, 
                        "data": img_data
                    }
                })
            except Exception as e:
                logger.error(f"Error processing image from {url}: {str(e)}")
                
        if not image_contents:
            raise Exception("Failed to process any images")
        
        prompt = f"""You are an expert in graphic design analysis and template creation.
    
ANALYSIS PROCESS:
1. First, analyze each thumbnail individually:
{chr(10).join([f'THUMBNAIL {i+1}:' for i, _ in enumerate(thumbnail_urls)])}

For each thumbnail, document:
- Composition structure
- Text placement and styling
- Visual hierarchy
- Color schemes
- Special effects
- Subject positioning
- Background treatment
- Unique elements

2. After analyzing ALL thumbnails individually, identify:
- Common patterns across thumbnails
- Consistent styling elements
- Recurring composition rules
- Series-specific markers
- Theme-specific variations

3. Only after completing both steps above, generate the full JSON structure.

VALIDATION CHECKLIST:
✓ Have you analyzed each thumbnail individually?
✓ Have you identified patterns across ALL thumbnails?
✓ Can you confidently describe the series style?
✓ Have you found consistent technical markers?
✓ Are you certain about the style classification?

Only proceed to JSON generation after checking ALL items above.

Analyze these YouTube thumbnails for series '{series_name}' and theme '{theme_name}'.
YOU MUST OUTPUT A COMPLETE JSON STRUCTURE WITH ALL OF THE FOLLOWING SECTIONS: NO ADDITIONAL TEXT IN YOUR OUTPUT..

1. LAYOUT_STRUCTURE:
   - "canvas": MUST specify dimensions and DPI
   - "grid_system": MUST define ALL content zones as:
     {{
         "zone_name": {{
             "area": [x1, y1, x2, y2],  // Exact pixel coordinates
             "description": "Detailed purpose"
         }}
     }}

2. TEXT_SPECIFICATIONS:
   For each text element:
   {{
       "text_name": {{
           "font": "exact font name",
           "size": int or {{size rules}},
           "color": "#hex_code",
           "effects": [
               {{
                   "type": "effect_name",
                   "parameters": {{exact settings}}
               }}
           ],
           "dynamic_rules": {{
               "pattern": "extraction pattern",
               "formats": [
                   {{
                       "condition": "when to apply",
                       "format": "format string",
                       "example": "input -> output"
                   }}
               ]
           }}
       }}
   }}

3. OVERLAY_ELEMENTS:
   For each overlay:
   {{
       "element_name": {{
           "type": "element type",
           "size": {{dimensions}},
           "position": [x, y] or "rule",
           "effects": [{{effect settings}}],
           "conditions": {{
               "show_when": "condition",
               "position": "positioning logic"
           }}
       }}
   }}

4. BASE_IMAGE_REQUIREMENTS:
   {{
       "composition": {{
           "element_name": {{
               "position": "exact position or rule",
               "size": "exact size or percentage",
               "clear_space": "required clear areas",
               "requirements": {{specific details}}
           }}
       }},
       "lighting": {{
           "style": "lighting description",
           "requirements": "specific needs"
       }}
   }}

5. DYNAMIC_RULES:
   {{
       "category_name": {{
           "extract_patterns": [
               "regex or rules"
           ],
           "conversion_rules": {{rule details}},
           "positioning_rules": {{position logic}}
       }}
   }}

6. SERIES_PATTERN_ANALYSIS: {{
    "title_integration": {{
        "placement_zones": [[x1, y1, x2, y2]],
        "text_treatment": {{
            "font": "font_name",
            "size_range": [min, max],
            "color_scheme": ["#hex1", "#hex2"],
            "emphasis_words": ["list", "of", "emphasized", "words"]
        }},
        "topic_visualization": {{
            "subject_placement": "rule for placing topic-specific elements",
            "scaling_rules": "how elements scale with different topics",
            "integration_method": "how topic gets represented visually"
        }}
    }},
    "series_identifiers": {{
        "visual_constants": ["list of elements that stay consistent"],
        "variable_elements": ["elements that change with topic"],
        "branding_elements": ["series-specific visual elements"]
    }}
}}

7. THUMBNAIL_PROGRESSION_RULES: {{
    "evolution_patterns": {{
        "stages": [
            {{
                "identifier": "stage name",
                "visual_characteristics": ["list of traits"],
                "transformation_rules": "how elements transform"
            }}
        ],
        "transition_effects": ["list of effects between stages"]
    }},
    "scaling_system": {{
        "size_progression": "how elements scale",
        "intensity_rules": "how effects intensify",
        "complexity_increase": "how detail levels progress"
    }}
}}

8. TRAINING_GUIDANCE: {{
    "critical_elements": {{
        "must_maintain": ["list of elements that must stay consistent"],
        "can_vary": ["elements allowed to change"],
        "style_anchors": ["key style elements to preserve"]
    }},
    "caption_structure": {{
        "format": "template for training captions",
        "variables": ["list of dynamic elements"],
        "example": "example caption with variable"
    }},
    "concept_generation": {{
        "prompt_template": "base prompt structure",
        "key_descriptors": ["essential descriptive elements"],
        "style_markers": ["unique style identifiers"]
    }}
}}

9. STYLE_CLASSIFICATION: {{
    "primary_category": {{
        "main_type": "category_name",
        "sub_type": "specific_variant",
        "guidance_value": 0.0
    }},
    "technical_markers": {{
        "recording_device": "device_type", 
        "processing_level": "processing_amount",
        "quality_indicators": ["list", "of", "indicators"]
    }},
    "artistic_properties": {{
        "medium_type": "medium_name",
        "technique_markers": ["specific", "technique", "indicators"],
        "style_period": "historical_modern_etc"
    }},
    "authenticity_metrics": {{
        "raw_characteristics": ["unprocessed", "markers"],
        "stylization_level": "none_to_heavy",
        "genre_authenticity": "style_specific_traits"
    }}
}}


SECTION FILLING INSTRUCTIONS: MAKE SURE THAT YOU PROVIDE YOUR RESPONSES IN FULL IN THE JSON.. EVERYTIME NO ADDTIONAL WORDS OR TEXT.
CRITICAL: Identify the exact style category of these thumbnails. This will determine optimal generation parameters.

STYLE CATEGORIES:
1. Real-World Content:
   - "realistic_video": Smartphone/camera video screenshots (guidance: 3.0)
   - "realistic_photo": Professional photography (guidance: 3.0)
   - "realistic_candid": Spontaneous real-world captures (guidance: 3.0)

2. Gaming Content:
   - "game_screenshot": Direct game captures (guidance: 3.5)
   - "game_fortnite": Fortnite-style rendering (guidance: 4.0)
   - "game_minecraft": Minecraft-style graphics (guidance: 4.5)
   - "game_roblox": Roblox-style rendering (guidance: 4.0)
   - "game_animated": Animated game cutscenes (guidance: 4.5)

3. Animated Content:
   - "anime": Anime/manga style (guidance: 5.0)
   - "cartoon_western": Western animation style (guidance: 5.0)
   - "cartoon_3d": 3D animation style (guidance: 4.5)
   - "cartoon_chibi": Chibi/cute style (guidance: 5.0)

4. Digital Art:
   - "illustration_digital": Digital artwork (guidance: 4.5)
   - "illustration_comic": Comic book style (guidance: 4.5)
   - "illustration_concept": Concept art style (guidance: 4.0)

5. Mixed/Hybrid:
   - "mixed_game_real": Game/reality hybrid (guidance: 3.8)
   - "mixed_anime_real": Anime/reality hybrid (guidance: 4.2)
   - "mixed_cartoon_real": Cartoon/reality hybrid (guidance: 4.0)

Include the exact style category in the guidelines under:
  "GENERATION_PARAMETERS": 
    "style_type": "[category from above]",
    "guidance_scale": corresponding value,
    "style_specific_requirements":
      "medium": "[identified medium]",
      "rendering_style": "[specific style details]"
 

Analyze the thumbnails carefully to match the EXACT style category for optimal generation parameters.


1. LAYOUT_STRUCTURE:
- Measure exact pixel coordinates for ALL content zones
- Include padding and safe zones
- Define grid system with mathematical precision
- Document responsive scaling rules

2. TEXT_SPECIFICATIONS:
- List ALL text elements separately
- Include exact font names and fallbacks
- Define size ranges for variable text
- Document ALL text effects with exact parameters

3. OVERLAY_ELEMENTS:
- Define exact positioning rules for each element
- Specify all effect parameters numerically
- Document conditional display logic
- Include z-index and layering rules

4. BASE_IMAGE_REQUIREMENTS:
- Provide exact measurements for all elements
- Define specific lighting parameters
- Document composition ratios mathematically
- Specify clear space requirements in pixels

5. DYNAMIC_RULES:
- Create precise extraction patterns
- Define exact conversion formulas
- Document positioning algorithms
- Include all edge cases and exceptions

6. SERIES_PATTERN_ANALYSIS:
- Identify repeating elements across series
- Document how video topics get visualized
- Map title integration patterns
- List consistent branding elements

7. THUMBNAIL_PROGRESSION_RULES:
- Document ALL stage transitions
- Define exact scaling ratios
- List transformation effects
- Specify intensity progression

8. TRAINING_GUIDANCE:
- List elements critical for style preservation:
  - Visual Medium Characteristics:
    - Capture method and quality markers
    - Medium-specific artifacts and distortions
    - Characteristic lighting patterns
  - Technical Style Elements:
    - Camera angles and perspectives
    - Distance and framing patterns
    - Motion and stability traits
    - Post-processing effects
  - Authenticity Markers:
    - Natural vs staged qualities
    - Environmental authenticity
    - Lighting and shadow patterns
    - Characteristic imperfections
  - Medium-Specific Details:
    - Compression artifacts
    - Lens characteristics 
    - Rendering qualities
    - Style-specific markers
  - Environmental Context:
    - Setting consistency
    - Lighting patterns
    - Background treatment
    - Space utilization
- Create detailed caption templates with:
  - Medium identification
  - Technical specifications
  - Style markers
  - Environmental context
  - Authenticity elements
- Define concept generation rules:
  - Match medium characteristics
  - Preserve technical style
  - Maintain authenticity markers
  - Include environment context
- Specify style preservation requirements:
  - Document all medium traits
  - Maintain technical patterns
  - Keep authenticity elements
  - Preserve environmental style

CRITICAL REQUIREMENTS:
1. ALL measurements must be in exact pixels
2. ALL colors must be hex codes
3. ALL positions must use [x1, y1, x2, y2] format
4. EVERY dynamic rule must include examples
5. ALL zones must have clear purposes
6. EVERY effect must have specific parameters
7. ALL text must have complete formatting rules
8. EVERY overlay must have position and condition rules
9. ALL measurements must include responsive scaling rules
10. EVERY text element must include topic integration rules
11. ALL visual effects must document progression patterns
12. EVERY zone must specify topic adaptation rules
13. Include caption templates for training data
14. Define concept generation guidelines
15. Specify style preservation requirements
16. Document series-specific pattern rules

ANALYZE FOR:
1. Consistent elements across thumbnails
2. Text placement and styling patterns
3. Color schemes and effects
4. Overlay usage patterns
5. Clear zones and spacing requirements
6. Dynamic content patterns
7. Environmental integration methods

8. Base Image Composition Details:
   - Focal point positioning and scale
   - Subject-to-frame ratio
   - Negative space requirements
   - Depth and perspective guidelines
   - Character expressions and poses
   - Environmental context rules
   - Lighting direction and intensity
   - Color palette restrictions
   - Texture and material guidelines
   - Camera angle preferences
   - Background complexity levels
   - Motion and energy requirements
   - Visual hierarchy rules
   - Edge treatment specifications
   - Contrast and saturation limits

   9. Thumbnail Panel Structure:
   - Panel count and arrangement
   - Panel division specifications
   - Panel progression patterns
   - Panel size ratios
   - Panel transition effects
   - Panel background evolution
   - Panel spacing requirements

   MANDATORY TRAINING GUIDANCE REQUIREMENTS:
1. MUST include complete "caption_structure" with:
   - "format": Exact template string for training captions
   - "variables": List of all dynamic elements
   - "example": At least one full example caption

2. MUST include complete "concept_generation" with:
   - "prompt_template": Exact base prompt structure for generating new thumbnails
   - "key_descriptors": List of essential visual elements
   - "style_markers": At least 5 specific style identifiers

3. MUST include complete "critical_elements" with:
   - "must_maintain": At least 5 elements that define the series style
   - "can_vary": At least 3 elements that can change
   - "style_anchors": At least 3 key style elements to preserve

VALIDATION RULES:
- Every section must be complete
- No placeholder text allowed
- All lists must have specific, concrete items
- Style markers must be detailed and unique to the series
- Caption template must include all critical elements
- Prompt template must maintain series consistency
The BASE_IMAGE_REQUIREMENTS section MUST include:
- Exact pixel measurements for subject placement
- Specific lighting angles and intensities
- Required negative space around subjects
- Detailed composition ratios
- Background complexity guidelines
- Character scale requirements
- Mood and atmosphere specifications
- Color palette restrictions
- Texture and material requirements

Your output MUST be valid JSON and include ALL sections above.
2. MUST include complete "concept_generation" with:
   - "prompt_template": Exact base prompt structure for generating new thumbnails
   - "key_descriptors": List of essential visual elements
   - "style_markers": At least 5 specific style identifiers

Please analyze ALL these aspects and incorporate them into the guidelines structure. Pay special attention to medium-specific qualities that make the series distinctive and authentic.

Create a comprehensive guideline structure that includes:
1. All standard thumbnail elements
2. Medium-specific technical requirements
3. Style-specific authenticity markers
4. Characteristic imperfections or artifacts
5. Environmental and contextual patterns

Remember: The goal is to capture EVERY nuanced detail that makes these thumbnails distinctive and authentic to their medium and style.


Thumbnails to analyze:
{thumbnail_urls}

Series: {series_name}
Theme: {theme_name}
"""

        response = await client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=10000,
            temperature=0.2,
            messages=[{
                "role": "user", 
                "content": [
                    {"type": "text", "text": prompt},
                    *image_contents
                ]
            }]
        )
        
        return response.content[0].text
    except Exception as e:
        logger.error(f"Error in analyze_thumbnails_with_ai: {str(e)}")
        return None

import tenacity


@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
    retry=tenacity.retry_if_exception_type(replicate.exceptions.ReplicateError),
    reraise=True
)

def run_replicate_prediction(api_token, prompt):
    import replicate
    import time

    client = replicate.Client(api_token=api_token)
    model = "black-forest-labs/flux-1.1-pro"
    version = client.models.get(model).latest_version.id

    prediction = client.predictions.create(
        version=version,
        input={
            "prompt": prompt,
            "width": 1280,
            "height": 720,
            "aspect_ratio": "custom",
            "output_format": "jpg",
            "output_quality": 100,
            "safety_tolerance": 5,
            "prompt_upsampling": True
        }
    )

    while prediction.status not in ["succeeded", "failed"]:
        time.sleep(1)
        prediction = client.predictions.get(prediction.id)

    if prediction.status == "succeeded":
        return prediction.output
    else:
        raise Exception(f"Prediction failed: {prediction.error}")

async def analyze_audience_demographics(comments: List[Dict]) -> Dict:
    """
    Analyze comments to determine audience demographics and engagement patterns
    """
    try:
        # Prepare comments for analysis
        comment_texts = [comment.get('text', '') for comment in comments if comment.get('text')]
        
        if not comment_texts:
            return {
                "is_us_audience": False,
                "confidence": 0,
                "reasons": ["No comments available for analysis"]
            }

        # Combine comments for analysis
        combined_comments = "\n".join(comment_texts[:20])  # Analyze up to 20 comments
        
        # Use Claude with a more explicit prompt
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1000,
            temperature=0,
            messages=[{
                "role": "user",
                "content": (
                    "You are a JSON API. Analyze these YouTube comments to determine if they're from a US audience. "
                    "Respond ONLY with a JSON object in this exact format, nothing else:\n"
                    "{\n"
                    "  \"is_us_audience\": true/false,\n"
                    "  \"confidence\": 0.0-1.0,\n"
                    "  \"reasons\": [\"reason1\", \"reason2\"]\n"
                    "}\n\n"
                    f"Comments to analyze:\n{combined_comments}"
                )
            }]
        )
        
        try:
            # Extract the content and convert TextBlock to string
            content = str(response.content[0].text) if isinstance(response.content, list) else str(response.content)
            # Clean the response to ensure it's valid JSON
            content = content.strip()
            if content.startswith('```json'):
                content = content.split('```json')[1]
            if content.endswith('```'):
                content = content.split('```')[0]
            content = content.strip()
            
            analysis = json.loads(content)
            return analysis
            
        except (json.JSONDecodeError, IndexError, AttributeError) as e:
            logger.error(f"Failed to parse Claude's response as JSON: {str(e)}")
            return {
                "is_us_audience": False,
                "confidence": 0,
                "reasons": ["Failed to parse demographic analysis"]
            }

    except Exception as e:
        logger.error(f"Error in analyze_audience_demographics: {str(e)}", exc_info=True)
        return {
            "is_us_audience": False,
            "confidence": 0,
            "reasons": [f"Analysis error: {str(e)}"]
        }

def check_ffmpeg():
    """Verify ffmpeg is available"""
    ffmpeg_paths = [
        r"E:\ffmpeg\ffmpeg-n7.1-latest-win64-gpl-7.1\bin\ffmpeg.exe",
        r"C:\ffmpeg\ffmpeg-n7.1-latest-win64-gpl-7.1\bin\ffmpeg.exe",
    ]
    
    for path in ffmpeg_paths:
        if path and os.path.exists(path):
            logger.info(f"Found ffmpeg at: {path}")
            # Set environment variables
            os.environ["FFMPEG_BINARY"] = path
            os.environ["PATH"] = f"{os.path.dirname(path)};{os.environ.get('PATH', '')}"
            # Explicitly tell pydub where to find ffmpeg
            AudioSegment.converter = path
            AudioSegment.ffmpeg = path
            AudioSegment.ffprobe = path.replace("ffmpeg.exe", "ffprobe.exe")
            return True
            
    logger.error("ffmpeg not found in any expected paths")
    return False
import re
from typing import List, Dict

def remove_metadata(script: str) -> str:
    """
    Remove extraneous metadata from the script.
    
    This function removes:
      - "Word count:" lines
      - "Segment:" lines
      - "Total word count:" lines
      - "Total duration:" lines
      - Combined script notice lines
      - "[CLIP NEEDED: ...]" sections
      - Extra newlines
    """
    script = re.sub(r'Word count:.*?\n', '', script)
    script = re.sub(r'Segment:.*?\n', '', script)
    script = re.sub(r'Total word count:.*?\n', '', script)
    script = re.sub(r'Total duration:.*?\n', '', script)
    script = re.sub(r'I have combined the script segments as requested,.*\n', '', script)
    script = re.sub(r'\[CLIP NEEDED:.*?\]', '', script)
    script = re.sub(r'\n\s*\n', '\n', script)
    return script

def split_script_into_segments(script: str) -> List[Dict[str, str]]:
    """
    Split the script into segments based on a header pattern.
    
    This function assumes each segment begins with a header line in the format:
      The Prisoner's Dilemma (45:15 - 59:45, Duration: 14:30)
    
    If no such headers are found, the entire script is returned as one segment.
    """
    segment_pattern = r"(?m)^(?P<header>.+\(\d+(?::\d{2}){1,2}\s*-\s*\d+(?::\d{2}){1,2},\s*Duration:\s*\d+(?::\d{2}){1,2}\))\s*\n"
    segments = []
    matches = list(re.finditer(segment_pattern, script))
    
    if not matches:
        segments.append({"title": "Full Script", "content": script})
        return segments
    
    for i, match in enumerate(matches):
        header = match.group("header").strip()
        start_index = match.end()
        end_index = matches[i + 1].start() if i + 1 < len(matches) else len(script)
        content = script[start_index:end_index].strip()
        segments.append({"title": header, "content": content})
    
    return segments

async def generate_kokoro_voice_over(
    script: str,
    voice_selections: Dict[str, str],
    user_id: str,
    group_id: str,
    series_name: str,
    theme_name: str,
    title: str
) -> Optional[str]:
    """
    Generate segmented Kokoro voice over audio for the given script.
    Modified to use external server for processing.
    """
    # Clean the script to remove segment breaks
    script = script.replace("=== SEGMENT BREAK ===", "").strip()
    
    try:
        # Get the Drive service.
        drive_service = get_drive_service()
        if not drive_service:
            raise ValueError("Failed to initialize Drive service")
        
        # Create a folder in Google Drive for all segment files.
        timestamp = int(time.time())
        folder_metadata = {
            'name': f'Voice_Over_{title}_{user_id}_{timestamp}',
            'mimeType': 'application/vnd.google-apps.folder',
            'description': f'Voice overlays for video "{title}" generated for user {user_id}'
        }
        folder = drive_service.files().create(
            body=folder_metadata,
            fields='id,webViewLink'
        ).execute()
        folder_id = folder['id']
        folder_url = folder['webViewLink']
        logger.info(f"Created Drive folder with URL: {folder_url}")
        
        # Make the folder public so anyone can view its contents.
        drive_service.permissions().create(
            fileId=folder_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        
        # Process script into segments
        cleaned_script = remove_metadata(script)
        segments = split_script_into_segments(cleaned_script)
        logger.info(f"Found {len(segments)} segment(s) in the script.")
            
        # Send to external server for processing
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                data = {
                    "folder_id": folder_id,
                    "segments": segments,
                    "voice_selections": voice_selections,
                    "user_id": user_id
                }
                
                # Use your server's actual IP address or domain
                url = "http://157.180.0.71:8081/api/process-audio"
                
                async with session.post(url, json=data, timeout=60) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Successfully sent to external server: {result}")
                    else:
                        error_text = await response.text()
                        logger.error(f"Error from external server: {error_text}")
        except Exception as server_error:
            logger.error(f"Error communicating with voice server: {str(server_error)}")
            # Continue anyway since we've already created the folder
        
        # Return the folder URL immediately while audio generation continues in background
        return folder_url

    except Exception as e:
        logger.error(f"Error in generate_kokoro_voice_over: {str(e)}", exc_info=True)
        return None


def remove_subsegment_headers(script: str) -> str:
    """
    Remove sub-segment headers like "Setup & Context (00:00:30 - 00:02:00)" from the script.
    These are structural elements for organization but should not be narrated.
    
    Args:
        script: The input script text
        
    Returns:
        Cleaned script with sub-segment headers removed
    """
    # Pattern to match sub-segment headers like "Setup & Context (00:00:30 - 00:02:00)"
    # This pattern looks for text followed by a timestamp in parentheses
    pattern = r'\n?[A-Za-z\s&\-\']+\s*\(\d{2}:\d{2}(?::\d{2})?\s*-\s*\d{2}:\d{2}(?::\d{2})?(?:,\s*Duration:\s*\d+:\d+)?\)\n'
    
    # Replace headers with just a newline to maintain spacing
    cleaned_script = re.sub(pattern, '\n', script)
    
    # Word count lines (often appear at the end of segments)
    word_count_pattern = r'\n\[?Word count:?\s*\d+\s*(?:words)?\]?\n'
    cleaned_script = re.sub(word_count_pattern, '\n', cleaned_script)
    
    return cleaned_script

async def generate_thumbnail_with_replicate(concept: str, reference_urls: List[str]) -> Optional[str]:
    try:
        replicate_api_token = os.getenv("REPLICATE_API_TOKEN")
        if not replicate_api_token:
            logger.error("REPLICATE_API_TOKEN is not set in the environment variables")
            return None

        prompt = f"Create a YouTube thumbnail with the following specifications: {concept}. Use the style and composition of these reference thumbnails: {', '.join(reference_urls)}"

        output = await asyncio.to_thread(run_replicate_prediction, replicate_api_token, prompt)

        if isinstance(output, str) and output.startswith('http'):
            return output
        elif isinstance(output, list) and len(output) > 0 and isinstance(output[0], str) and output[0].startswith('http'):
            return output[0]
        elif isinstance(output, dict) and 'output' in output:
            return output['output']
        else:
            logger.warning(f"Unexpected output format from Replicate API: {output}")
            return None

    except replicate.exceptions.ReplicateError as e:
        logger.error(f"Replicate API error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error generating image with Replicate API: {str(e)}", exc_info=True)
        return None

import aiohttp
import os
import zipfile
import shutil
import os
import asyncio
import aiohttp
import shutil
import tempfile
import replicate
import re
from typing import List, Optional
from config import REPLICATE_API_TOKEN, logger

async def download_and_prepare_images(thumbnail_data: List[Any], captions: Dict[str, str]) -> str:
    """
    Download images and prepare them for training with proper cropping.
    """
    temp_dir = tempfile.mkdtemp()
    logger.info(f"Created temporary directory at {temp_dir}")
    
    # Create images directory
    images_dir = os.path.join(temp_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    
    # YouTube thumbnail aspect ratio (16:9)
    TARGET_ASPECT_RATIO = 16/9
    # Maximum dimensions allowed by the model
    MAX_SIZE = 1568
    
    # Download and save images
    for i, item in enumerate(thumbnail_data, 1):
        url = item['url'] if isinstance(item, dict) else item
        filename = f"image_{i}.jpg"
        filepath = os.path.join(images_dir, filename)
        
        logger.info(f"Downloading image {i}/{len(thumbnail_data)}: {url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to download image from {url}, status code: {response.status}")
                        continue
                    
                    data = await response.read()
                    if not data:
                        logger.warning(f"Empty data received from {url}")
                        continue
                    
                    # Process image
                    try:
                        img = Image.open(BytesIO(data))
                        
                        # Convert to RGB if it's RGBA to avoid issues
                        if img.mode == 'RGBA':
                            img = img.convert('RGB')
                        
                        # Calculate proper dimensions for 16:9 aspect ratio
                        current_ratio = img.width / img.height
                        
                        if current_ratio > TARGET_ASPECT_RATIO:
                            # Image is wider than 16:9, crop width
                            new_width = int(img.height * TARGET_ASPECT_RATIO)
                            left = (img.width - new_width) // 2
                            img = img.crop((left, 0, left + new_width, img.height))
                        elif current_ratio < TARGET_ASPECT_RATIO:
                            # Image is taller than 16:9, crop height
                            new_height = int(img.width / TARGET_ASPECT_RATIO)
                            top = (img.height - new_height) // 2
                            img = img.crop((0, top, img.width, top + new_height))
                        
                        # Resize if needed while maintaining aspect ratio
                        if img.width > MAX_SIZE or img.height > MAX_SIZE:
                            # Calculate dimensions that maintain aspect ratio
                            if img.width >= img.height:
                                new_width = MAX_SIZE
                                new_height = int(MAX_SIZE / TARGET_ASPECT_RATIO)
                            else:
                                new_height = MAX_SIZE
                                new_width = int(MAX_SIZE * TARGET_ASPECT_RATIO)
                            
                            img = img.resize((new_width, new_height), Image.LANCZOS)
                        
                        # Save image
                        img.save(filepath, format="JPEG", quality=95)
                        
                        # Create caption file
                        title = item.get('title', '') if isinstance(item, dict) else ''
                        caption = captions.get(url, captions.get(title, ''))
                        
                        if caption:
                            caption_filepath = os.path.join(images_dir, f"image_{i}.txt")
                            with open(caption_filepath, 'w', encoding='utf-8') as f:
                                f.write(caption)
                    except Exception as img_error:
                        logger.warning(f"Error processing image {url}: {str(img_error)}")
                        continue
        except Exception as e:
            logger.warning(f"Error processing image {url}: {str(e)}")
            continue
    
    # Create zip file
    logger.info("Creating zip file of training images")
    zip_filepath = os.path.join(temp_dir, "training_images.zip")
    with zipfile.ZipFile(zip_filepath, 'w') as zipf:
        for root, dirs, files in os.walk(images_dir):
            for file in files:
                zipf.write(
                    os.path.join(root, file),
                    os.path.relpath(os.path.join(root, file), temp_dir)
                )
    
    logger.info(f"Created zip file at {zip_filepath}")
    return temp_dir

async def download_image(session, url, filepath):
    async with session.get(url) as resp:
        if resp.status == 200:
            with open(filepath, 'wb') as f:
                f.write(await resp.read())
async def train_model_with_replicate(
    training_data_path: str,
    series_name: str, 
    theme_name: str,
    guidelines: Any = None  # Accept any type for guidelines
) -> Optional[dict]:
    try:
        # Create shortened model name (max 82 chars)
        base_name = f"flux_{series_name}_{theme_name}".replace(' ', '_').lower()
        safe_model_name = re.sub(r'[^a-z0-9-]', '-', base_name)
        if len(safe_model_name) > 82:
            # Truncate while keeping meaningful parts
            words = safe_model_name.split('-')
            safe_model_name = '-'.join(words[:3])  # Keep first 3 parts
            safe_model_name = safe_model_name[:82]

        replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)
        
        # Parse guidelines if provided
        style_prefix = ""
        style_suffix = ""
        if guidelines:
            try:
                # Handle both string and dict input
                if isinstance(guidelines, str) and guidelines.strip():
                    guidelines_data = json.loads(guidelines)
                elif isinstance(guidelines, dict):
                    guidelines_data = guidelines
                else:
                    guidelines_data = {}
                
                # Extract training guidance
                if "TRAINING_GUIDANCE" in guidelines_data:
                    training_guidance = guidelines_data["TRAINING_GUIDANCE"]
                    
                    # Build style-preserving prefix
                    critical_elements = training_guidance.get("critical_elements", {}).get("must_maintain", [])
                    if critical_elements:
                        style_prefix = f"YouTube thumbnail in the style of {safe_model_name}, maintaining {', '.join(critical_elements)}"
                    
                    # Build style-preserving suffix
                    style_markers = training_guidance.get("concept_generation", {}).get("style_markers", [])
                    if style_markers:
                        style_suffix = f", preserving {', '.join(style_markers)}"
            except Exception as e:
                logger.warning(f"Failed to parse guidelines: {str(e)}")
        else:
            guidelines_data = {}

        # Create or get existing model
        try:
            model = replicate_client.models.get(f"whysoboneless/{safe_model_name}")
            logger.info(f"Found existing model: {safe_model_name}")
        except Exception:
            model = replicate_client.models.create(
                owner="whysoboneless",
                name=safe_model_name,
                visibility="private",
                hardware="gpu-a100-large",
                description=f"Fine-tuned FLUX model for {series_name} - {theme_name} thumbnails"
            )
            logger.info(f"Created new model: {safe_model_name}")

        # Build training input with style-preserving captions and optimized parameters
        training_input = {
            "input_images": open(os.path.join(training_data_path, 'training_images.zip'), "rb"),
            "steps": 1500,
            "trigger_word": safe_model_name,
            "learning_rate": 0.0003,
            "batch_size": 2,
            "resolution": "1280,720",
            "optimizer": "lion8bit",
            "autocaption": True,  # Disable autocaption
            "caption_dropout_rate": 0.0,  # No caption dropout since we're using custom captions
            "lora_rank": 32,
            "cache_latents": True,
            "layers_to_optimize_regex": "transformer.single_transformer_blocks.(12|16|20).proj_out",
            "scheduler": "DPMSolverMultistep",
            "output_format": "png",
            "output_quality": 100,
            "prompt_strength": 0.8,
            "guidance_scale": 7.5,
            "disable_safety_checker": True
        }
    
        # Add style-preserving caption guidance if available
        if style_prefix:
            training_input["autocaption_prefix"] = style_prefix
        if style_suffix:
            training_input["autocaption_suffix"] = style_suffix

        # Start training using Flux trainer
        training = replicate_client.trainings.create(
            version="ostris/flux-dev-lora-trainer:e440909d3512c31646ee2e0c7d6f6f4923224863a6a10c494606e79fb5844497",
            input=training_input,
            destination=f"whysoboneless/{safe_model_name}"
        )

        logger.info(f"Training started with ID: {training.id}")
        logger.info(f"Using style prefix: {style_prefix}")
        logger.info(f"Using style suffix: {style_suffix}")

        # Wait for training to complete
        status = training.status
        retries = 0
        max_retries = 5

        while status == "starting" and retries < max_retries:
            await asyncio.sleep(10)
            training = replicate_client.trainings.get(training.id)
            status = training.status
            retries += 1
            logger.info(f"Training status: {status} (attempt {retries})")

        if status == "starting":
            raise Exception("Training failed to start after multiple attempts")

        while status == "processing":
            logger.info(f"Training status: {status}")
            await asyncio.sleep(30)
            training = replicate_client.trainings.get(training.id)
            status = training.status

        if status == "succeeded":
            logger.info("Training completed successfully")
            version = replicate_client.models.get(f"whysoboneless/{safe_model_name}").versions.list()[0]
            
            return {
                "version": version.id,
                "model_name": safe_model_name,
                "weights_url": training.output.get("weights"),
                "trigger_word": safe_model_name
            }
        else:
            logger.error(f"Training failed with status: {status}")
            return None

    except Exception as e:
        logger.error(f"Error during model training: {str(e)}")
        return None

async def poll_training_status(training):
    while True:
        training.reload()
        if training.status == "succeeded":
            logger.info("Training succeeded")
            break
        elif training.status == "failed":
            logger.error("Training failed")
            raise Exception("Model training failed")
        else:
            logger.info(f"Training status: {training.status}, waiting...")
            await asyncio.sleep(30)  # Wait 30 seconds before checking again

async def create_training_captions(guidelines: str, thumbnail_urls: List[str], titles: List[str] = None) -> Dict[str, str]:
    """
    Creates captions for training images based on guidelines analysis and titles.
    Returns a dictionary mapping image URLs to their captions.
    """
    try:
        # Parse the guidelines JSON with error handling
        try:
            guidelines_data = json.loads(guidelines)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing guidelines JSON: {str(e)}")
            guidelines_data = {
                "LAYOUT_STRUCTURE": {
                    "canvas": "",
                    "grid_system": {"main_content": {"description": ""}}
                },
                "TEXT_SPECIFICATIONS": {"main_text": {"font": ""}}
            }
        
        # Create base caption template from guidelines
        base_caption = (
            f"YouTube thumbnail with {guidelines_data.get('LAYOUT_STRUCTURE', {}).get('canvas', '')}. "
            f"Main content zone: {guidelines_data.get('LAYOUT_STRUCTURE', {}).get('grid_system', {}).get('main_content', {}).get('description', '')}. "
            f"Text style: {guidelines_data.get('TEXT_SPECIFICATIONS', {}).get('main_text', {}).get('font', '')}"
        )

        # Create captions dictionary
        captions = {}
        for i, url in enumerate(thumbnail_urls):
            title = titles[i] if titles and i < len(titles) else ""
            caption = f"{base_caption} Title: {title}"
            captions[url] = caption.strip()
            
        return captions
        
    except Exception as e:
        logger.error(f"Error creating training captions: {str(e)}")
        return {url: f"YouTube thumbnail for {titles[i] if titles and i < len(titles) else 'video'}" 
                for i, url in enumerate(thumbnail_urls)}

async def generate_rain_video(
    voice_over_url: str,
    title: str,
    user_id: str,
    group_id: str,
    series_name: str,
    theme_name: str,
    duration_minutes: int = None,
    plot_outline: str = None,
    visual_style: str = "black_rain"
) -> tuple[Optional[str], Optional[float]]:
    """Creates a folder and immediately returns the link, then processes in background"""
    try:
        import os
        import time
        import re
        from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
        from services.cloud_service import CloudVideoService
        
        logger.info(f"Starting rain video generation for '{title}'")
        
        # Get Drive service
        drive_service = get_drive_service()
        if not drive_service:
            raise ValueError("Failed to initialize Drive service")
        
        # Create a folder in Google Drive for the video - DO THIS IMMEDIATELY
        timestamp = int(time.time())
        video_folder_metadata = {
            'name': f'Video_{title.replace(" ", "_")}_{timestamp}',
            'mimeType': 'application/vnd.google-apps.folder',
            'description': f'Video for "{title}" generated for user {user_id}'
        }
        
        video_folder = drive_service.files().create(
            body=video_folder_metadata,
            fields='id,webViewLink'
        ).execute()
        
        video_folder_id = video_folder['id']
        video_folder_url = video_folder['webViewLink']
        
        # Make the folder public
        drive_service.permissions().create(
            fileId=video_folder_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        
        # START BACKGROUND TASK - Don't wait for it to finish
        asyncio.create_task(_process_rain_video_background(
            voice_over_url=voice_over_url,
            title=title,
            user_id=user_id,
            group_id=group_id,
            series_name=series_name,
            theme_name=theme_name,
            duration_minutes=duration_minutes,
            video_folder_id=video_folder_id,
            visual_style=visual_style
        ))
        
        # Return folder URL immediately so UI can be updated
        return video_folder_url, None
        
    except Exception as e:
        logger.error(f"Error in generate_rain_video: {str(e)}", exc_info=True)
        return None, None

async def _process_rain_video_background(
    voice_over_url: str,
    title: str,
    user_id: str,
    group_id: str,
    series_name: str,
    theme_name: str,
    duration_minutes: int,
    video_folder_id: str,
    visual_style: str = "black_rain",
    plot_outline: str = None
):
    """Background task to process video without blocking UI"""
    try:
        # Get Drive service
        drive_service = get_drive_service()
        if not drive_service:
            logger.error("Failed to initialize Drive service in background task")
            return {'error': 'Failed to initialize Drive service', 'failed': True}
        
        # Log the voice_over_url for debugging
        logger.info(f"Voice over URL: {voice_over_url}")
        
        # Get the folder ID from the voice-over URL (using the old method that worked)
        folder_id = voice_over_url.split('/')[-1]
        logger.info(f"Extracted folder ID: {folder_id}")
        
        # Sharing output folder with service account
        logger.info(f"Sharing output folder {video_folder_id} with service account")
        try:
            # Add the service account as an editor to the folder
            permission = {
                'type': 'user',
                'role': 'writer',
                'emailAddress': 'nicole-workspace-service@festive-magpie-436206-a7.iam.gserviceaccount.com'
            }
            
            drive_service.permissions().create(
                fileId=video_folder_id,
                body=permission,
                fields='id'
            ).execute()
            
            logger.info(f"Successfully shared folder with service account")
        except Exception as e:
            logger.error(f"Error sharing folder with service account: {str(e)}")
        
        # List files in the voice-over folder
        voice_files = []
        page_token = None
        
        try:
            logger.info(f"Listing files in folder: {folder_id}")
            while True:
                response = drive_service.files().list(
                    q=f"'{folder_id}' in parents",
                    spaces='drive',
                    fields='nextPageToken, files(id, name, webViewLink)',
                    pageToken=page_token
                ).execute()
                
                files_in_response = response.get('files', [])
                logger.info(f"Found {len(files_in_response)} files in response")
                
                for file in files_in_response:
                    voice_files.append(file)
                    logger.info(f"Found file: {file.get('name')} (ID: {file.get('id')})")
                    
                page_token = response.get('nextPageToken')
                if not page_token:
                    break
        except Exception as e:
            logger.error(f"Error listing files in folder: {str(e)}")
            return {'error': f'Error listing files: {str(e)}', 'failed': True}
        
        if not voice_files:
            logger.error("No voice-over files found in the provided folder")
            return {'error': 'No voice-over files found', 'failed': True}
        
        # Get file IDs for cloud processing
        file_ids = [file['id'] for file in voice_files]
        logger.info(f"File IDs for processing: {file_ids}")
        
        # Create cloud service client and process video
        cloud_service = CloudVideoService()
        
        # Send to cloud for processing
        logger.info(f"Sending to cloud service with folder_id={folder_id}, output_folder_id={video_folder_id}, file_ids={file_ids}")
        result = await cloud_service.process_rain_video(
            drive_service=drive_service,
            folder_id=folder_id,
            output_folder_id=video_folder_id,
            file_ids=file_ids,
            title=title,
            visual_style=visual_style,
            plot_outline=plot_outline
        )
        
        if isinstance(result, dict) and result.get('success'):
            # Update database with the final video link if needed
            logger.info(f"Cloud service successfully processed video: {result.get('video_url')}")
            
            # Create a README file in the folder to notify completion
            readme_metadata = {
                'name': 'README.txt',
                'parents': [video_folder_id],
                'description': 'Processed video information'
            }
            
            readme_content = (
                f"Video processing completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Title: {title}\n"
                f"Duration: {result.get('duration_minutes', 'Unknown')} minutes\n\n"
                f"Direct video link: {result.get('video_url', 'Not available')}\n"
            )
            
            # Create a temporary file with the README content
            with tempfile.NamedTemporaryFile(mode='w+', delete=False) as f:
                f.write(readme_content)
                readme_path = f.name
            
            # Upload the README file
            media = MediaFileUpload(readme_path, mimetype='text/plain')
            drive_service.files().create(
                body=readme_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            # Clean up
            try:
                # Try to delete the file, but don't worry if it fails
                os.unlink(readme_path)
            except Exception as e:
                logger.warning(f"Could not delete temporary README file: {str(e)}")
                # This is not critical, continue processing
            
            # Update database with video URL
            from database import db
            video_url = result.get('video_url')
            video_duration = result.get('duration_minutes')
            
            if video_url and group_id and series_name and theme_name and title:
                await db.save_video_url(
                    group_id=group_id,
                    series_name=series_name,
                    theme_name=theme_name,
                    video_title=title,
                    video_url=video_url,
                    duration_minutes=video_duration
                )
                logger.info(f"Updated database with video URL for {title}")
            return result
        else:
            error_msg = result if isinstance(result, str) else result.get('error', 'Unknown error')
            logger.error(f"Cloud processing failed: {error_msg}")
            return {'error': error_msg, 'failed': True}
            
    except Exception as e:
        logger.error(f"Error in background video processing: {str(e)}", exc_info=True)
        return {'error': str(e), 'failed': True}

async def generate_thumbnail_with_trained_model(db, group_id: str, series_name: str, theme_name: str, concept: str, thumbnail_urls: List[str] = None) -> Optional[List[str]]:
    """
    Generate thumbnails using a trained Replicate model.
    Returns a list of URLs to the generated thumbnails.
    """
    try:
        # 1. Get model info and validate it
        logger.debug(f"Starting thumbnail generation for {series_name} - {theme_name}")
        
        model_info = await db.get_trained_model_info(group_id, series_name, theme_name)
        if not model_info:
            logger.error("No model info found in database")
            return None
            
        if not model_info.get('version'):
            logger.error("Model version missing from model_info")
            return None
            
        # 2. Prepare model parameters
        safe_model_name = model_info.get("trigger_word", "").strip()
        if not safe_model_name:
            safe_model_name = model_info.get("model_name", "")
            if not safe_model_name:
                logger.error("No model name found in model_info")
                return None
                
        version = model_info.get("version")
        trigger_word = model_info.get("trigger_word", safe_model_name)
        
        # 3. Get guidelines to determine style
        try:
            guidelines = await db.get_thumbnail_guidelines(group_id, series_name, theme_name)
            if isinstance(guidelines, str):
                try:
                    guidelines_data = json.loads(guidelines)
                except json.JSONDecodeError:
                    # Only log a small excerpt instead of potentially large data
                    logger.debug("Invalid JSON format for guidelines, using defaults")
                    guidelines_data = {}
            else:
                guidelines_data = guidelines if guidelines else {}
        except Exception as e:
            logger.debug(f"Error getting guidelines: {str(e)}")
            guidelines_data = {}
        
        # 4. Determine guidance scale based on style
        style_type = guidelines_data.get("STYLE_CLASSIFICATION", {}).get("primary_category", {}).get("main_type", "realistic")
        if not style_type or style_type == "":
            style_type = "realistic"
            
        # Define guidance scales for different style types
        guidance_scale = {
            # Real-World Content (reduced for more natural look)
            "realistic_video": 2.5,
            "realistic_photo": 2.5,
            "realistic_candid": 2.5,
            
            # Gaming Content (slightly reduced)
            "game_screenshot": 3.0,
            "game_fortnite": 3.5,
            "game_minecraft": 3.5,
            "game_roblox": 3.5,
            "game_animated": 3.5,
            
            # Animated Content (moderated for better balance)
            "anime": 4.0,
            "cartoon_western": 3.5,
            "cartoon_3d": 3.5,
            "cartoon_chibi": 4.0,
            
            # Digital Art (adjusted for cleaner results)
            "illustration_digital": 3.5,
            "illustration_comic": 3.5,
            "illustration_concept": 3.0,
            
            # Mixed/Hybrid (fine-tuned for better blending)
            "mixed_game_real": 3.0,
            "mixed_anime_real": 3.5,
            "mixed_cartoon_real": 3.0,
            
            # Legacy categories
            "realistic": 2.5,
            "photo": 2.5,
            "video": 2.5,
            "cartoon": 4.0,
            "animated": 4.0,
            "illustration": 3.5,
            "mixed": 3.0
        }.get(style_type.lower(), 3.5)  # Default to 3.5 if style not recognized
        
        # 5. Build input dictionary with text size emphasis
        input_dict = {
            "prompt": f"{trigger_word}, {concept}, ENORMOUS TEXT (occupying 45-55% of width), MAXIMUM SIZE TYPOGRAPHY, EXTREMELY LARGE BOLD TEXT, dominating text composition, massive readable fonts, high contrast typography, clear text edges, YouTube thumbnail with enormous text, maintain original style",
            "model": "dev",
            "width": 1280,
            "height": 720,
            "scheduler": "DPMSolverMultistep",
            "lora_scale": 0.75,
            "num_outputs": 1,
            "aspect_ratio": "16:9", 
            "output_format": "png",
            "output_quality": 100,
            "num_inference_steps": 50,
            "guidance_scale": guidance_scale,
            "prompt_strength": 0.8,
            "disable_safety_checker": True,
            "go_fast": False,
            "negative_prompt": "small text, medium text, tiny text, blurry text, distorted text, complex font, stylized text, unreadable text, bad typography, low contrast text, watermark, border, text smaller than 40% of frame width",
        }
        
        # 6. Make API call to generate thumbnail
        try:
            logger.debug(f"Making API call to Replicate for {safe_model_name}")
            client = replicate.Client(api_token=REPLICATE_API_TOKEN)
            output = client.run(
                f"whysoboneless/{safe_model_name}:{version}",
                input=input_dict
            )
            
            # 7. Process output based on response format
            if output:
                if isinstance(output, list):
                    return [str(url) for url in output if url]
                elif isinstance(output, dict) and 'output' in output:
                    urls = output['output']
                    return [str(url) for url in urls] if isinstance(urls, list) else [str(urls)]
                else:
                    return [str(output)]
            else:
                logger.error("Empty response from Replicate API")
                return None
                
        except Exception as api_error:
            logger.error(f"Error calling Replicate API: {str(api_error)}")
            
            # 8. Fallback: Try direct API call if client.run fails
            try:
                logger.debug("Attempting fallback with direct API call")
                import requests
                
                headers = {"Authorization": f"Token {REPLICATE_API_TOKEN}"}
                payload = {
                    "version": version,
                    "input": input_dict
                }
                
                response = requests.post(
                    f"https://api.replicate.com/v1/models/whysoboneless/{safe_model_name}/predictions",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 201:
                    prediction = response.json()
                    prediction_id = prediction["id"]
                    
                    # Poll for completion
                    for _ in range(60):  # Wait up to 5 minutes
                        time.sleep(5)
                        response = requests.get(
                            f"https://api.replicate.com/v1/predictions/{prediction_id}",
                            headers=headers
                        )
                        data = response.json()
                        
                        if data["status"] == "succeeded":
                            output = data["output"]
                            if isinstance(output, list):
                                return [str(url) for url in output if url]
                            return [str(output)]
                        
                        if data["status"] == "failed":
                            logger.error(f"Prediction failed: {data.get('error')}")
                            break
                else:
                    logger.error(f"Fallback API call failed with status {response.status_code}")
                    
            except Exception as fallback_error:
                logger.error(f"Fallback method also failed: {str(fallback_error)}")
    
    except Exception as e:
        logger.error(f"Error generating thumbnail: {str(e)}")
        return None

    
async def generate_search_terms(series, theme, example_titles, custom_niche=None):
    """Generate effective search terms from ANY niche based on theme and examples"""
    
    import json, re
    
    # Create a direct prompt that forces a simple response in correct format
    prompt = f"""
    I need 5 search terms to find trending YouTube videos about: {theme['name']}
    
    Some example video titles in this area:
    {example_titles[:3]}
    
    RULES:
    1. ONLY include search terms 1-3 words long
    2. Make them EXACTLY what people type into YouTube search
    3. Focus on the core topic, not marketing advice
    4. MUST be simple terms people actually search
    
    ONLY respond with a JSON array like this - no other text:
    ["term one", "term two", "term three", "term four", "term five"]
    """
    
    try:
        # Get response and retry if needed to ensure we get a valid format
        for attempt in range(3):  # Try up to 3 times
            response = await generate_ai_response(prompt, model="claude-sonnet-4-5-20250929")
            
            # Multiple regex patterns to extract JSON array
            patterns = [
                r'\[\s*"[^"]+(?:",\s*"[^"]+")*\s*\]',  # Standard JSON array
                r'\[\'[^\']+(?:\',\s*\'[^\']+\')*\s*\]',  # Array with single quotes
                r'\[\s*([^,\]]+(?:,\s*[^,\]]+)*)\s*\]'  # Bare array without quotes
            ]
            
            for pattern in patterns:
                json_match = re.search(pattern, response)
                if json_match:
                    try:
                        # Try to parse as JSON
                        json_str = json_match.group(0).replace("'", '"')
                        search_terms = json.loads(json_str)
                        
                        # Very minimal validation - just ensure we have strings
                        terms = [str(term).strip() for term in search_terms if term]
                        if terms:
                            logger.info(f"Generated search terms: {terms}")
                            return terms[:5]
                    except:
                        continue
            
            # If we get here, try a simpler prompt
            prompt = f"Give me 5 popular YouTube search terms about {theme['name']}. Response format: [\"term1\", \"term2\", ...]"
        
        # Emergency fallback - split theme name into individual words
        words = theme['name'].split()
        terms = [theme['name']]
        terms.extend([w for w in words if len(w) > 3])
        terms.extend([f"{words[0]} {words[i]}" for i in range(1, min(4, len(words)))])
        
        logger.warning(f"Using emergency terms from theme name: {terms[:5]}")
        return terms[:5]
            
    except Exception as e:
        logger.error(f"Error in generate_search_terms: {str(e)}")
        return [theme['name']]

async def extract_keywords_from_titles(titles: List[str]) -> List[str]:
    """Extract common keywords and themes from a list of video titles using AI"""
    if not titles or len(titles) == 0:
        return []
        
    prompt = f"""
    Analyze these {len(titles)} trending YouTube video titles and extract the top 10-15 keywords or phrases that:
    1. Represent trending topics or themes
    2. Could be incorporated into new video titles
    3. Would likely drive high engagement

    Video titles:
    {json.dumps(titles, indent=2)}

    Format your response as a JSON array of strings containing ONLY the keywords/phrases.
    Each keyword should be a single word or short phrase (1-3 words maximum).
    """
    
    try:
        response = await generate_ai_response(prompt, model="claude-3-haiku-20240307")
        
        # Extract JSON array from response
        json_match = re.search(r'\[\s*"[^"]+(?:",\s*"[^"]+")*\s*\]', response)
        if json_match:
            keywords = json.loads(json_match.group(0))
            logger.info(f"Extracted {len(keywords)} keywords from titles")
            return keywords
        else:
            # Fallback parsing for non-JSON responses
            keywords = []
            for line in response.split('\n'):
                # Look for list items like "- keyword" or "1. keyword"
                match = re.match(r'^(\d+\.|\*|\-)\s+(.+)$', line)
                if match:
                    keyword = match.group(2).strip('" ')
                    keywords.append(keyword)
            
            if keywords:
                logger.info(f"Extracted {len(keywords)} keywords using fallback method")
                return keywords
                
            # Last resort - extract any words in quotes
            quote_matches = re.findall(r'"([^"]+)"', response)
            if quote_matches:
                logger.info(f"Extracted {len(quote_matches)} keywords by finding quoted text")
                return quote_matches
            
            logger.warning("Could not extract keywords from AI response")
            return []
            
    except Exception as e:
        logger.error(f"Error extracting keywords from titles: {str(e)}")
        return []

