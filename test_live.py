import time
import requests

time.sleep(1)
for conv_id in [None, 1, '1']:
    try:
        t0 = time.time()
        res = requests.post('http://localhost:10000/api/voice-assistant/chat', json={
            'message': 'Hello, what are you doing?',
            'conversation_id': conv_id,
            'voice': 'hi-IN-SwaraNeural',
            'language': 'auto',
            'speed': '+0%'
        }, timeout=20)
        dt = round(time.time() - t0, 2)
        if res.status_code == 200:
            data = res.json()
            print(f'conv_id={conv_id} -> SUCCESS ({dt}s): reply="{data["reply"][:60]}..." audio_url={data.get("audio_url")}')
        else:
            print(f'conv_id={conv_id} -> FAILED ({res.status_code}): {res.text[:200]}')
    except Exception as e:
        print(f'conv_id={conv_id} -> Exception: {e}')
