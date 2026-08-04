#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import pathlib

# Define replacements
replacements = {
    'ArtificeDraft': 'ArtificeDraft',
    'artifice_draft': 'artifice_draft',
    'Artifice': 'Artifice',
}

# Files and directories to search (using pathlib for cross-platform compatibility)
search_paths = [
    '.',
    './src',
]

# Process all files
print("Searching and updating files...")
updated_count = 0

for path_str in search_paths:
    for file_path in pathlib.Path(path_str).glob('**/*'):
        if file_path.is_file() and file_path.suffix.lower() in ['.py', '.md', '.html', '.css', '.json', '.txt']:
            try:
                content = file_path.read_text(encoding='utf-8')
                original_content = content
                
                # Apply replacements
                for old, new in replacements.items():
                    content = content.replace(old, new)
                
                # Check if changes were made
                if content != original_content:
                    file_path.write_text(content, encoding='utf-8')
                    print(f"  Updated {file_path}")
                    updated_count += 1
                    
            except Exception as e:
                print(f"  Error updating {file_path}: {e}")

print(f"\nDone! Updated {updated_count} files.")
