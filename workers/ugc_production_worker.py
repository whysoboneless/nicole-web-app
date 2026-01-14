"""
UGC Production Background Worker
Runs the scheduler continuously to auto-produce videos for active channels
"""

import asyncio
import logging
import sys
import os

# Add parent directory to path for imports
parent_dir = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, parent_dir)

from core.database import Database

# Try importing the scheduler service
try:
    from services.ugc_scheduler_service import get_scheduler
except ImportError:
    # Try absolute import
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ugc_scheduler_service",
        os.path.join(parent_dir, "services", "ugc_scheduler_service.py")
    )
    ugc_scheduler_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ugc_scheduler_module)
    get_scheduler = ugc_scheduler_module.get_scheduler

# Setup logging with immediate console output
import sys

# Configure root logger for this module
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    stream=sys.stdout,
    force=True  # Override any existing config
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Ensure stdout is unbuffered for real-time output
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

async def run_ugc_scheduler():
    """Start the UGC production scheduler"""
    db = Database()
    scheduler = get_scheduler(db)
    
    logger.info("=" * 60)
    logger.info("🤖 UGC PRODUCTION WORKER STARTING")
    logger.info("=" * 60)
    logger.info("📡 Monitoring active TikTok/Instagram channels")
    logger.info("🎬 Auto-producing videos based on upload schedule")
    logger.info("=" * 60)
    
    try:
        await scheduler.start()
    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down UGC worker...")
        scheduler.stop()
    except Exception as e:
        logger.error(f"❌ Fatal error in UGC worker: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(run_ugc_scheduler())

