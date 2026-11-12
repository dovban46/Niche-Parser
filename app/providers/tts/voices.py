"""Каталог голосів для вибору в UI. API-ключ ElevenLabs у нас без права `voices_read`, тому
список не тягнеться з API — це вручну перевірені voice_id (кожен відповідав 200 на синтез).
Свій голос із https://elevenlabs.io/app/voice-library можна вставити в UI як "власний ID".
"""

# eleven_multilingual_v2 говорить усіма мовами з SUPPORTED_LANGUAGES будь-яким голосом,
# але "language"-голоси (рідні для мови) звучать природніше — вони йдуть першими.
_ELEVENLABS_MULTILINGUAL = [
    {"id": "iB0m5bo5Htdz0t9yE0xq", "name": "Custom (дефолт)", "gender": "?", "note": "обраний користувачем, дефолт для ancient_mysteries — перейменуй тут, коли визначишся з іменем/статтю"},
    {"id": "nPczCjzI2devNBz1zQrb", "name": "Brian", "gender": "male", "note": "глибокий, спокійний — попередній дефолт"},
    {"id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel", "gender": "male", "note": "рівний, документальний"},
    {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam", "gender": "male", "note": "низький, впевнений"},
    {"id": "JBFqnCBsd6RMkjVDRZzb", "name": "George", "gender": "male", "note": "теплий, оповідний"},
    {"id": "cjVigY5qzO86Huf0OWal", "name": "Eric", "gender": "male", "note": "м'який, невимушений"},
    {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah", "gender": "female", "note": "м'який, розмовний"},
    {"id": "Xb7hH8MSUJpSbSDYk0k2", "name": "Alice", "gender": "female", "note": "чіткий, навчальний"},
    {"id": "XrExE9yKIg1WjnnlVkGX", "name": "Matilda", "gender": "female", "note": "привітний, теплий"},
    {"id": "pFZP5JQG7iQjIQuC4Bku", "name": "Lily", "gender": "female", "note": "виразний"},
    {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel", "gender": "female", "note": "стандартний демо-голос (звучить штучно)"},
]

_ELEVENLABS_NATIVE = {
    "pl": [
        {"id": "CLuTGacrAhcIhaJslbXt", "name": "Rafał", "gender": "male", "note": "рідний польський, найприродніший"},
    ],
}

_EDGE = {
    "uk": [("uk-UA-PolinaNeural", "Polina", "female"), ("uk-UA-OstapNeural", "Ostap", "male")],
    "en": [("en-US-AriaNeural", "Aria", "female"), ("en-US-GuyNeural", "Guy", "male")],
    "pl": [("pl-PL-ZofiaNeural", "Zofia", "female"), ("pl-PL-MarekNeural", "Marek", "male")],
    "de": [("de-DE-KatjaNeural", "Katja", "female"), ("de-DE-ConradNeural", "Conrad", "male")],
    "es": [("es-ES-ElviraNeural", "Elvira", "female"), ("es-ES-AlvaroNeural", "Alvaro", "male")],
    "it": [("it-IT-ElsaNeural", "Elsa", "female"), ("it-IT-DiegoNeural", "Diego", "male")],
    "fr": [("fr-FR-DeniseNeural", "Denise", "female"), ("fr-FR-HenriNeural", "Henri", "male")],
}

# Коротка фраза для прослуховування голосу (~100 символів — копійки навіть в ElevenLabs).
PREVIEW_TEXT = {
    "uk": "Привіт! Ось так звучатиме озвучка вашого відео. Слухайте уважно — інтонація має бути живою.",
    "en": "Hello! This is how the narration of your video will sound. Listen closely — the delivery should feel alive.",
    "pl": "Cześć! Tak będzie brzmiała narracja Twojego filmu. Posłuchaj uważnie — intonacja powinna być żywa.",
    "de": "Hallo! So wird die Erzählung Ihres Videos klingen. Hören Sie genau hin — die Betonung soll lebendig sein.",
    "es": "¡Hola! Así sonará la narración de tu vídeo. Escucha con atención: la entonación debe sonar viva.",
    "it": "Ciao! Ecco come suonerà la narrazione del tuo video. Ascolta con attenzione: l'intonazione deve essere viva.",
    "fr": "Bonjour ! Voici comment sonnera la narration de votre vidéo. Écoutez bien : l'intonation doit être vivante.",
}


def voices_for(provider: str, language: str) -> list[dict]:
    if provider == "elevenlabs":
        return _ELEVENLABS_NATIVE.get(language, []) + _ELEVENLABS_MULTILINGUAL
    if provider == "edge":
        return [
            {"id": vid, "name": name, "gender": gender, "note": "безкоштовний нейронний голос"}
            for vid, name, gender in _EDGE.get(language, _EDGE["uk"])
        ]
    return []


def voice_name(provider: str, language: str, voice_id: str | None) -> str | None:
    if not voice_id:
        return None
    for v in voices_for(provider, language) + _ELEVENLABS_MULTILINGUAL:
        if v["id"] == voice_id:
            return v["name"]
    return voice_id
