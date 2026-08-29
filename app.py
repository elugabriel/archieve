from flask import Flask, render_template, request, jsonify, session, send_file
from flask_login import LoginManager, login_required, current_user
from werkzeug.utils import secure_filename
import os
import re
from datetime import datetime
import uuid
from PIL import Image
from google import genai

from config import Config
from database import db, User, Folder, File
from auth import auth_bp, bcrypt

app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
bcrypt.init_app(app)

# Gemini client for AI image generation. Left as None (feature disabled)
# if GEMINI_API_KEY isn't set, rather than crashing the app on startup.
gemini_client = genai.Client(api_key=app.config['GEMINI_API_KEY']) if app.config['GEMINI_API_KEY'] else None

# Flask-Login setup
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Register blueprints
app.register_blueprint(auth_bp, url_prefix='/auth')

# Create tables
with app.app_context():
    db.create_all()
    # Create upload folder if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Raise existing accounts to the configured storage limit (leaves any
    # account that was manually given a larger allowance untouched).
    storage_limit = app.config['USER_STORAGE_LIMIT']
    updated = User.query.filter(User.storage_limit < storage_limit).update(
        {User.storage_limit: storage_limit}
    )
    if updated:
        db.session.commit()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_file_type(filename):
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in ['png', 'jpg', 'jpeg', 'gif']:
        return 'image'
    elif ext in ['mp4', 'avi', 'mov']:
        return 'video'
    elif ext in ['mp3', 'wav']:
        return 'audio'
    elif ext in ['pdf']:
        return 'pdf'
    elif ext in ['doc', 'docx']:
        return 'document'
    else:
        return 'other'

def create_thumbnail(file_path, thumbnail_path):
    try:
        with Image.open(file_path) as img:
            img.thumbnail((200, 200))
            img.save(thumbnail_path)
            return True
    except:
        return False

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/create')
@login_required
def create():
    return render_template('create.html', ai_enabled=bool(gemini_client))

@app.route('/api/folders')
@login_required
def get_folders():
    parent_id = request.args.get('parent_id', type=int)
    if parent_id:
        folders = Folder.query.filter_by(user_id=current_user.id, parent_id=parent_id).all()
    else:
        folders = Folder.query.filter_by(user_id=current_user.id, parent_id=None).all()
    
    return jsonify([{
        'id': f.id,
        'name': f.name,
        'type': 'folder',
        'created_at': f.created_at.isoformat(),
        'parent_id': f.parent_id
    } for f in folders])

@app.route('/api/files')
@login_required
def get_files():
    folder_id = request.args.get('folder_id', type=int)
    search_query = request.args.get('search', '')
    
    query = File.query.filter_by(user_id=current_user.id)
    
    if folder_id:
        query = query.filter_by(folder_id=folder_id)
    elif folder_id == 0:
        query = query.filter_by(folder_id=None)
    
    if search_query:
        query = query.filter(File.original_filename.contains(search_query))
    
    files = query.order_by(File.upload_date.desc()).all()
    
    return jsonify([{
        'id': f.id,
        'name': f.original_filename,
        'size': f.file_size,
        'type': f.file_type,
        'upload_date': f.upload_date.isoformat(),
        'url': f'/api/files/{f.id}/download',
        'thumbnail': f'/api/files/{f.id}/thumbnail' if f.file_type == 'image' else None
    } for f in files])

@app.route('/api/folder', methods=['POST'])
@login_required
def create_folder():
    data = request.json
    folder_name = data.get('name')
    parent_id = data.get('parent_id')
    
    if not folder_name:
        return jsonify({'error': 'Folder name required'}), 400
    
    # Check for duplicate folder name in same location
    existing = Folder.query.filter_by(
        user_id=current_user.id,
        name=folder_name,
        parent_id=parent_id
    ).first()
    
    if existing:
        return jsonify({'error': 'Folder already exists'}), 400
    
    folder = Folder(
        name=folder_name,
        user_id=current_user.id,
        parent_id=parent_id if parent_id != 0 else None
    )
    
    db.session.add(folder)
    db.session.commit()
    
    return jsonify({
        'id': folder.id,
        'name': folder.name,
        'message': 'Folder created successfully'
    }), 201

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_files():
    if 'files' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400
    
    files = request.files.getlist('files')
    folder_id = request.form.get('folder_id', type=int)
    
    if len(files) > app.config['MAX_FILES_PER_UPLOAD']:
        return jsonify({'error': f'Max {app.config["MAX_FILES_PER_UPLOAD"]} files per upload'}), 400
    
    uploaded_files = []
    errors = []
    total_size = 0
    
    for file in files:
        if file.filename == '':
            continue
        
        if not allowed_file(file.filename):
            errors.append(f'{file.filename}: File type not allowed')
            continue
        
        # Check storage limit
        total_size += len(file.read())
        file.seek(0)
        
        if current_user.storage_used + total_size > current_user.storage_limit:
            errors.append('Storage limit exceeded')
            break
        
        # Generate unique filename
        original_filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        # Save file
        file.save(file_path)
        
        # Create thumbnail for images
        if get_file_type(original_filename) == 'image':
            thumbnail_path = file_path.replace('.', '_thumb.')
            create_thumbnail(file_path, thumbnail_path)
        
        # Save to database
        db_file = File(
            filename=unique_filename,
            original_filename=original_filename,
            file_path=file_path,
            file_size=os.path.getsize(file_path),
            file_type=get_file_type(original_filename),
            user_id=current_user.id,
            folder_id=folder_id if folder_id != 0 else None
        )
        
        db.session.add(db_file)
        current_user.storage_used += db_file.file_size
        uploaded_files.append(original_filename)
    
    db.session.commit()
    
    return jsonify({
        'message': f'Successfully uploaded {len(uploaded_files)} files',
        'files': uploaded_files,
        'errors': errors
    })

@app.route('/api/files/<int:file_id>/download')
@login_required
def download_file(file_id):
    file = File.query.get_or_404(file_id)
    
    if file.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    file.downloads += 1
    db.session.commit()
    
    return send_file(file.file_path, download_name=file.original_filename)

@app.route('/api/files/<int:file_id>/thumbnail')
@login_required
def get_thumbnail(file_id):
    file = File.query.get_or_404(file_id)

    if file.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    thumbnail_path = file.file_path.replace('.', '_thumb.')
    if os.path.exists(thumbnail_path):
        return send_file(thumbnail_path)

    # Fall back to the full image if no thumbnail was generated
    return send_file(file.file_path)

@app.route('/api/generate-image', methods=['POST'])
@login_required
def generate_image():
    if not gemini_client:
        return jsonify({'error': 'Image generation is not configured. Set the GEMINI_API_KEY environment variable and restart the app.'}), 503

    data = request.json or {}
    prompt_text = (data.get('prompt') or '').strip()
    folder_id = data.get('folder_id')

    if not prompt_text:
        return jsonify({'error': 'Prompt is required'}), 400

    if len(prompt_text) > 2000:
        return jsonify({'error': 'Prompt is too long (max 2000 characters)'}), 400

    try:
        response = gemini_client.models.generate_content(
            model=app.config['GEMINI_IMAGE_MODEL'],
            contents=prompt_text,
        )
    except Exception as e:
        status = getattr(e, 'code', None) or getattr(e, 'status_code', None)
        message = str(e)

        if status == 429 or 'RESOURCE_EXHAUSTED' in message or '429' in message:
            retry_after = None
            match = re.search(r'retry in ([\d.]+)s', message, re.IGNORECASE)
            if match:
                retry_after = int(float(match.group(1))) + 1
            hint = (
                'Gemini quota exceeded for image generation. This model has no free '
                'tier — enable billing on the Google Cloud project for this API key '
                '(https://console.cloud.google.com/billing), then try again.'
            )
            if retry_after:
                hint = f'Rate limit hit. Retry in about {retry_after}s. ' + hint
            payload = {'error': hint}
            if retry_after:
                payload['retry_after'] = retry_after
            return jsonify(payload), 429

        if 'API key not valid' in message or 'API_KEY_INVALID' in message or status == 401:
            return jsonify({'error': 'The Gemini API key was rejected. Check GEMINI_API_KEY in your .env file.'}), 401

        return jsonify({'error': f'Image generation failed: {message}'}), 502

    # Pull the first inline image out of the response
    image_bytes = None
    for candidate in (response.candidates or []):
        for part in candidate.content.parts:
            inline_data = getattr(part, 'inline_data', None)
            if inline_data is not None and inline_data.data:
                image_bytes = inline_data.data
                break
        if image_bytes:
            break

    if not image_bytes:
        return jsonify({'error': 'The model did not return an image. Try rephrasing the prompt.'}), 502

    if current_user.storage_used + len(image_bytes) > current_user.storage_limit:
        return jsonify({'error': 'Storage limit exceeded'}), 400

    safe_prompt = secure_filename(prompt_text[:50]) or 'generated-image'
    original_filename = f'{safe_prompt}.png'
    unique_filename = f'{uuid.uuid4().hex}_{original_filename}'
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

    with open(file_path, 'wb') as f:
        f.write(image_bytes)

    thumbnail_path = file_path.replace('.', '_thumb.')
    create_thumbnail(file_path, thumbnail_path)

    db_file = File(
        filename=unique_filename,
        original_filename=original_filename,
        file_path=file_path,
        file_size=os.path.getsize(file_path),
        file_type='image',
        user_id=current_user.id,
        folder_id=folder_id if folder_id else None,
        source='generated',
        prompt=prompt_text
    )

    db.session.add(db_file)
    current_user.storage_used += db_file.file_size
    db.session.commit()

    return jsonify({
        'message': 'Image generated successfully',
        'file': db_file.to_dict()
    }), 201

@app.route('/api/files/<int:file_id>/delete', methods=['DELETE'])
@login_required
def delete_file(file_id):
    file = File.query.get_or_404(file_id)
    
    if file.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Delete physical file
    if os.path.exists(file.file_path):
        os.remove(file.file_path)
    
    # Update storage used
    current_user.storage_used -= file.file_size
    
    db.session.delete(file)
    db.session.commit()
    
    return jsonify({'message': 'File deleted successfully'})

@app.route('/api/folder/<int:folder_id>/delete', methods=['DELETE'])
@login_required
def delete_folder(folder_id):
    folder = Folder.query.get_or_404(folder_id)
    
    if folder.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Recursively delete all files in folder
    def delete_folder_contents(folder_obj):
        for file in folder_obj.files:
            if os.path.exists(file.file_path):
                os.remove(file.file_path)
            current_user.storage_used -= file.file_size
            db.session.delete(file)
        
        for subfolder in folder_obj.children:
            delete_folder_contents(subfolder)
            db.session.delete(subfolder)
    
    delete_folder_contents(folder)
    db.session.delete(folder)
    db.session.commit()
    
    return jsonify({'message': 'Folder deleted successfully'})

@app.route('/api/search')
@login_required
def search():
    query = request.args.get('q', '')
    
    if len(query) < 2:
        return jsonify({'files': [], 'folders': []})
    
    files = File.query.filter(
        File.user_id == current_user.id,
        File.original_filename.contains(query)
    ).limit(50).all()
    
    folders = Folder.query.filter(
        Folder.user_id == current_user.id,
        Folder.name.contains(query)
    ).limit(20).all()
    
    return jsonify({
        'files': [{
            'id': f.id,
            'name': f.original_filename,
            'type': f.file_type,
            'size': f.file_size,
            'folder_id': f.folder_id
        } for f in files],
        'folders': [{
            'id': f.id,
            'name': f.name,
            'parent_id': f.parent_id
        } for f in folders]
    })

@app.route('/api/user/storage')
@login_required
def get_storage_info():
    used_mb = current_user.storage_used / (1024 * 1024)
    limit_mb = current_user.storage_limit / (1024 * 1024)
    percentage = (current_user.storage_used / current_user.storage_limit) * 100
    
    return jsonify({
        'used': round(used_mb, 2),
        'limit': round(limit_mb, 2),
        'percentage': round(percentage, 1)
    })

@app.route('/api/folder/<int:folder_id>/move', methods=['POST'])
@login_required
def move_folder(folder_id):
    data = request.json
    new_parent_id = data.get('new_parent_id')
    
    folder = Folder.query.get_or_404(folder_id)
    
    if folder.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Prevent circular reference
    if new_parent_id:
        parent = Folder.query.get(new_parent_id)
        temp = parent
        while temp:
            if temp.id == folder.id:
                return jsonify({'error': 'Cannot move folder into itself'}), 400
            temp = temp.parent
    
    folder.parent_id = new_parent_id if new_parent_id != 0 else None
    db.session.commit()
    
    return jsonify({'message': 'Folder moved successfully'})

if __name__ == '__main__':
    # Debug is off unless FLASK_DEBUG is explicitly enabled. Production servers
    # (PythonAnywhere, gunicorn) import `app` via wsgi.py and never hit this.
    debug = os.environ.get('FLASK_DEBUG', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=debug, host='0.0.0.0', port=port)