"""Old command, kept so that existing instructions still work: the page is now built by build_page.py.
Usage (from the repository root): python app/demo/embed_day_data.py   (same as: python -I app/demo/build_page.py)"""
import os, runpy, sys
sys.argv = [sys.argv[0]]                 # the old arguments (page and data file) are fixed paths in build_page.py
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_page.py'), run_name='__main__')
