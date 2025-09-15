#!/usr/bin/env python3
"""
Build script for creating executables from Python scripts using PyInstaller
Usage: python build_exe.py [script_name.py]
"""

import os
import sys
import subprocess
import argparse

def build_executable(script_path, output_dir="dist", icon_path=None, one_file=True):
    """
    Build an executable from a Python script using PyInstaller
    
    Args:
        script_path: Path to the Python script to build
        output_dir: Directory to output the executable (default: dist)
        icon_path: Optional path to an icon file (.ico)
        one_file: If True, creates a single executable file
    """
    
    if not os.path.exists(script_path):
        print(f"Error: Script '{script_path}' not found!")
        return False
    
    # Build PyInstaller command
    cmd = ["pyinstaller"]
    
    if one_file:
        cmd.append("--onefile")
    
    # Add console mode (keeps console window open)
    cmd.append("--console")
    
    # Set output directory
    cmd.extend(["--distpath", output_dir])
    
    # Add icon if provided
    if icon_path and os.path.exists(icon_path):
        cmd.extend(["--icon", icon_path])
    
    # Clean previous builds
    cmd.append("--clean")
    
    # Add the script to build
    cmd.append(script_path)
    
    print(f"Building executable for: {script_path}")
    print(f"Command: {' '.join(cmd)}")
    print("-" * 50)
    
    try:
        # Run PyInstaller
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("Build successful!")
        print(f"Executable created in: {output_dir}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Build failed with error code {e.returncode}")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        return False
    except FileNotFoundError:
        print("Error: PyInstaller not found. Please install it first:")
        print("pip install pyinstaller")
        return False

def main():
    parser = argparse.ArgumentParser(description="Build executables from Python scripts")
    parser.add_argument("script", nargs="?", help="Python script to build")
    parser.add_argument("--output", "-o", default="dist", help="Output directory (default: dist)")
    parser.add_argument("--icon", "-i", help="Icon file (.ico)")
    parser.add_argument("--no-onefile", action="store_true", help="Create folder instead of single file")
    
    args = parser.parse_args()
    
    # If no script provided, show available Python scripts
    if not args.script:
        print("Available Python scripts in the project:")
        print("-" * 40)
        
        python_scripts = []
        for root, dirs, files in os.walk("."):
            # Skip __pycache__ and other hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            
            for file in files:
                if file.endswith('.py') and not file.startswith('.'):
                    script_path = os.path.join(root, file)
                    python_scripts.append(script_path)
        
        for i, script in enumerate(python_scripts, 1):
            print(f"{i:2d}. {script}")
        
        if python_scripts:
            print("\nUsage examples:")
            print(f"  python build_exe.py \"{python_scripts[0]}\"")
            print("  python build_exe.py script.py --icon myicon.ico")
            print("  python build_exe.py script.py --no-onefile")
        else:
            print("No Python scripts found in the current directory.")
        
        return
    
    # Build the executable
    success = build_executable(
        script_path=args.script,
        output_dir=args.output,
        icon_path=args.icon,
        one_file=not args.no_onefile
    )
    
    if success:
        print(f"\n✓ Successfully built executable for {args.script}")
    else:
        print(f"\n✗ Failed to build executable for {args.script}")
        sys.exit(1)

if __name__ == "__main__":
    main()
