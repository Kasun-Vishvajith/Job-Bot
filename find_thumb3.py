import json
import re

transcript_path = r'C:\Users\kasun\.gemini\antigravity\brain\b012acb4-fdaf-440e-9d46-5491329d2674\.system_generated\logs\transcript.jsonl'

with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        if 'class="card-thumb"' in line:
            data = json.loads(line)
            content = data.get('content', '')
            if 'class="card-thumb"' in content:
                for match in re.finditer(r'.{0,50}class="card-thumb".{0,100}', content):
                    print(match.group(0))
                break
