import re
import json

transcript_path = r'C:\Users\kasun\.gemini\antigravity\brain\b012acb4-fdaf-440e-9d46-5491329d2674\.system_generated\logs\transcript.jsonl'

found = False
with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        if 'card-thumb' in line:
            try:
                data = json.loads(line)
                content = data.get('content', '')
                if 'card-thumb' in content:
                    lines = content.split('\n')
                    for i, l in enumerate(lines):
                        if 'card-thumb' in l:
                            print(f"Line {i}: {l}")
                            if i > 0: print(f"  Prev: {lines[i-1]}")
                            if i < len(lines)-1: print(f"  Next: {lines[i+1]}")
                            found = True
                            break
            except Exception:
                pass
        if found: break
