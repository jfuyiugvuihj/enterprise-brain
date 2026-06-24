"""Fix chat.py indentation by shifting lines 284-364 right by 4 spaces"""
path = 'C:/Users/fengx/PycharmProjects/企业智脑/app/api/v1/chat.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Lines 284-364 (0-indexed: 283-363) need 4 more spaces of indent
# They're at 12 spaces but should be at 16 (inside async for body)
for i in range(283, min(365, len(lines))):
    stripped = lines[i].lstrip()
    if stripped:  # non-empty line
        # Add 4 spaces to the leading whitespace to push from 12→16
        leading = len(lines[i]) - len(lines[i].lstrip())
        lines[i] = '    ' + lines[i]

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('done')
