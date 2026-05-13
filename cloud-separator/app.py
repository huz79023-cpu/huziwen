"""
普音 — 云端 AI 人声分离服务
阿里云函数计算 FC (GPU) 部署
接收音频 → Demucs v4 分离 → 返回各音轨 ZIP
"""

import io
import os
import zipfile
import tempfile
import torch
import torchaudio
from flask import Flask, request, send_file
from demucs import pretrained
from demucs.apply import apply_model

app = Flask(__name__)

model = None          # 模型单例（冷启动后常驻）
model_sr = None       # 模型期望采样率
model_ch = None       # 模型声道数

SOURCE_NAMES = ['drums', 'bass', 'other', 'vocals']


def _load_model():
    """懒加载 Demucs 模型（第一次请求时加载，后续复用）"""
    global model, model_sr, model_ch
    if model is not None:
        return

    print("[Demucs] 正在加载模型 htdemucs（首次调用较慢，约 5-10 秒）...")
    model = pretrained.get_model('htdemucs')
    model.cuda()
    model.eval()
    model_sr = model.samplerate
    model_ch = model.audio_channels
    print(f"[Demucs] 模型加载完成。采样率={model_sr}，声道数={model_ch}")


def _resample(wav, orig_sr):
    """重采样到模型采样率"""
    if orig_sr == model_sr:
        return wav
    return torchaudio.functional.resample(wav, orig_sr, model_sr)


def _separate(audio_path):
    """
    对音频文件执行 Demucs 分离
    返回 dict: {stem_name: tensor(channels, samples)}
    """
    _load_model()

    # 读取音频
    wav, sr = torchaudio.load(audio_path)
    print(f"[Demucs] 音频已加载：{wav.shape}，采样率={sr}")

    # 转成单声道/重采样到模型期望格式
    if wav.shape[0] > model_ch:
        # 多声道降混为 stereo
        wav = wav[:model_ch]
    wav = _resample(wav, sr)

    # 转 GPU
    wav = wav.cuda()

    # 标准化
    ref = wav.mean(0)
    wav = (wav - ref.mean()) / (ref.std() + 1e-8)

    # 推理（batch_size=1）
    with torch.no_grad():
        sources = apply_model(model, wav[None], device='cuda', shifts=1, split=True)[0]

    # 还原增益
    sources = sources * ref.std() + ref.mean()

    # 结果 dict
    stems = {}
    for i, name in enumerate(SOURCE_NAMES):
        stems[name] = sources[i].cpu()

    return stems


# ─── 路由 ───────────────────────────────────────────────

@app.route('/ping', methods=['GET'])
def ping():
    """健康检查"""
    return {'status': 'ok'}


@app.route('/invoke', methods=['POST'])
def invoke():
    """
    分离音频
    请求：multipart/form-data，字段名 'audio'
    返回：ZIP 文件（内含 drums.wav / bass.wav / other.wav / vocals.wav）
    """
    req_id = request.headers.get('x-fc-request-id', 'N/A')
    print(f"\n[Request] {req_id} — 收到分离请求")

    # 检查文件
    file = request.files.get('audio')
    if not file:
        return {'error': '缺少 audio 字段'}, 400

    # 保存到临时文件
    tmp_audio = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    try:
        file.save(tmp_audio.name)
        tmp_audio.close()

        # 分离
        stems = _separate(tmp_audio.name)
        print(f"[Demucs] 分离完成：{list(stems.keys())}")

        # 打包 ZIP
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for name, tensor in stems.items():
                stem_tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
                try:
                    torchaudio.save(stem_tmp.name, tensor, model_sr)
                    zf.write(stem_tmp.name, f'{name}.wav')
                finally:
                    os.unlink(stem_tmp.name)

        buf.seek(0)
        print(f"[Request] {req_id} — 返回 ZIP (共 {len(stems)} 个音轨)")
        return send_file(
            buf,
            mimetype='application/zip',
            as_attachment=True,
            download_name='separated.zip'
        )

    finally:
        if os.path.exists(tmp_audio.name):
            os.unlink(tmp_audio.name)


# ─── 启动 ───────────────────────────────────────────────

if __name__ == '__main__':
    print("[Server] 普音云端分离服务启动中...")
    # 阿里云 FC 需要监听 0.0.0.0:9000
    app.run(host='0.0.0.0', port=9000, debug=False)
