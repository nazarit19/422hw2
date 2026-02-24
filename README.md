# 422project2 **


to run: 

1. create python environment and start it: 
- python3 -m venv venv 
- source venv/bin/activate

2. install dependencies with pip: 
* flask
* boto3
* python-dotenv
* exifread

3. create .env file in photogallery with AWS_KEY, AWS_SECRET, and the BUCKET_NAME environment variables

4. run the app:
- flask run

5. to upload images, they need to be in the photogallery/media/ folder
