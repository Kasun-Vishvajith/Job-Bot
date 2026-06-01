import re
import json

transcript_path = r'C:\Users\kasun\.gemini\antigravity\brain\b012acb4-fdaf-440e-9d46-5491329d2674\.system_generated\logs\transcript.jsonl'

with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        if 'card-thumb' in line:
            try:
                data = json.loads(line)
                if 'content' in data:
                    match = re.search(r'<article class="card[^>]*>.*?<div class="card-body">', data['content'], re.DOTALL)
                    if match:
                        print("FOUND RENDER:", match.group(0))
                        break
            except Exception as e:
                pass
