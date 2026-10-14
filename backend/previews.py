"""Stable identifiers shared by the preview API and sample builder."""
import hashlib
from .catalog import MODELS, VOICES

PREVIEW_TEXT = '안녕하세요. 오늘도 만나서 반갑습니다. 지금부터 새로운 이야기를 들려드릴게요.'
PREVIEW_VERSION = 'v1'

def preview_key(model, voice, emotion):
    value = '|'.join([PREVIEW_VERSION, model, voice, emotion])
    return hashlib.sha256(value.encode()).hexdigest()[:24]

def combinations():
    for model in ['qwen', 'fish', 'higgs']:
        for voice in VOICES:
            for emotion in MODELS[model]['emotions']:
                yield model, voice['id'], emotion['id']
