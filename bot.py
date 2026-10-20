"""TikTok verification and policy pages only. No Telegram functionality."""
import os
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Delgraphyha Shorts Factory web pages", 200

@app.route("/terms")
def terms():
    return """
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Delgraphyha Shorts Factory - Terms of Service</title>
    </head>
    <body style="font-family:Arial,sans-serif;max-width:800px;margin:40px auto;line-height:1.6;padding:0 20px;">
        <h1>Terms of Service</h1>
        <p><strong>Last updated:</strong> October 19, 2026</p>
        <p>Delgraphyha Shorts Factory is a private content management and publishing tool operated by Delgraphyha.</p>
        <p>The service is used by the account owner to prepare, upload and publish original short-form video content to connected social media platforms, including TikTok.</p>
        <h2>Use of the service</h2>
        <p>The service is intended for private use by the owner of Delgraphyha. It is not offered as a public upload or publishing service for third parties.</p>
        <h2>Content</h2>
        <p>Only content owned by, created by, or authorized for use by Delgraphyha may be published through the service.</p>
        <h2>Third-party platforms</h2>
        <p>Use of TikTok and other connected platforms is also subject to the respective platform terms and policies.</p>
        <h2>Contact</h2>
        <p>Delgraphyha</p>
    </body>
    </html>
    """, 200, {"Content-Type": "text/html; charset=utf-8"}

@app.route("/privacy")
def privacy():
    return """
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Delgraphyha Shorts Factory - Privacy Policy</title>
    </head>
    <body style="font-family:Arial,sans-serif;max-width:800px;margin:40px auto;line-height:1.6;padding:0 20px;">
        <h1>Privacy Policy</h1>
        <p><strong>Last updated:</strong> October 19, 2026</p>
        <p>Delgraphyha Shorts Factory is a private content publishing tool operated by Delgraphyha.</p>
        <h2>Data processed</h2>
        <p>The service may process authentication tokens, account identifiers, publishing status information and video metadata required to connect to supported social media platforms.</p>
        <h2>Purpose</h2>
        <p>This information is used only to authenticate the account owner and upload or publish original Delgraphyha content.</p>
        <h2>Data sharing</h2>
        <p>Personal data is not sold. Data is only transmitted to connected platforms when required to provide the publishing functionality.</p>
        <h2>Data retention</h2>
        <p>Authentication information and publishing records are retained only for as long as required to operate and secure the service.</p>
        <h2>Contact</h2>
        <p>Delgraphyha</p>
    </body>
    </html>
    """, 200, {"Content-Type": "text/html; charset=utf-8"}

@app.route("/tiktok5DvEZcp4OV0sXiL0fS0fH36XI5V5ogyx.txt")
def tiktok_site_verification():
    return "tiktok-developers-site-verification=5DvEZcp4OV0sXiL0fS0fH36XI5V5ogyx", 200, {"Content-Type": "text/plain; charset=utf-8"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
