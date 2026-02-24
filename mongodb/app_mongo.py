"""
MongoDB-backed version of the photo gallery app (Project 2 - Part B).

Reuses the existing templates/assets in ../photogallery so the UI stays the same
while swapping DynamoDB for MongoDB.
"""

from pathlib import Path
import datetime
import json
import os
import time
import uuid

import boto3
import exifread
from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, redirect, render_template, request
from flask import session, flash
from pymongo import ASCENDING, DESCENDING, MongoClient
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
PHOTO_APP_DIR = PROJECT_ROOT / "photogallery"

# Load env from common locations so this can run from either /mongodb or project root.
for env_path in (
    BASE_DIR / ".env",
    PROJECT_ROOT / ".env",
    PHOTO_APP_DIR / ".env",
):
    if env_path.exists():
        load_dotenv(env_path)


app = Flask(
    __name__,
    template_folder=str(PHOTO_APP_DIR),
    static_url_path="/assets",
    static_folder=str(PHOTO_APP_DIR / "assets"),
)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24).hex())

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

AWS_ACCESS_KEY = os.getenv("AWS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET")
AWS_REGION = os.getenv("AWS_REGION", "us-east-2")
BUCKET_NAME = os.getenv("BUCKET_NAME")

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "PhotoGalleryDB")
MONGO_PHOTOS_COLLECTION = os.getenv("MONGO_PHOTOS_COLLECTION", "PhotoGallery")
MONGO_USERS_COLLECTION = os.getenv("MONGO_USERS_COLLECTION", "PhotoGalleryUsers")


mongo_client = MongoClient(MONGODB_URI)
mongo_db = mongo_client[MONGO_DB_NAME]
photos_collection = mongo_db[MONGO_PHOTOS_COLLECTION]
users_collection = mongo_db[MONGO_USERS_COLLECTION]

# Best-effort indexes to keep lookups fast and enforce unique users.
users_collection.create_index([("Email", ASCENDING)], unique=True)
photos_collection.create_index([("UserID", ASCENDING), ("PhotoID", ASCENDING)], unique=True)
photos_collection.create_index([("Public", ASCENDING), ("CreationTime", DESCENDING)])


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def serialize_photo(doc):
    """Drop Mongo's internal id so templates receive the same shape as Part A."""
    if not doc:
        return doc
    clean = dict(doc)
    clean.pop("_id", None)
    return clean


def get_exif_data(file_stream):
    file_stream.seek(0)
    tags = exifread.process_file(file_stream)
    exif_data = {}
    for tag in tags.keys():
        if tag not in ("JPEGThumbnail", "TIFFThumbnail", "Filename", "EXIF MakerNote"):
            exif_data[str(tag)] = str(tags[tag])
    return exif_data


def s3_upload(filename, file_stream):
    if not (AWS_ACCESS_KEY and AWS_SECRET_KEY and BUCKET_NAME):
        raise RuntimeError("Missing AWS_KEY/AWS_SECRET/BUCKET_NAME environment variables")

    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION,
    )
    path_filename = f"photos/{filename}"
    file_stream.seek(0)
    s3.upload_fileobj(file_stream, BUCKET_NAME, path_filename)
    s3.put_object_acl(ACL="public-read", Bucket=BUCKET_NAME, Key=path_filename)
    return f"http://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{path_filename}"


def public_photos():
    return [serialize_photo(p) for p in photos_collection.find({"Public": "yes"}).sort("CreationTime", DESCENDING)]


def user_photos(user_email):
    return [serialize_photo(p) for p in photos_collection.find({"UserID": user_email}).sort("CreationTime", DESCENDING)]


def filter_photos(items, query):
    q = (query or "").lower()
    if not q:
        return items
    return [
        item
        for item in items
        if q in item.get("Title", "").lower()
        or q in item.get("Description", "").lower()
        or q in item.get("Tags", "").lower()
    ]


@app.errorhandler(400)
def bad_request(_error):
    return make_response(jsonify({"error": "Bad request"}), 400)


@app.errorhandler(404)
def not_found(_error):
    return make_response(jsonify({"error": "Not found"}), 404)


@app.route("/", methods=["GET", "POST"])
def home_page():
    items = public_photos()
    return render_template("index.html", photos=items, username=session.get("username"))


@app.route("/myphotos", methods=["GET"])
def my_photos():
    if "username" not in session:
        flash("Please log in to view your photos")
        return redirect("/login")
    items = user_photos(session["username"])
    return render_template("myphotos.html", photos=items, username=session.get("username"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not email or not password:
            flash("Email and password are required")
            return redirect("/register")

        existing = users_collection.find_one({"Email": email}, {"_id": 1})
        if existing:
            flash("An account with this email already exists")
            return redirect("/register")

        users_collection.insert_one(
            {
                "Email": email,
                "PasswordHash": generate_password_hash(password),
                "CreatedAt": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
        )
        session["username"] = email
        return redirect("/")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = users_collection.find_one({"Email": email})

        if not user or not check_password_hash(user.get("PasswordHash", ""), password):
            flash("Invalid email or password")
            return redirect("/login")

        session["username"] = email
        return redirect("/")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect("/")


@app.route("/add", methods=["GET", "POST"])
def add_photo():
    if "username" not in session:
        flash("Please log in to upload photos")
        return redirect("/login")

    if request.method == "GET":
        return render_template("form.html")

    file = request.files.get("imagefile")
    title = request.form.get("title", "").strip()
    tags = request.form.get("tags", "").strip()
    description = request.form.get("description", "").strip()
    public = "yes" if request.form.get("public") else "no"

    if not file or not file.filename:
        flash("Please choose an image file")
        return redirect("/add")
    if not allowed_file(file.filename):
        flash("Only .png, .jpg, and .jpeg files are allowed")
        return redirect("/add")

    exif_data = get_exif_data(file)
    uploaded_url = s3_upload(file.filename, file)

    ts = time.time()
    photo_id = str(int(ts * 1000))
    timestamp = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

    doc = {
        "UserID": session["username"],
        "PhotoID": photo_id,
        "CreationTime": timestamp,
        "Title": title,
        "Description": description,
        "Tags": tags,
        "URL": uploaded_url,
        "Public": public,
        "ExifData": json.dumps(exif_data),
    }

    try:
        photos_collection.insert_one(doc)
    except Exception:
        # Rare timestamp collision; retry once with a unique suffix while keeping route compatibility numeric.
        doc["PhotoID"] = str(int(ts * 1000)) + str(uuid.uuid4().int % 1000)
        photos_collection.insert_one(doc)

    return redirect("/")


@app.route("/<photo_id>", methods=["GET"])
def view_photo(photo_id):
    photo = photos_collection.find_one({"PhotoID": str(photo_id)})
    if not photo:
        return not_found(None)

    item = serialize_photo(photo)
    tags = item.get("Tags", "").split(",") if item.get("Tags") else []
    exifdata = json.loads(item.get("ExifData", "{}"))

    return render_template("photodetail.html", photo=item, tags=tags, exifdata=exifdata)


@app.route("/search", methods=["GET"])
def search_page():
    query = request.args.get("query", None)
    items = filter_photos(public_photos(), query)
    return render_template("search.html", photos=items, searchquery=query)


@app.route("/mysearch", methods=["GET"])
def my_search_page():
    if "username" not in session:
        return redirect("/login")

    query = request.args.get("query", None)
    items = filter_photos(user_photos(session["username"]), query)
    return render_template("myphotos.html", photos=items, username=session.get("username"))


@app.route("/healthz", methods=["GET"])
def healthz():
    try:
        mongo_client.admin.command("ping")
        return jsonify({"status": "ok", "mongo": "reachable"})
    except Exception as exc:
        return jsonify({"status": "error", "mongo": str(exc)}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", "5002")))
