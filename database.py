from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import os

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    storage_used = db.Column(db.BigInteger, default=0)  # in bytes
    storage_limit = db.Column(db.BigInteger, default=3 * 1024 * 1024 * 1024)  # 3 GB default
    
    files = db.relationship('File', backref='owner', lazy=True)
    folders = db.relationship('Folder', backref='owner', lazy=True)

class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('folder.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    children = db.relationship('Folder', backref=db.backref('parent', remote_side=[id]))
    files = db.relationship('File', backref='folder', lazy=True)

class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(200), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    file_type = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey('folder.id'), nullable=True)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    downloads = db.Column(db.Integer, default=0)
    source = db.Column(db.String(20), default='upload')  # 'upload' or 'generated'
    prompt = db.Column(db.Text, nullable=True)  # prompt used, if AI-generated

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.original_filename,
            'size': self.file_size,
            'type': self.file_type,
            'upload_date': self.upload_date.isoformat(),
            'downloads': self.downloads,
            'source': self.source,
            'prompt': self.prompt,
            'url': f'/api/files/{self.id}/download',
            'thumbnail': f'/api/files/{self.id}/thumbnail' if self.file_type == 'image' else None
        }