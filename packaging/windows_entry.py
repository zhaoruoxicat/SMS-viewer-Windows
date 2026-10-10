"""Windows executable entry point; the application is shared with Ubuntu."""
from sms_client.__main__ import main

if __name__ == '__main__':
    raise SystemExit(main())
