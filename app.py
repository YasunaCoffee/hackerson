from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
import os
import requests
import json
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    # Pillowがインストールされていない場合の代替
    print("Pillowライブラリがインストールされていません。")
    print("pip install Pillow を実行してください。")
    exit(1)
import imageio
import io
import zipfile
import tempfile
import uuid
from datetime import datetime

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB制限

# アップロードフォルダ作成
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# VOICEVOX設定
VOICEVOX_URL = "http://localhost:50021"
DEFAULT_SPEAKER = 1  # 四国めたん

# プリセットテキスト
PRESET_TEXTS = [
    "わーい！",
    "やったー！",
    "えー！",
    "すごい！",
    "かわいい！",
    "やばい！",
    "まじで！",
    "うわー！"
]

@app.route('/')
def index():
    return render_template('index.html', preset_texts=PRESET_TEXTS)

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'image' not in request.files:
            return jsonify({'error': '画像が選択されていません'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'ファイルが選択されていません'}), 400
        
        # ファイル形式チェック
        if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            return jsonify({'error': 'PNGまたはJPGファイルを選択してください'}), 400
        
        # テキスト取得
        text = request.form.get('text', 'わーい！')
        if not text.strip():
            return jsonify({'error': 'テキストを入力してください'}), 400
        
        # ファイル保存
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}_{filename}")
        file.save(filepath)
        
        # 画像処理
        processed_image = process_image(filepath, text)
        
        # 音声生成
        audio_data = generate_voice(text)
        
        # アニメーションGIF作成
        gif_data = create_animated_gif(processed_image, text)
        
        # ZIPファイル作成
        zip_data = create_zip_package(gif_data, audio_data, text)
        
        # 一時ファイル削除
        os.remove(filepath)
        
        return send_file(
            io.BytesIO(zip_data),
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'stamp_{text[:10]}.zip'
        )
        
    except Exception as e:
        return jsonify({'error': f'エラーが発生しました: {str(e)}'}), 500

def process_image(image_path, text):
    """画像を処理してLINEスタンプサイズにリサイズ"""
    with Image.open(image_path) as img:
        # RGBAに変換
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # 正方形にリサイズ（240x240px）
        img = img.resize((240, 240), Image.Resampling.LANCZOS)
        
        return img

def generate_voice(text):
    """VOICEVOXで音声を生成"""
    try:
        # 音声合成リクエスト
        synthesis_params = {
            "text": text,
            "speaker": DEFAULT_SPEAKER,
            "speedScale": 1.0,
            "volumeScale": 1.0,
            "intonationScale": 1.0,
            "prePhonemeLength": 0.1,
            "postPhonemeLength": 0.1
        }
        
        response = requests.post(
            f"{VOICEVOX_URL}/audio_query",
            params={"text": text, "speaker": DEFAULT_SPEAKER},
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code != 200:
            raise Exception("音声合成クエリの作成に失敗しました")
        
        audio_query = response.json()
        
        # 音声合成
        response = requests.post(
            f"{VOICEVOX_URL}/synthesis",
            params={"speaker": DEFAULT_SPEAKER},
            data=json.dumps(audio_query),
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code != 200:
            raise Exception("音声合成に失敗しました")
        
        return response.content
        
    except requests.exceptions.ConnectionError:
        # VOICEVOXが起動していない場合のダミー音声
        return create_dummy_audio()

def create_dummy_audio():
    """ダミー音声ファイル作成（VOICEVOX未起動時）"""
    # 1秒の無音WAVファイル
    import wave
    import struct
    
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(44100)
        
        # 1秒の無音データ
        for _ in range(44100):
            wav_file.writeframes(struct.pack('<h', 0))
    
    return buffer.getvalue()

def create_animated_gif(base_image, text):
    """画像と文字のアニメーションGIF作成"""
    frames = []
    
    # フォント設定（デフォルトフォント使用）
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        font = ImageFont.load_default()
    
    # アニメーションフレーム作成
    for i in range(10):
        # 画像をコピー
        frame = base_image.copy()
        draw = ImageDraw.Draw(frame)
        
        # テキストの位置計算
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (240 - text_width) // 2
        y = 200 - text_height  # 下部に配置
        
        # フェードイン効果
        alpha = int(255 * (i + 1) / 10)
        
        # テキスト描画（白文字+黒縁取り）
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, alpha))
        
        draw.text((x, y), text, font=font, fill=(255, 255, 255, alpha))
        
        frames.append(frame)
    
    # GIF作成
    buffer = io.BytesIO()
    imageio.mimsave(buffer, frames, format='GIF', duration=0.1, loop=0)
    return buffer.getvalue()

def create_zip_package(gif_data, audio_data, text):
    """ZIPパッケージ作成"""
    buffer = io.BytesIO()
    
    with zipfile.ZipFile(buffer, 'w') as zip_file:
        # アニメーションGIF
        zip_file.writestr('stamp_animated.gif', gif_data)
        
        # 音声ファイル
        zip_file.writestr('stamp_audio.wav', audio_data)
        
        # 使用方法説明
        usage_text = f"""LINEスタンプ音声セット使用方法

1. stamp_animated.gif をLINEスタンプとして追加
2. stamp_audio.wav を音声ファイルとして保存
3. スタンプ送信時に音声も同時再生

テキスト: {text}
生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

※ 音声付きGIFは一部のブラウザ/アプリでのみ再生可能です
※ 音声ファイルは別途再生してください
"""
        zip_file.writestr('README.txt', usage_text)
    
    return buffer.getvalue()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 