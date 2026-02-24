# Part B (MongoDB) Photo Gallery App

This is the MongoDB-backed version of the photo gallery app for SE 4220 Project 2 Part B.

## What it does

- Reuses the same UI/templates from `../photogallery`
- Keeps the same routes (`/`, `/login`, `/register`, `/add`, `/search`, `/myphotos`)
- Replaces DynamoDB with MongoDB (`pymongo`)
- Still uploads images to S3 (same as Part A)

## Install dependencies

From the project root (`422hw2`):

```powershell
pip install flask pymongo boto3 python-dotenv exifread
```

## Environment variables

Create a `.env` file in one of these locations (any one works):

- `422hw2/mongodb/.env`
- `422hw2/.env`
- `422hw2/photogallery/.env`

Required values:

```env
SECRET_KEY=change-me

AWS_KEY=...
AWS_SECRET=...
BUCKET_NAME=...
AWS_REGION=us-east-2

MONGODB_URI=mongodb://localhost:27017
MONGO_DB_NAME=PhotoGalleryDB
MONGO_PHOTOS_COLLECTION=PhotoGallery
MONGO_USERS_COLLECTION=PhotoGalleryUsers
```

## Run (local)

From `422hw2`:

```powershell
python mongodb\app_mongo.py
```

Then open:

- `http://localhost:5002`
- Health check: `http://localhost:5002/healthz`

## Notes for deliverables

- You need screenshots for login, uploads, searches, and downloads using this MongoDB version (Part B).
- Part C requires migration proof from DynamoDB to MongoDB (separate from this app file).
