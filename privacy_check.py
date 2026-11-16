"""Scan tracked files (or source candidates before git init). Never print matched secrets."""
from pathlib import Path
import re, subprocess, sys

ROOT=Path(__file__).resolve().parent
PRIVATE_DIRS={'data','instance','backups','tools','.venv','venv','node_modules','__pycache__','.git','MaiBot-main','MaiBot','WhaleGirl'}
SOURCE_SUFFIXES={'.py','.js','.html','.ps1','.cmd','.md','.json','.txt','.cs','.csproj','.yml','.yaml'}
PATTERNS={
    'provider credential':r'\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b',
    'private key':r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'personal user directory':r'(?i)[A-Z]:[/\\]Users[/\\](?!Public\b|EXAMPLE\b)[^\s/\\\"\x27]+',
    'real chat identifier':r'\b\d{7,}@chatroom\b|\bwxid_(?!xxx\b|example\b)[a-zA-Z0-9]{5,}\b',
    'live tunnel URL':r'https://[a-z0-9]+(?:-[a-z0-9]+)+\.trycloudflare\.com',
    'literal credential assignment':r'(?i)[\"\x27]?(?:api[_-]?key|access_token|secret)[\"\x27]?\s*[:=]\s*[\"\x27][A-Za-z0-9_-]{24,}[\"\x27]',
}

def check(paths):
    errors=[]
    for path in paths:
        relative=path.relative_to(ROOT)
        if any(part in PRIVATE_DIRS for part in relative.parts) or '.local.' in path.name:
            errors.append((str(relative),'private path'));continue
        if path.name not in ('LICENSE','.gitignore','.gitattributes') and path.suffix.lower() not in SOURCE_SUFFIXES:
            errors.append((str(relative),'unexpected file type'));continue
        try:content=path.read_text(encoding='utf-8-sig')
        except (UnicodeError,OSError):errors.append((str(relative),'unreadable/binary'));continue
        for label,pattern in PATTERNS.items():
            if re.search(pattern,content):errors.append((str(relative),label))
    return errors

def main():
    from build_source import sources
    paths=sources()
    errors=check(paths)
    for name,label in errors:print(name+': '+label+' (value hidden)')
    print('Privacy scan:',len(paths),'files;',len(errors),'findings. Manual review still required.')
    return bool(errors)

if __name__=='__main__':sys.exit(main())
