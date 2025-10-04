from app.browser import PageSnapshot
from app.extract import extract_metadata


def test_extract_metadata_basic():
    html = """
    <html>
      <head>
        <title>Example Page</title>
        <meta name='description' content='A sample description'>
      </head>
      <body>
        <h1>Welcome</h1>
        <p>This is an example page.</p>
        <script>var x = 1;</script>
      </body>
    </html>
    """
    snapshot = PageSnapshot(
        url="https://example.com",
        final_url="https://example.com",
        title="Example Page",
        status=200,
        content=html,
        total_height=1000,
    )
    metadata = extract_metadata(snapshot)
    assert metadata["meta_description"] == "A sample description"
    assert metadata["h1"] == "Welcome"
    assert metadata["word_count"] >= 5
    assert metadata["final_url"] == "https://example.com"
