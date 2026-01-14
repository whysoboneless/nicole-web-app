import os

# Read the file
with open('content_studio_routes.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Keep only lines 1-1064 (index 0-1063)
good_lines = lines[:1064]

# Write the cleaned content back
with open('content_studio_routes.py', 'w', encoding='utf-8') as f:
    f.writelines(good_lines)

print(f'File truncated to {len(good_lines)} lines')
os.remove('cleanup_file.py')
