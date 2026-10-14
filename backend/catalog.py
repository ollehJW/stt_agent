VOICES = [
    {'id': 'Sohee', 'label': 'Sohee', 'gender': '여성', 'native': '한국어', 'description': '따뜻하고 풍부한 표현'},
    {'id': 'Ryan', 'label': 'Ryan', 'gender': '남성', 'native': '영어', 'description': '역동적이고 리듬감 있는 목소리'},
    {'id': 'Aiden', 'label': 'Aiden', 'gender': '남성', 'native': '영어', 'description': '밝고 또렷한 목소리'},
    {'id': 'Serena', 'label': 'Serena', 'gender': '여성', 'native': '중국어', 'description': '부드럽고 따뜻한 목소리'},
    {'id': 'Vivian', 'label': 'Vivian', 'gender': '여성', 'native': '중국어', 'description': '밝고 선명한 목소리'},
    {'id': 'Uncle_Fu', 'label': 'Uncle Fu', 'gender': '남성', 'native': '중국어', 'description': '낮고 중후한 목소리'},
    {'id': 'Dylan', 'label': 'Dylan', 'gender': '남성', 'native': '중국어', 'description': '자연스럽고 명료한 목소리'},
    {'id': 'Eric', 'label': 'Eric', 'gender': '남성', 'native': '중국어', 'description': '활기차고 약간 허스키한 목소리'},
    {'id': 'Ono_Anna', 'label': 'Ono Anna', 'gender': '여성', 'native': '일본어', 'description': '발랄하고 가벼운 목소리'},
]

def options(items):
    return [{'id': key, 'label': label} for key, label in items]

QWEN_EMOTIONS = options([
    ('neutral', '중립'), ('calm', '차분함'), ('warm', '따뜻함'), ('happy', '기쁨'),
    ('excited', '신남'), ('sad', '슬픔'), ('angry', '분노'), ('surprised', '놀람'),
    ('confident', '자신감'), ('empathetic', '공감'), ('whisper', '속삭임'),
])
QWEN_PROMPTS = {
    'neutral': 'Speak naturally and clearly in a neutral tone.',
    'calm': 'Speak calmly and gently with a composed, clear presentation tone.',
    'warm': 'Speak warmly with a friendly and reassuring tone.',
    'happy': 'Speak happily with a cheerful, bright tone.',
    'excited': 'Speak with excitement, enthusiasm and energetic expression.',
    'sad': 'Speak with sadness in a soft, subdued voice.',
    'angry': 'Speak with an angry and forceful tone.',
    'surprised': 'Speak with surprise and amazement.',
    'confident': 'Speak with confidence and a steady, assured tone.',
    'empathetic': 'Speak with empathy and a comforting tone.',
    'whisper': 'Speak in a quiet whisper.',
}
HIGGS_EMOTIONS = options([
    ('neutral', '중립'), ('affection', '애정'), ('amusement', '유쾌함'), ('anger', '분노'),
    ('arousal', '욕망의 고조'), ('awe', '경외'), ('bitterness', '씁쓸함'), ('confusion', '혼란'),
    ('contemplation', '숙고'), ('contentment', '차분한 만족'), ('determination', '결의'),
    ('disgust', '혐오'), ('elation', '환희'), ('enthusiasm', '열정 · 신남'), ('fear', '공포'),
    ('helplessness', '무력감'), ('longing', '갈망'), ('pride', '자부심'), ('relief', '안도'),
    ('sadness', '슬픔'), ('shame', '수치심'), ('surprise', '놀람'),
])
FISH_EMOTIONS = options([
    ('neutral', '중립'), ('calm', '차분함'), ('excited', '신남'), ('delight', '기쁨'),
    ('angry', '분노'), ('sad', '슬픔'), ('surprised', '놀람'), ('shocked', '충격'),
    ('laughing tone', '웃음 섞인 말투'), ('whisper', '속삭임'), ('shouting', '외침'),
    ('professional broadcast tone', '방송 진행'),
])
MODELS = {
    'qwen': {'label': 'Qwen3', 'description': '9가지 기본 목소리와 자연어 감정 지시', 'emotions': QWEN_EMOTIONS,
             'instructions': True, 'custom_voice': False, 'emotion_note': '자연어 지시를 사용하는 추천 프리셋입니다. 추가 지시로 세부 말투를 조절할 수 있습니다.'},
    'higgs': {'label': 'Higgs V3', 'description': '21가지 감정과 참조 음성 복제', 'emotions': HIGGS_EMOTIONS,
              'instructions': False, 'custom_voice': True, 'emotion_note': '공식 감정 21종을 지원합니다. 중립은 감정 태그를 적용하지 않습니다.'},
    'fish': {'label': 'Fish S2 Pro', 'description': '자유로운 표현 제어와 참조 음성 복제', 'emotions': FISH_EMOTIONS,
             'instructions': True, 'custom_voice': True, 'emotion_note': '자유 형식 표현 지시를 지원합니다. 아래는 자주 사용하는 추천 프리셋입니다.'},
}
REFERENCE_TEXTS = {
    'ko': '안녕하세요. 오늘도 함께해 주셔서 감사합니다. 지금부터 새로운 서비스를 쉽고 자세하게 안내해 드리겠습니다.',
    'en': 'Hello, and thank you for joining us today. Let me introduce our new service and explain how it can help you.',
}

HIGGS_CONTROLS = [
    {'id': 'speed', 'label': '말하기 속도', 'options': options([('very_slow','매우 느리게'),('slow','느리게'),('default','기본'),('fast','빠르게'),('very_fast','매우 빠르게')])},
    {'id': 'pitch', 'label': '음높이', 'options': options([('low','낮게'),('default','기본'),('high','높게')])},
    {'id': 'expression', 'label': '표현 강도', 'options': options([('low','약하게'),('default','기본'),('high','강하게')])},
    {'id': 'style', 'label': '발성 스타일', 'options': options([('default','기본'),('whispering','속삭임'),('shouting','외침'),('singing','노래')])},
]
MODELS['higgs']['controls'] = HIGGS_CONTROLS
