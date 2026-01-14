"""
VFX Workflow Executor
Executes VFX automation workflows from content styles during production
Builds Remotion timelines with learned components and research assets
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from typing import Dict, List, Optional
import re
import json
import logging

logger = logging.getLogger(__name__)


class VFXWorkflowExecutor:
    """
    Executes VFX workflows from content style profiles
    Builds Remotion timelines synced to voice timing
    """
    
    def __init__(self):
        pass
    
    async def build_remotion_timeline(
        self,
        script: str,
        voice_timing: Dict,
        asset_map: Dict,
        vfx_profile: Dict,
        remotion_components: List[Dict]
    ) -> Dict:
        """
        Build complete Remotion timeline from VFX workflow
        
        Args:
            script: Generated script
            voice_timing: Voice timing data with segments
            asset_map: Researched assets per segment
            vfx_profile: VFX profile with automation workflows
            remotion_components: Generated Remotion components
        
        Returns:
            Remotion timeline specification:
            {
              "duration": 600,  # Total duration in frames (30fps)
              "fps": 30,
              "sequences": [
                {
                  "component": "NumberReveal",
                  "props": {"number": 10, "text": "Great Pyramid"},
                  "startFrame": 150,
                  "durationInFrames": 90
                },
                ...
              ],
              "assets": {
                "clips": [...],
                "images": [...]
              }
            }
        """
        
        try:
            logger.info("🎬 Building Remotion timeline from VFX workflow...")
            
            # Get automation workflows
            workflows = vfx_profile.get('automation_workflows', {})
            
            if not workflows:
                logger.warning("No automation workflows in VFX profile")
                return None
            
            # Calculate total duration
            total_duration_seconds = voice_timing.get('total_duration', 0) if voice_timing else 600
            total_frames = int(total_duration_seconds * 30)  # 30 FPS
            
            # Build timeline
            timeline = {
                'duration': total_frames,
                'fps': 30,
                'sequences': [],
                'assets': {
                    'clips': [],
                    'images': []
                }
            }
            
            # Process each segment
            voice_segments = voice_timing.get('segments', []) if voice_timing else []
            
            for i, segment_timing in enumerate(voice_segments):
                segment_start = segment_timing.get('start', 0)
                segment_duration = segment_timing.get('duration', 10)
                start_frame = int(segment_start * 30)
                duration_frames = int(segment_duration * 30)
                
                # Get segment from script
                segment_script = self._get_segment_script(script, i)
                segment_name = self._extract_segment_name(segment_script)
                
                # Get assets for this segment
                segment_assets = asset_map.get(segment_name, {})
                
                # Execute workflow for this segment type
                segment_sequences = await self._execute_segment_workflow(
                    segment_type=segment_name,
                    workflow=workflows.get(segment_name, {}),
                    script_text=segment_script,
                    start_frame=start_frame,
                    duration_frames=duration_frames,
                    assets=segment_assets,
                    components=remotion_components
                )
                
                timeline['sequences'].extend(segment_sequences)
                
                # Add assets to timeline
                if segment_assets.get('clips'):
                    timeline['assets']['clips'].extend(segment_assets['clips'])
                if segment_assets.get('images'):
                    timeline['assets']['images'].extend(segment_assets['images'])
            
            logger.info(f"✅ Timeline built with {len(timeline['sequences'])} sequences")
            return timeline
            
        except Exception as e:
            logger.error(f"❌ Timeline building failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_segment_script(self, script: str, segment_index: int) -> str:
        """Extract script text for specific segment"""
        
        # Split by segment break markers
        segments = script.split('=== SEGMENT BREAK ===')
        
        if segment_index < len(segments):
            return segments[segment_index].strip()
        
        return ""
    
    def _extract_segment_name(self, segment_script: str) -> str:
        """Extract segment name from script header"""
        
        # Pattern: "Segment Name (00:00 - 01:00, Duration: 01:00)"
        match = re.search(r'^(.+?)\s*\(\d{1,2}:\d{2}', segment_script)
        if match:
            return match.group(1).strip()
        
        return "Unknown"
    
    async def _execute_segment_workflow(
        self,
        segment_type: str,
        workflow: Dict,
        script_text: str,
        start_frame: int,
        duration_frames: int,
        assets: Dict,
        components: List[Dict]
    ) -> List[Dict]:
        """Execute automation workflow for a segment"""
        
        try:
            sequences = []
            
            execution_steps = workflow.get('execution_steps', [])
            
            for step in execution_steps:
                action = step.get('action')
                
                if action == 'show_component':
                    # Find matching component
                    component_name = step.get('component')
                    component = next((c for c in components if c['name'] == component_name), None)
                    
                    if component:
                        # Parse script to extract data for props
                        props = await self._populate_component_props(
                            step.get('props', []),
                            script_text,
                            assets
                        )
                        
                        # Calculate timing
                        trigger = step.get('trigger', 'segment_start')
                        component_start = self._calculate_component_start(
                            trigger, start_frame, duration_frames
                        )
                        component_duration = int(step.get('duration', 3) * 30)  # Convert seconds to frames
                        
                        sequences.append({
                            'component': component_name,
                            'props': props,
                            'startFrame': component_start,
                            'durationInFrames': component_duration
                        })
            
            return sequences
            
        except Exception as e:
            logger.error(f"Workflow execution failed for {segment_type}: {e}")
            return []
    
    async def _populate_component_props(
        self,
        prop_definitions: List[Dict],
        script_text: str,
        assets: Dict
    ) -> Dict:
        """Populate component props from script and assets"""
        
        props = {}
        
        for prop_def in prop_definitions:
            prop_name = prop_def.get('name')
            source = prop_def.get('source')
            
            if source == 'script':
                # Extract from script using pattern
                pattern = prop_def.get('pattern', '')
                if pattern:
                    match = re.search(pattern, script_text)
                    if match:
                        props[prop_name] = match.group(1) if match.groups() else match.group(0)
            
            elif source == 'assets':
                # Use researched assets
                asset_type = prop_def.get('asset_type')
                if asset_type in assets:
                    props[prop_name] = assets[asset_type]
        
        return props
    
    def _calculate_component_start(
        self,
        trigger: str,
        segment_start_frame: int,
        segment_duration_frames: int
    ) -> int:
        """Calculate when component should start"""
        
        if trigger == 'segment_start':
            return segment_start_frame
        elif trigger == 'segment_middle':
            return segment_start_frame + (segment_duration_frames // 2)
        elif trigger == 'segment_end':
            return segment_start_frame + segment_duration_frames - 90  # 3 seconds before end
        else:
            # Parse offset like "segment_start+5s"
            offset_match = re.search(r'([+-])(\d+)s', trigger)
            if offset_match:
                operator = offset_match.group(1)
                seconds = int(offset_match.group(2))
                frames_offset = seconds * 30
                
                if operator == '+':
                    return segment_start_frame + frames_offset
                else:
                    return segment_start_frame - frames_offset
        
        return segment_start_frame


# Singleton
vfx_executor = VFXWorkflowExecutor()

