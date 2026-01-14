# Web App External Dependencies

## Files the webapp imports from parent directory:

### 1. `/config.py` (Discord bot config)
- Contains: API keys, MongoDB URI, Discord credentials
- **Imported by:** `nicole_web_suite_template/config.py`

### 2. `/database.py` (Discord bot database)
- Contains: Full database class with all MongoDB operations
- **Imported by:** `nicole_web_suite_template/core/database.py`

### 3. `/utils/ai_utils.py` (AI utilities)
- Contains: All AI generation functions (breakdown_script, generate_plot_outline, etc.)
- **Imported by:** `nicole_web_suite_template/dashboard/routes.py`
- **Size:** ~9000 lines

### 4. `/channel_discovery_app/channel_discovery_service.py`
- Contains: Channel discovery logic
- **Imported by:** `nicole_web_suite_template/dashboard/routes.py`

## Solutions for Vercel Deployment:

### Option 1: Make Webapp Standalone (RECOMMENDED)
Copy needed files into webapp folder:
```
nicole_web_suite_template/
├── shared/          (NEW - copied from parent)
│   ├── config_base.py      (from /config.py)
│   ├── database_base.py    (from /database.py)
│   └── ai_utils.py         (from /utils/ai_utils.py)
└── services/
    └── channel_discovery_service.py (from /channel_discovery_app/)
```

Then update imports to use local files instead of parent directory.

### Option 2: Deploy Entire Parent Directory
- Upload entire `niche_analysis_bot` folder to GitHub
- Set Vercel root directory to `nicole_web_suite_template`
- All imports will work as-is

---

## Recommendation:
**Use Option 2** (deploy entire repo) because:
- ✅ No code changes needed
- ✅ Keeps bot and webapp in sync
- ✅ Easier to maintain
- ✅ GitHub repo includes everything

Just make sure to add `.gitignore` to exclude:
- `__pycache__/`
- `*.log`
- `.env`
- `node_modules/`
- Downloaded files

