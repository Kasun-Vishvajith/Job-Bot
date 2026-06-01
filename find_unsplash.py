import re

transcript_path = r'C:\Users\kasun\.gemini\antigravity\brain\b012acb4-fdaf-440e-9d46-5491329d2674\.system_generated\logs\transcript.jsonl'

with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        if 'unsplash' in line.lower() or 'source.unsplash' in line.lower():
            print("Found unsplash reference")
            match = re.search(r'.{0,50}unsplash.{0,100}', line, re.IGNORECASE)
            if match: print(match.group(0))
            break
