import os
import sys

# The packaging check needs a real Qt application but no interactive window.
if '--self-test' in sys.argv:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from modelcheck.app import main

if __name__ == '__main__':
    raise SystemExit(main())
