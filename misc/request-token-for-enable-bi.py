import jwt
import time

METABASE_SITE_URL = "http://{{CHANGE_WITH_URL_FROM_SERVICE}}"
METABASE_SECRET_KEY = "{{CHANGE_WITH_SECRET_FROM_SERVICE}}"

payload = {
    "resource": {"dashboard": 2},
    "params": {
        "first_seen": "{{START_DATE}}~{{END_DATE}}",
        "author": [
            "{{USERS}}",
        ],
    },
    "exp": round(time.time()) + (60 * 60 * 24 * 365),  # 1 year expiration
}
token = jwt.encode(payload, METABASE_SECRET_KEY, algorithm="HS256")

iframeUrl = (
    METABASE_SITE_URL
    + "/embed/dashboard/"
    + token
    + "#theme=night&bordered=true&titled=false"
)
print(iframeUrl)
print("Copy paste the token")
print(token)
