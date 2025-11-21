#!/usr/bin/env python3
"""
Cleanup script to remove the 'case' folder 
"""
import shutil
from pathlib import Path

def remove_if_exists(path: Path, name: str):
    if path.exists() and path.is_dir():
        shutil.rmtree(path)
        print(f"🗑️  Deleted: {name}")
    else:
        print(f"ℹ️  Not found: {name}")

def _remove_silently(path: Path):
    """Delete a file or directory without printing anything."""
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except Exception:
            pass

def main():
    script_dir  = Path(__file__).resolve().parent
    case_dir    = script_dir / 'case'
    scripts_dir = script_dir / 'scripts'
    input_dir   = script_dir / 'inputSTL'

    print("🚨 This will permanently delete the following folder:")
    print(f"- {case_dir}")
    confirm = input("Are you sure? [y/N]: ").strip().lower()
    if confirm == 'y':
        # Delete 'case/' with output (as before)
        remove_if_exists(case_dir, 'case/')

        # Silently delete scripts/__pycache__
        _remove_silently(scripts_dir / '__pycache__')

        # Silently delete rotated STL copies in inputSTL (keep originals)
        if input_dir.is_dir():
            for p in input_dir.glob("*.stl"):
                if "rotated" in p.stem.lower():
                    _remove_silently(p)

        print("✅ Cleanup complete.")
    else:
        print("❌ Aborted by user.")

if __name__ == '__main__':
    main()
