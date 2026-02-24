'''
MIT License

Copyright (c) 2019 Arshdeep Bahga and Vijay Madisetti

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

#!flask/bin/python
from flask import Flask, jsonify, abort, request, make_response, url_for
from flask import render_template, redirect, session, flash
import os
import io
import boto3    
import time
import datetime
from boto3.dynamodb.conditions import Key, Attr
import exifread
import json
import uuid
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__, template_folder="./", static_url_path="/assets", static_folder="assets")
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24).hex())

ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg'])
AWS_ACCESS_KEY=os.getenv("AWS_KEY")
AWS_SECRET_KEY=os.getenv("AWS_SECRET")
REGION="us-east-2"
BUCKET_NAME=os.getenv("BUCKET_NAME")

dynamodb = boto3.resource('dynamodb', aws_access_key_id=AWS_ACCESS_KEY,
                            aws_secret_access_key=AWS_SECRET_KEY,
                            region_name=REGION)

table = dynamodb.Table('PhotoGallery')
users_table = dynamodb.Table('PhotoGalleryUsers')


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.errorhandler(400)
def bad_request(error):
    return make_response(jsonify({'error': 'Bad request'}), 400)


@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)

def getExifData(file_stream):
    file_stream.seek(0)
    tags = exifread.process_file(file_stream)
    ExifData={}
    for tag in tags.keys():
        if tag not in ('JPEGThumbnail', 
                        'TIFFThumbnail', 
                        'Filename', 
                        'EXIF MakerNote'):            
            key="%s"%(tag)
            val="%s"%(tags[tag])
            ExifData[key]=val
    return ExifData

def s3uploading(filename, file_stream):
    s3 = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY,
                            aws_secret_access_key=AWS_SECRET_KEY)
                       
    bucket = BUCKET_NAME
    path_filename = "photos/" + filename
    print(path_filename)
    file_stream.seek(0)
    s3.upload_fileobj(file_stream, bucket, path_filename)  
    s3.put_object_acl(ACL='public-read', 
                Bucket=bucket, Key=path_filename)
    return "http://"+BUCKET_NAME+\
        ".s3.us-east-2.amazonaws.com/"+ path_filename  

@app.route('/', methods=['GET', 'POST'])
def home_page():
    # Get all public photos
    public_response = table.scan(
        FilterExpression=Attr('Public').eq('yes')
    )
    items = public_response['Items']

    print(items)
    return render_template('index.html', photos=items,
                           username=session.get('username'))

@app.route('/myphotos', methods=['GET'])
def my_photos():
    if 'username' not in session:
        flash('Please log in to view your photos')
        return redirect('/login')
    response = table.query(
        KeyConditionExpression=Key('UserID').eq(session['username'])
    )
    items = response['Items']
    return render_template('myphotos.html', photos=items,
                           username=session.get('username'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        # Check if user already exists
        response = users_table.get_item(Key={'Email': email})
        if 'Item' in response:
            flash('An account with this email already exists')
            return redirect('/register')
        users_table.put_item(Item={
            'Email': email,
            'PasswordHash': generate_password_hash(password)
        })
        session['username'] = email
        return redirect('/')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        response = users_table.get_item(Key={'Email': email})
        if 'Item' not in response or not check_password_hash(
                response['Item']['PasswordHash'], password):
            flash('Invalid email or password')
            return redirect('/login')
        session['username'] = email
        return redirect('/')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect('/')

@app.route('/add', methods=['GET', 'POST'])
def add_photo():
    if 'username' not in session:
        flash('Please log in to upload photos')
        return redirect('/login')
    if request.method == 'POST':    
        uploadedFileURL=''

        file = request.files['imagefile']
        title = request.form['title']
        tags = request.form['tags']
        description = request.form['description']
        public = 'yes' if request.form.get('public') else 'no'

        print(title,tags,description)
        if file and allowed_file(file.filename):
            filename = file.filename
            ExifData=getExifData(file)
            uploadedFileURL = s3uploading(filename, file)
            ts=time.time()
            timestamp = datetime.datetime.\
                        fromtimestamp(ts).\
                        strftime('%Y-%m-%d %H:%M:%S')

            table.put_item(
            Item={
                    "UserID": session['username'],
                    "PhotoID": str(int(ts*1000)),
                    "CreationTime": timestamp,
                    "Title": title,
                    "Description": description,
                    "Tags": tags,
                    "URL": uploadedFileURL,
                    "Public": public,
                    "ExifData": json.dumps(ExifData)
                }
            )

        return redirect('/')
    else:
        return render_template('form.html')

@app.route('/<int:photoID>', methods=['GET'])
def view_photo(photoID):
    response = table.scan(
        FilterExpression=Attr('PhotoID').eq(str(photoID))
    )

    items = response['Items']
    print(items[0])
    tags=items[0]['Tags'].split(',')
    exifdata=json.loads(items[0]['ExifData'])

    return render_template('photodetail.html', 
            photo=items[0], tags=tags, exifdata=exifdata)

@app.route('/search', methods=['GET'])
def search_page():
    query = request.args.get('query', None)    
    
    response = table.scan(
        FilterExpression=Attr('Title').contains(str(query)) | 
                        Attr('Description').contains(str(query)) | 
                        Attr('Tags').contains(str(query))
    )
    items = response['Items']
    return render_template('search.html', 
            photos=items, searchquery=query)

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5001)
