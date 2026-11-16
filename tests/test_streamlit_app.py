"""The Streamlit shell (app/streamlit/app.py) starts without an error and embeds the built page.
Run: python tests/test_streamlit_app.py   (skipped with a message if Streamlit is not installed)"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _js


def test_app_runs_without_exception():
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError:
        return 'skip: Streamlit is not installed'
    at = AppTest.from_file(os.path.join(_js.ROOT, 'app', 'streamlit', 'app.py'), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


if __name__ == '__main__':
    _js.run_tests(globals())
