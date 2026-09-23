import http.client
from threading import Thread

import pytest


@pytest.mark.parametrize("url,platform", [
    ("https://meet.google.com/abc-defg-hij", "Google Meet"),
    ("https://company.zoom.us/j/123456789", "Zoom"),
    ("https://teams.microsoft.com/l/meetup-join/abc", "Teams"),
])
def test_platform_links(url, platform):
    from services.capture import meeting_platform
    assert meeting_platform(url) == platform


@pytest.mark.parametrize("url", ["https://zoom.us.evil.test/j/1", "http://meet.google.com/abc",
                                "https://user@zoom.us/j/1", "file:///etc/passwd", "https://127.0.0.1/"])
def test_untrusted_links_rejected(url):
    from services.capture import meeting_platform
    with pytest.raises(ValueError):
        meeting_platform(url)


def test_capture_requires_token_and_consent_and_saves_generated_path(tmp_path):
    from services.capture import create_server
    server = create_server(tmp_path, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_port
        def post(headers):
            connection = http.client.HTTPConnection("127.0.0.1", port)
            connection.request("POST", "/upload", body=b"webm-audio", headers=headers)
            response = connection.getresponse()
            body = response.read()
            connection.close()
            return response.status, body
        assert post({})[0] == 403
        headers = {"X-Alem-Token": server.token, "Origin": f"http://127.0.0.1:{port}",
                   "Content-Type": "audio/webm", "X-Recording-Consent": "yes"}
        assert post(headers)[0] == 201
        assert len(list(tmp_path.glob("*.webm"))) == 1
        headers["Origin"] = "https://evil.test"
        assert post(headers)[0] == 403
    finally:
        server.shutdown()
        server.server_close()
